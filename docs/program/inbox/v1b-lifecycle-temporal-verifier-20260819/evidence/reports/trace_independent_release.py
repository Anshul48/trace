"""Independent S5 V1b-Trace release lifecycle checks.

The harness uses the verifier worktree's Trace code, a fresh SQLite file under
the leased scratch root, and deterministic in-process adapters only. It does
not exercise PostgreSQL/RLS, external indexes except for an injected failure
adapter, deployment migrations, or temporal semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from trace.v2.models import (
    CortexReleaseCreateRequest,
    CortexReleaseRollbackRequest,
    CortexReleaseValidateRequest,
    CortexValidationReceipt,
    IngestionRequest,
    QueryRequest,
)
from trace.v2.retrieval import HybridRetrievalEngine
from trace.v2.service import TraceService
from trace.v2.store import InvariantViolation, NotFoundError, SqliteEventStore


SCRATCH = Path(os.environ["S5_SCRATCH"])
SCRATCH.mkdir(parents=True, exist_ok=True)


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str, **_: object) -> dict[str, object]:
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "object_key": "s5/source",
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {},
        }

    def put_text(self, text: str, media_type: str, **kwargs: object) -> dict[str, object]:
        return self.put_bytes(text.encode("utf-8"), media_type, **kwargs)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def open_service(root: Path | None = None, *, persistent: bool = False, retrieval_engine=None) -> tuple[SqliteEventStore, TraceService]:
    path = str(root / "trace.sqlite3") if persistent and root is not None else ":memory:"
    store = SqliteEventStore(path)
    service = TraceService(store, MemoryObjectStore(), retrieval_engine=retrieval_engine)
    return store, service


def create_active(service: TraceService, workspace_id: str, policy: str = "v0") -> dict:
    planned = service.create_cortex_release(
        CortexReleaseCreateRequest(workspace_id=workspace_id, policy_revision=policy)
    )
    validated = service.validate_cortex_release(
        planned["release_id"],
        CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)),
    )
    assert validated["status"] == "validated"
    active = service.activate_cortex_release(planned["release_id"])
    assert active["status"] == "active"
    return active


def run_case(name: str, fn):
    started = time.perf_counter()
    try:
        observation = fn()
        return {
            "case": name,
            "status": "pass",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "observation": observation,
        }
    except Exception as exc:
        return {
            "case": name,
            "status": "fail",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": {"type": type(exc).__name__, "detail": str(exc)[:500]},
        }


def case_candidate_isolation_and_same_pair():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        store, service = open_service(Path(raw))
        try:
            ingestion = service.ingest(
                IngestionRequest(workspace_id="alpha", text="alpha one\n\nalpha two\n\nalpha three")
            )
            atoms = store.ingestion_atoms(ingestion["ingestion_id"])
            a1, a2 = atoms[0]["atom_version_id"], atoms[1]["atom_version_id"]
            active = create_active(service, "alpha")
            store.put_affinity_edge(
                workspace_id="alpha", source_atom_version_id=a1, target_atom_version_id=a2,
                score=0.60, signal={"provider": "active"}, expires_at="2999-01-01T00:00:00+00:00",
                release_id=active["release_id"],
            )
            candidate = service.create_cortex_release(
                CortexReleaseCreateRequest(workspace_id="alpha", policy_revision="candidate")
            )
            cid = candidate["release_id"]
            store.put_affinity_edge(
                workspace_id="alpha", source_atom_version_id=a1, target_atom_version_id=a2,
                score=0.95, signal={"provider": "candidate"}, expires_at="2999-01-01T00:00:00+00:00",
                release_id=cid,
            )
            store.upsert_activation_prior(
                workspace_id="alpha", atom_version_id=a1, prior_kind="pin", score=0.8, release_id=cid,
            )
            ordinary_edges = store.affinity_neighbors("alpha", [a1])
            candidate_edges = store.affinity_neighbors("alpha", [a1], release_id=cid)
            ordinary_priors = store.activation_priors("alpha", [a1])
            candidate_priors = store.activation_priors("alpha", [a1], release_id=cid)
            assert ordinary_edges[0]["score"] == 0.60
            assert ordinary_edges[0]["signal"]["provider"] == "active"
            assert candidate_edges[0]["score"] == 0.95
            assert ordinary_priors == {}
            assert candidate_priors[a1][0]["score"] == 0.8
            return {
                "predecessor_release_id": active["release_id"],
                "candidate_release_id": cid,
                "ordinary_edge": ordinary_edges,
                "candidate_edge": candidate_edges,
                "ordinary_priors": ordinary_priors,
                "candidate_priors": candidate_priors,
                "source_hash": digest(atoms),
                "projection_hash": digest({"ordinary": ordinary_edges, "candidate": candidate_edges}),
            }
        finally:
            store.close()


def case_validation_and_atomic_handover():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        store, service = open_service(Path(raw))
        try:
            first = create_active(service, "alpha")
            candidate = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
            cid = candidate["release_id"]
            try:
                service.activate_cortex_release(cid)
            except InvariantViolation as exc:
                building_error = str(exc)
            else:
                raise AssertionError("building release activated")
            failed = service.validate_cortex_release(
                cid,
                CortexReleaseValidateRequest(validation_receipt={"passed": False, "failure_detail": "validation fault"}),
            )
            assert failed["status"] == "failed"
            try:
                service.activate_cortex_release(cid)
            except InvariantViolation as exc:
                failed_error = str(exc)
            else:
                raise AssertionError("failed release activated")
            successor = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
            sid = successor["release_id"]
            service.validate_cortex_release(
                sid,
                CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)),
            )
            activated = service.activate_cortex_release(sid)
            predecessor = store.get_cortex_release(first["release_id"])
            assert activated["release_id"] == sid
            assert store.get_active_cortex_release("alpha")["release_id"] == sid
            assert predecessor["status"] == "superseded"
            return {
                "predecessor_release_id": first["release_id"],
                "failed_candidate_id": cid,
                "successor_release_id": sid,
                "building_activation_error": building_error,
                "failed_activation_error": failed_error,
                "active_after": store.get_active_cortex_release("alpha"),
                "predecessor_after": predecessor,
            }
        finally:
            store.close()


def case_atomic_activation_crash_and_restart():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        root = Path(raw)
        store, service = open_service(root, persistent=True)
        try:
            first = create_active(service, "alpha")
            candidate = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
            cid = candidate["release_id"]
            service.validate_cortex_release(
                cid,
                CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)),
            )
            original = store._append_event

            def crash_after_pointer_sql(conn, *args, **kwargs):
                if kwargs.get("event_type") == "cortex.release_activated":
                    raise RuntimeError("independent simulated crash after pointer SQL")
                return original(conn, *args, **kwargs)

            store._append_event = crash_after_pointer_sql
            try:
                service.activate_cortex_release(cid)
            except RuntimeError as exc:
                expected_error = str(exc)
            else:
                raise AssertionError("activation crash did not surface")
            store._append_event = original
            active_after_fault = store.get_active_cortex_release("alpha")
            candidate_after_fault = store.get_cortex_release(cid)
            assert active_after_fault["release_id"] == first["release_id"]
            assert candidate_after_fault["status"] == "validated"
        finally:
            store.close()
        reopened, reopened_service = open_service(root, persistent=True)
        try:
            active_after_restart = reopened.get_active_cortex_release("alpha")
            assert active_after_restart["release_id"] == first["release_id"]
            activated = reopened_service.activate_cortex_release(cid)
            assert activated["release_id"] == cid
            return {
                "predecessor_release_id": first["release_id"],
                "candidate_release_id": cid,
                "fault": expected_error,
                "active_after_fault": active_after_fault,
                "candidate_after_fault": candidate_after_fault,
                "active_after_restart": active_after_restart,
                "replay_activation": activated,
            }
        finally:
            reopened.close()


def case_pointer_rollback_and_workspace_isolation():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        store, service = open_service(Path(raw))
        try:
            first = create_active(service, "alpha")
            successor = create_active(service, "alpha", policy="v1")
            rolled_back = service.rollback_cortex_release(
                CortexReleaseRollbackRequest(workspace_id="alpha", reason="independent rollback")
            )
            assert rolled_back["release_id"] == first["release_id"]
            assert store.get_active_cortex_release("alpha")["release_id"] == first["release_id"]
            assert store.get_cortex_release(successor["release_id"])["status"] == "superseded"

            alpha_candidate = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
            beta_candidate = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="beta"))
            beta_ids = {item["release_id"] for item in service.list_cortex_releases("beta")}
            assert alpha_candidate["release_id"] not in beta_ids
            assert beta_candidate["release_id"] in beta_ids
            try:
                service.rollback_cortex_release(
                    CortexReleaseRollbackRequest(workspace_id="beta", target_release_id=alpha_candidate["release_id"])
                )
            except (InvariantViolation, NotFoundError) as exc:
                cross_workspace_error = str(exc)
            else:
                raise AssertionError("cross-workspace rollback succeeded")
            return {
                "initial_release_id": first["release_id"],
                "successor_release_id": successor["release_id"],
                "rollback": rolled_back,
                "beta_release_ids": sorted(beta_ids),
                "cross_workspace_error": cross_workspace_error,
            }
        finally:
            store.close()


class FailingAlias:
    provider_id = "independent-failing-alias"

    def promote_alias(self, workspace_id: str, release_id: str) -> None:
        raise RuntimeError(f"alias promotion unavailable for {workspace_id}/{release_id}")


def case_external_promotion_compensation():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        store, service = open_service(Path(raw))
        try:
            first = create_active(service, "alpha")
            candidate = service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
            cid = candidate["release_id"]
            service.validate_cortex_release(
                cid,
                CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)),
            )
            service.retrieval_engine.lexical_index = FailingAlias()
            try:
                service.activate_cortex_release(cid)
            except InvariantViolation as exc:
                expected_error = str(exc)
            else:
                raise AssertionError("external alias failure activated candidate")
            failed = store.get_cortex_release(cid)
            active = store.get_active_cortex_release("alpha")
            assert failed["status"] == "failed"
            assert active["release_id"] == first["release_id"]
            return {
                "predecessor_release_id": first["release_id"],
                "failed_candidate_id": cid,
                "error": expected_error,
                "failed_release": failed,
                "active_after_failure": active,
            }
        finally:
            store.close()


def case_source_watermark_and_read_identity():
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as raw:
        store, service = open_service(Path(raw))
        try:
            ingestion = service.ingest(IngestionRequest(workspace_id="alpha", text="release identity evidence"))
            atoms = store.ingestion_atoms(ingestion["ingestion_id"])
            active = create_active(service, "alpha")
            response = service.query(QueryRequest(workspace_id="alpha", query="identity evidence"))
            diagnostics = response["retrieval_diagnostics"]
            bundle = store.get_bundle(response["evidence_bundle_id"])
            bundled_diagnostics = bundle["query"]["retrieval_diagnostics"]
            assert diagnostics["active_cortex_release_id"] == active["release_id"]
            assert bundled_diagnostics["active_cortex_release_id"] == active["release_id"]
            before_arrival = active["spine_event_watermark"]
            service.ingest(IngestionRequest(workspace_id="alpha", text="arrived after release"))
            current = store.get_active_cortex_release("alpha")
            assert current["release_id"] == active["release_id"]
            assert int(before_arrival) <= int(store.last_event_offset())
            return {
                "active_release_id": active["release_id"],
                "source_hash": digest(atoms),
                "ordinary_read_diagnostics": diagnostics,
                "bundle_diagnostics": bundled_diagnostics,
                "release_watermark": before_arrival,
                "watermark_after_source_arrival": store.last_event_offset(),
            }
        finally:
            store.close()


CASES = [
    ("candidate_isolation_and_same_pair", case_candidate_isolation_and_same_pair),
    ("validation_and_atomic_handover", case_validation_and_atomic_handover),
    ("atomic_activation_crash_and_restart", case_atomic_activation_crash_and_restart),
    ("pointer_rollback_and_workspace_isolation", case_pointer_rollback_and_workspace_isolation),
    ("external_promotion_compensation", case_external_promotion_compensation),
    ("source_watermark_and_read_identity", case_source_watermark_and_read_identity),
]


if __name__ == "__main__":
    receipt = {
        "verifier_id": "v1b-trace-release-verifier-20260819",
        "base_commit": "454c5aed2200796ac9874e4fbe6e099bdb53f830",
        "claim_level": "C1",
        "backend": "Trace SQLite local store with deterministic in-process adapters",
        "cases": [run_case(name, fn) for name, fn in CASES],
    }
    receipt["summary"] = {
        "passed": sum(case["status"] == "pass" for case in receipt["cases"]),
        "failed": sum(case["status"] == "fail" for case in receipt["cases"]),
        "total": len(receipt["cases"]),
    }
    serialized = json.dumps(receipt, sort_keys=True, indent=2, default=str)
    receipt_path = os.environ.get("S5_RECEIPT")
    if receipt_path:
        Path(receipt_path).write_text(serialized + "\n", encoding="utf-8")
        print(json.dumps({"summary": receipt["summary"], "receipt_path": receipt_path}, indent=2))
    else:
        print(serialized)
