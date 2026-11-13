# SPDX-License-Identifier: Apache-2.0
"""Identifier-token TF-IDF vectors for atom source text (stdlib only).

Tokeniser: identifiers split on underscores, then CamelCase/subword pieces,
lowercased. Weight is term-frequency times log(ndocs / doc-frequency),
L2-normalised. Vectors are sparse {term_index: weight} maps over a sorted
vocabulary; densify() expands one draw to dense lists for the organiser.
Deterministic: documents and vocabulary are processed in sorted order.
"""
import math
import re

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SUBWORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")


def tokenise(text):
    tokens = []
    for ident in IDENT.findall(text):
        for part in ident.split("_"):
            if not part:
                continue
            for sub in SUBWORD.findall(part):
                if sub:
                    tokens.append(sub.lower())
    return tokens


def build(documents):
    """documents: list of (id, text). Returns vocab/idf/sparse/norm info."""
    ordered = sorted(documents)
    ndocs = len(ordered)
    tokdocs = []
    docfreq = {}
    for doc_id, text in ordered:
        toks = tokenise(text)
        tokdocs.append((doc_id, toks))
        for term in set(toks):
            docfreq[term] = docfreq.get(term, 0) + 1
    vocab = sorted(docfreq)
    index = {term: i for i, term in enumerate(vocab)}
    idf = {term: math.log(ndocs / count) for term, count in docfreq.items()}
    sparse = {}
    n_zero = 0
    for doc_id, toks in tokdocs:
        termfreq = {}
        for tok in toks:
            termfreq[tok] = termfreq.get(tok, 0) + 1
        weights = {}
        for term, count in termfreq.items():
            weights[index[term]] = float(count) * idf[term]
        norm = math.sqrt(sum(w * w for w in weights.values()))
        if norm == 0.0:
            n_zero += 1
            sparse[doc_id] = {}
        else:
            sparse[doc_id] = {i: w / norm for i, w in weights.items()}
    return {"vocab": vocab, "idf": [idf[t] for t in vocab], "sparse": sparse,
            "ndocs": ndocs, "n_zero": n_zero}


def densify(sparse, dim):
    """One sparse vector to a dense list of length dim."""
    dense = [0.0] * dim
    for i, w in sparse.items():
        dense[i] = w
    return dense
