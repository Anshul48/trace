"""lane-BENCH10M TB backends: shipped C2-10M serving stack on fresh Narrow stores.

Two arms, one module (identical bytes except the emission budget):

- ``C2Bench10MShipped`` (A1, PRIMARY): NarrowQuery cfg fixed to the
  adopted shipping budgets M80-P100-A40 (M_REGIONS=80,
  PRUNE_CAP=100, MAX_ENTRIES=40).
- ``C2Bench10MK100`` (A2, diagnostic): same stack, MAX_ENTRIES=100,
  isolating the A40 cutoff effect under the TB K=100 protocol.

Deliberate, recorded differences from TB's built-in trace_narrow:

1. Fixed shipped budgets instead of ``MAX_ENTRIES=top_k``. A1
   returns at most 40 entries per query; metrics at cutoffs >40
   are unavailable-by-design (TB marks them, never imputes).
2. Raw MiniLM encoding (``normalize_embeddings=False``), matching
   the demonstrated serving path (lane-S5S ``s5s_serve_demo.py``)
   and the pinned CPU encode convention
   (``tl-eval/gpu_encode/config.py``: "cosine is downstream").
   trace_narrow normalizes; the shipped stack does not.

Everything else mirrors trace_narrow: fresh disposable store per
dataset, resident encoder per run (one process), same abstention
rule, same provenance hooks. No TB or tlsys file is modified.

Select with (module on PYTHONPATH)::

    trace-bench run --dataset scifact --baselines \\
        bm25,python:c2_bench10m:C2Bench10MShipped

Config (``--config`` JSON, keyed by the full ``python:...`` name)
accepts ``architecture_dir``, ``model_name``, ``revision``.
"""

import os
import sys
import tempfile
from pathlib import Path

from trace_bench.baselines.base import (
    BaseRetriever,
    RetrievalCandidate,
    RetrievalResponse,
)
from trace_bench.baselines.trace_narrow_retriever import (
    discover_architecture_dir,
)
from trace_bench.datasets.loader import compute_sha256, file_sha256

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# Adopted shipping budgets (lane-S-SEAT seat_sweep.py; SHIPPED 2026-10-08).
BUDGET_M_REGIONS = 80
BUDGET_PRUNE_CAP = 100
BUDGET_MAX_ENTRIES_SHIPPED = 40
BUDGET_MAX_ENTRIES_K100 = 100

# Product chunking defaults (tl-sys/tlsys/ingest.py CHUNK_TOKENS/OVERLAP).
CHUNK_TOKENS = 200
CHUNK_OVERLAP = 50


class _C2Bench10MBase(BaseRetriever):
    """Shared fresh-store Narrow machinery; subclasses fix the arm + budget."""

    arm = "base"
    max_entries = BUDGET_MAX_ENTRIES_SHIPPED
    engine_name = "c2_bench10m_base"

    def __init__(self, architecture_dir=None, model_name=MODEL_NAME,
                 revision=MODEL_REVISION):
        self.architecture_dir, self.architecture_provenance = (
            discover_architecture_dir(architecture_dir))
        self.model_name, self.revision = model_name, revision
        self._temporary = None
        self._store = self._index = self._model = None
        self._serving_view_kind = None

    # -- BaseRetriever API --

    def name(self):
        return self.engine_name

    def _budgets(self):
        return {"M_REGIONS": BUDGET_M_REGIONS,
                "PRUNE_CAP": BUDGET_PRUNE_CAP,
                "MAX_ENTRIES": self.max_entries}

    def configuration(self):
        return {
            "arm": self.arm,
            "query_budgets": self._budgets(),
            "budget_policy": "M80-P100-A40 adopted (c2-10m SHIPPED)"
            if self.max_entries == BUDGET_MAX_ENTRIES_SHIPPED
            else "M80-P100 + MAX_ENTRIES=100 diagnostic (NOT shipped policy)",
            "selection_limit": "at most MAX_ENTRIES entries per query; "
            "fewer than K distinct documents possible by design",
            "model_name": self.model_name,
            "revision": self.revision,
            "embedding": "raw st.encode, normalize_embeddings=False "
            "(shipped CPU convention; cosine is downstream)",
            "path": "S-04 Narrow",
            "chunking": f"product defaults: {CHUNK_TOKENS} tokens, "
            f"overlap {CHUNK_OVERLAP}",
            "serving_view": self._serving_view_kind,
            "architecture_provenance": self.architecture_provenance,
            "deployment_condition": "persistent process + resident "
            "encoder per run (TB holds one backend instance per run)",
        }

    def target_identity(self):
        from trace_bench.target_identity import snapshot_target_identity
        return snapshot_target_identity(self.architecture_dir)

    def native_pins(self):
        triple = getattr(self._index, "triple", None)
        if triple is None:
            return None
        birth, epoch, seq = None, None, None
        try:
            raw_birth, raw_epoch, raw_seq = str(triple).rsplit(":", 2)
            birth, epoch, seq = raw_birth, int(raw_epoch), int(raw_seq)
        except (ValueError, TypeError):
            pass
        return {"tl_birth": birth, "tl_epoch": epoch, "tl_seq": seq,
                "tl_triple": str(triple)}

    def implementation_identity(self):
        files = []
        for directory in (self.architecture_dir / "tl-sys" / "tlsys",
                          self.architecture_dir / "tl-candidate-batch" / "candidate"):
            files.extend((str(path.relative_to(self.architecture_dir)), file_sha256(path))
                         for path in sorted(directory.glob("*.py")))
        import json
        import sys as _sys
        target = self.target_identity()
        resolved = None
        module_file = getattr(_sys.modules.get("tlsys"), "__file__", None)
        if module_file is not None:
            try:
                resolved = {"tlsys": {"imported": True,
                                      "init_sha256": file_sha256(module_file)}}
            except OSError:
                resolved = {"tlsys": {"imported": True, "init_sha256": None}}
        serving = {}
        for rel in ("tl-sys/tlsys/dossier.py", "tl-sys/tlsys/relquery.py",
                    "tl-sys/tlsys/relserve.py", "tl-sys/tlsys/query.py",
                    "tl-sys/tlsys/index.py",
                    "tl-sys/tlsys/serving/generation.py",
                    "tl-sys/tlsys/prodstate.py"):
            try:
                serving[rel] = file_sha256(self.architecture_dir / rel)
            except OSError:
                serving[rel] = None
        return {"candidate_revision": target.get("candidate_revision"),
                "product_sources_sha256": compute_sha256(json.dumps(files)),
                "target_role": "TL",
                "canonical_engine": self.engine_name,
                "arm": self.arm,
                "query_budgets": self._budgets(),
                "serving_file_sha256": serving,
                "target_identity": target,
                "resolved_modules": resolved}

    def index(self, documents):
        if os.name == "nt":
            raise RuntimeError("c2_bench10m requires POSIX locking. Run TB in WSL/Linux.")
        source = self.architecture_dir / "tl-sys"
        if not (source / "tlsys").is_dir():
            raise FileNotFoundError("Set architecture_dir in --config to the checkout containing tl-sys.")
        if "tlsys" in sys.modules and Path(sys.modules["tlsys"].__file__).resolve().parent != source / "tlsys":
            raise RuntimeError("A different tlsys checkout is already imported; start a fresh process.")
        sys.path.insert(0, str(source))
        from trace_bench.target_identity import no_target_bytecode
        with no_target_bytecode():
            from sentence_transformers import SentenceTransformer
            from tlsys.store_if import TLStore
            from tlsys.ingest import ingest_docs
            from tlsys.index import NarrowIndex
        # Resident encoder for this run (deployment condition, per-run scope).
        self._model = SentenceTransformer(self.model_name, revision=self.revision)
        self._temporary = tempfile.TemporaryDirectory(prefix="tb_c2_bench10m_")

        def embed_texts(texts):
            return self._model.encode(
                texts, normalize_embeddings=False,
                show_progress_bar=False).tolist()

        self._store = TLStore(str(Path(self._temporary.name) / "store"),
                              create=True, lease_owner="c2-bench10m")
        ingest_docs(self._store, [(d.doc_id, f"{d.title}\n{d.text}".strip())
                                  for d in documents], embed_texts)
        self._index = NarrowIndex(self._store, self._store.pin())
        view = getattr(self._index, "serving_view", None)
        if view is None:
            view = getattr(self._index, "_view", None)
        self._serving_view_kind = (type(view).__name__ if view is not None else None)

    def retrieve_with_outcome(self, query, top_k=10):
        from trace_bench.target_identity import no_target_bytecode
        with no_target_bytecode():
            from tlsys.query import NarrowQuery

        def embed_one(text):
            return self._model.encode(
                text, normalize_embeddings=False,
                show_progress_bar=False).tolist()

        dossier, receipt = NarrowQuery(
            self._store, self._index, embed_one,
            cfg=self._budgets()).run(query)
        if receipt["execution"]["status"] != "complete":
            raise RuntimeError(f"Trace returned incomplete execution: {receipt['execution']}")
        receipt["storage_calls"] = self._store.trace.summary()
        entries = dossier["entries"]
        abstained = not entries and receipt["support_findings"] == "examined-no-support"
        return RetrievalResponse(candidates=[RetrievalCandidate(
            e["doc_id"], e["emitted_score"], e["text"], metadata={"atom_id": e["atom_id"],
                "span": e["span"], "generation": e["resolving_generation"]}) for e in entries],
            abstained=abstained, receipt=receipt)

    def retrieve(self, query, top_k=10):
        return self.retrieve_with_outcome(query, top_k).candidates

    def preserved_document_ids(self):
        return set(self._index.doc_atoms)

    def organization_snapshot(self):
        memberships = [h["members"] for h in self._index.holons.values()]
        return {"source_atom_ids": list(self._index.atoms),
                "indexed_atom_ids": [aid for group in memberships for aid in group],
                "memberships": memberships, "evidence": {
                    "generation": self._index.triple, "path": "committed per-document holons",
                    "storage_calls": self._store.trace.summary()}}

    def cleanup(self):
        if self._store is not None:
            self._store.close()
            self._store = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


class C2Bench10MShipped(_C2Bench10MBase):
    """A1 PRIMARY: shipped serving stack + adopted M80-P100-A40."""

    arm = "shipped-M80-P100-A40"
    max_entries = BUDGET_MAX_ENTRIES_SHIPPED
    engine_name = "c2_bench10m_shipped"


class C2Bench10MK100(_C2Bench10MBase):
    """A2 diagnostic: shipped stack, MAX_ENTRIES=100 (K-filling check)."""

    arm = "diagnostic-M80-P100-A100"
    max_entries = BUDGET_MAX_ENTRIES_K100
    engine_name = "c2_bench10m_k100"
