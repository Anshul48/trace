"""Shared scratch-store fixtures for Lane S serving tests.

Local-dev only: scratch stores under /tmp, deterministic fake encoders
(no model weights), small populations (unit tests: tens of atoms;
parity seeds: thousands). OOM guardrail: nothing here exceeds ~100 MB RSS.
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))

import numpy as np  # noqa: E402

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402


def fixture_approval(tag):
    """Explicitly-labeled test fixture leg (NOT operator consent)."""
    return {"type": "user", "approval_id": "fixture-c2lanes-" + tag}


def emb_votes(texts, dim=8):
    """Deterministic keyword-vote embedding (axis-aligned + jitter)."""
    out = []
    for t in texts:
        low = t.lower()
        v = [0.0] * dim
        v[0] = float(low.count("sport") + low.count("cat")
                     + low.count("alpha"))
        v[1] = float(low.count("medic") + low.count("dog")
                     + low.count("beta"))
        v[2] = float(len(t) % 7)
        v[3] = float(len(low.split()) % 5)
        for i in range(4, dim):
            v[i] = float((len(t) * (i + 1)) % 11) / 11.0
        out.append(v)
    return out


class UnitNormEmbed:
    """Seeded unit-norm random embedding (E2-like geometry).

    Same text -> same vector (memoized). Vectors are quantized
    through float32 like production (committed descriptors parse
    from JSON-serialized FP32 cache values, so exactly-held rows
    carry no dense override). `dup_map` forces exact duplicates:
    {text: canonical_text}.
    """

    def __init__(self, dim=384, seed=20261006):
        self.dim = dim
        self.rng = random.Random(seed)
        self.memo = {}
        self.dup_map = {}

    def __call__(self, texts):
        out = []
        for t in texts:
            t = self.dup_map.get(t, t)
            if t not in self.memo:
                v = np.array([self.rng.gauss(0.0, 1.0)
                              for _ in range(self.dim)])
                n = float(np.linalg.norm(v)) or 1.0
                v = (v / n).astype(np.float32).astype(np.float64)
                self.memo[t] = v.tolist()
            out.append(list(self.memo[t]))
        return out


def vocab_text(rng, vocab, n_terms):
    return " ".join(rng.choice(vocab) for _ in range(n_terms))


def make_vocab(rng, size=2000):
    stops = ["the", "a", "an", "of", "and", "in", "on", "to", "is",
             "for", "with", "as", "by", "at", "from"]
    words = list(stops)
    while len(words) < size:
        words.append(f"w{len(words)}x{rng.randrange(100000)}")
    return words


def make_docs(n_docs, seed=7, vocab_size=2000, dup_every=0,
              min_terms=20, max_terms=120):
    """[(doc_id, text)] deterministic; every dup_every-th doc duplicates
    doc 0's text exactly (tie cases) when dup_every > 0."""
    rng = random.Random(seed)
    vocab = make_vocab(rng, vocab_size)
    docs = []
    for i in range(n_docs):
        if dup_every and i > 0 and i % dup_every == 0:
            docs.append((f"sdoc-{i}", docs[0][1]))
        else:
            n = rng.randint(min_terms, max_terms)
            docs.append((f"sdoc-{i}", vocab_text(rng, vocab, n)))
    return docs


def make_store(docs, emb, retire=None, organize=False,
               prefix="tlsys-lanes-", place_xdoc=True):
    """Ingest docs into a scratch store; optionally retire + organize.

    retire: [doc_id] retired via lifecycle.retire_docs (approval-bound).
    Returns (tl, tmpdir, pin).
    """
    tmp = tempfile.mkdtemp(prefix=prefix)
    root = os.path.join(tmp, "store")
    tl = TLStore(root, create=True, lease_owner="test-c2lanes")
    ingest_docs(tl, docs, emb, place_xdoc=place_xdoc)
    if retire:
        retire_docs(tl, list(retire), reason="lanes-fixture",
                    approvals={d: fixture_approval(f"retire-{d}")
                               for d in retire})
    if organize:
        organize_segments(tl)
    return tl, tmp, tl.pin()
