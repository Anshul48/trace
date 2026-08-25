"""Implementation unit tests for durable fail-closed erasure state machine and revisioned release activation."""

import hashlib
import hmac
import json
import os
import tempfile
import uuid
from typing import Any
import pytest

from trace.v2.models import SourceErasureRequest, CortexReleaseActivateRequest
from trace.v2.service import TraceService, LocalPrivateObjectStore
from trace.v2.store import SqliteEventStore, InvariantViolation, NotFoundError



class MockObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.delete_calls: list[str] = []
        self.delete_should_raise = False
        self.head_should_raise = False
        self.head_status = 200

    def put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str | None = None) -> dict[str, Any]:
        digest = hashlib.sha256(raw).hexdigest()
        key = f"workspace/{workspace_id}/{digest}"
        self.objects[key] = raw
        return {"content_hash": digest, "object_key": key, "byte_length": len(raw), "media_type": media_type}

    def delete_object(self, object_key: str) -> dict[str, Any]:
        self.delete_calls.append(object_key)
        if self.delete_should_raise:
            raise RuntimeError("simulated S3 connection timeout")
        self.objects.pop(object_key, None)
        return {"deleted": True, "object_key": object_key}

    def verify_object_absent(self, object_key: str) -> bool:
        if self.head_should_raise:
            raise RuntimeError("simulated S3 500 Internal Error on HEAD")
        return object_key not in self.objects


class MockRevisionedIndex:
    def __init__(self, name: str) -> None:
        self.name = name
        self.aliases: dict[str, str] = {}
        self.revisions: dict[str, set[str]] = {}
        self.activate_should_raise = False
        self.delete_atom_should_raise = False

    def get_active_alias(self, alias: str | None = None) -> str | None:
        return self.aliases.get(alias or self.name)

    def activate_revision(self, revision: str, *, alias: str | None = None) -> None:
        if self.activate_should_raise:
            raise RuntimeError(f"simulated {self.name} connection failure during alias swap")
        self.aliases[alias or self.name] = revision

    def verify_alias(self, revision: str, *, alias: str | None = None) -> bool:
        return self.aliases.get(alias or self.name) == revision

    def restore_alias(self, target: str, *, alias: str | None = None) -> None:
        self.aliases[alias or self.name] = target

    def delete_alias(self, alias: str) -> None:
        self.aliases.pop(alias, None)

    def delete_atom(self, atom_version_id: str, *, revision: str) -> None:
        if self.delete_atom_should_raise:
            raise RuntimeError(f"simulated {self.name} delete error")
        if revision in self.revisions:
            self.revisions[revision].discard(atom_version_id)

    def verify_atom_absent(self, atom_version_id: str, *, revision: str) -> bool:
        return atom_version_id not in self.revisions.get(revision, set())


@pytest.fixture
def store() -> SqliteEventStore:
    s = SqliteEventStore(":memory:")
    s.initialize()
    return s


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-secret-key-32-bytes-long!!"
    monkeypatch.setenv("TRACE_ERASURE_SIGNING_KEY", key)
    return key


def _ingest_atom(store: SqliteEventStore, workspace_id: str, content: str, object_key: str | None = None) -> str:
    raw = content.encode("utf-8")
    content_hash = hashlib.sha256(raw).hexdigest()
    attachment = {
        "content_hash": content_hash,
        "object_key": object_key or f"fixture/{content_hash}",
        "media_type": "text/plain",
        "byte_length": len(raw),
        "metadata": {},
    }
    result = store.ingest(
        workspace_id=workspace_id,
        source={"uri": "fixture://tr2", "media_type": "text/plain", "adapter": "test"},
        attachment=attachment,
        atoms=[{
            "content": content,
            "start": 0,
            "end": len(content),
            "ordinal": 0,
            "parser_location": "fixture:1",
            "temporal": {},
        }],
        actor="test",
        visibility="private",
        idempotency_key=None,
    )
    return str(store.ingestion_atoms(result["ingestion_id"])[0]["atom_version_id"])


def test_durable_erasure_happy_path(store: SqliteEventStore, signing_key: str) -> None:
    mock_obj = MockObjectStore()
    service = TraceService(store=store, object_store=mock_obj)

    # Ingest a source atom with object attachment
    obj_info = mock_obj.put_bytes(b"secret payload content", "text/plain", workspace_id="ws-1")
    atom_id = _ingest_atom(store, "ws-1", "secret payload content", object_key=obj_info["object_key"])

    # Verify object exists before erasure
    assert not mock_obj.verify_object_absent(obj_info["object_key"])

    # Perform erasure
    res = service.erase_source(atom_id, SourceErasureRequest(actor="compliance-officer", reason="GDPR Article 17"))

    assert res["state"] == "redacted_purged"
    assert res["atom_version_id"] == atom_id
    assert res["workspace_id"] == "ws-1"
    receipt = res["erasure_receipt"]
    assert receipt["action"] == "redacted_purged"
    assert "signature" in receipt

    # Verify receipt allow-list: NO sensitive content or raw properties
    assert "secret" not in json.dumps(receipt)
    assert "object_key" not in receipt
    assert "content" not in receipt
    assert "reason" not in receipt  # excluded from receipt allow-list

    # Verify external object deleted & verified absent
    assert mock_obj.verify_object_absent(obj_info["object_key"])

    # Verify DB state purged
    atoms = store.atom_versions([atom_id])
    assert atoms[0]["content"] == ""

    # Verify repeat erasure returns exact identical receipt with 0 new writes/events
    with store._connect() as conn:
        before_event_count = conn.execute("SELECT COUNT(*) FROM events WHERE stream_id=?", (f"node:{atom_id}",)).fetchone()[0]
    delete_call_count = len(mock_obj.delete_calls)

    repeat_res = service.erase_source(atom_id, SourceErasureRequest(actor="repeat-caller"))
    assert repeat_res["erasure_receipt"] == receipt
    assert repeat_res["event_offset"] == res["event_offset"]

    with store._connect() as conn:
        after_event_count = conn.execute("SELECT COUNT(*) FROM events WHERE stream_id=?", (f"node:{atom_id}",)).fetchone()[0]
    assert after_event_count == before_event_count
    assert len(mock_obj.delete_calls) == delete_call_count


def test_erasure_fail_closed_on_object_deletion_error(store: SqliteEventStore, signing_key: str) -> None:
    mock_obj = MockObjectStore()
    mock_obj.delete_should_raise = True  # S3 delete failure
    service = TraceService(store=store, object_store=mock_obj)

    obj_info = mock_obj.put_bytes(b"fail-closed content", "text/plain", workspace_id="ws-1")
    atom_id = _ingest_atom(store, "ws-1", "fail-closed content", object_key=obj_info["object_key"])

    # Erasure must fail closed (raise InvariantViolation)
    with pytest.raises(InvariantViolation, match="compliance erasure failed"):
        service.erase_source(atom_id, SourceErasureRequest(actor="compliance-officer"))

    # Verify operation is in retryable_failure state, NOT completed
    op = store.get_erasure_operation("ws-1", atom_id)
    assert op is not None
    assert op["state"] == "retryable_failure"
    assert op["erasure_receipt"] is None

    # Verify DB content was NOT wiped yet
    atoms = store.atom_versions([atom_id])
    assert atoms[0]["content"] == "fail-closed content"

    # Now repair the object store connectivity and retry
    mock_obj.delete_should_raise = False
    retry_res = service.erase_source(atom_id, SourceErasureRequest(actor="compliance-officer"))
    assert retry_res["state"] == "redacted_purged"
    assert mock_obj.verify_object_absent(obj_info["object_key"])


def test_erasure_fail_closed_on_head_500_error(store: SqliteEventStore, signing_key: str) -> None:
    mock_obj = MockObjectStore()
    mock_obj.head_should_raise = True  # S3 HEAD 500
    service = TraceService(store=store, object_store=mock_obj)

    obj_info = mock_obj.put_bytes(b"content 500", "text/plain", workspace_id="ws-1")
    atom_id = _ingest_atom(store, "ws-1", "content 500", object_key=obj_info["object_key"])

    with pytest.raises(InvariantViolation, match="compliance erasure failed"):
        service.erase_source(atom_id, SourceErasureRequest(actor="compliance-officer"))

    op = store.get_erasure_operation("ws-1", atom_id)
    assert op["state"] == "retryable_failure"


def test_release_activation_with_rollback_compensation(store: SqliteEventStore) -> None:
    mock_obj = MockObjectStore()
    lexical = MockRevisionedIndex("lexical")
    dense = MockRevisionedIndex("dense")
    retrieval = type("MockRetrieval", (), {"lexical_index": lexical, "dense_index": dense})()
    service = TraceService(store=store, object_store=mock_obj, retrieval_engine=retrieval)

    # Ingest baseline and register Release 1
    _ingest_atom(store, "ws-1", "baseline atom a")
    rel1 = store.create_cortex_release(
        workspace_id="ws-1",
        components=[
            {"component_kind": "lexical_index", "component_revision": "lex-v1"},
            {"component_kind": "dense_index", "component_revision": "dense-v1"},
        ],
        actor="tester",
    )
    store.validate_cortex_release(rel1["release_id"], {"passed": True}, actor="tester")
    service.activate_cortex_release(rel1["release_id"], CortexReleaseActivateRequest(actor="admin"))

    assert lexical.get_active_alias("lexical") == "lex-v1"
    assert dense.get_active_alias("dense") == "dense-v1"

    # Register Release 2, but simulate dense alias activation failure
    rel2 = store.create_cortex_release(
        workspace_id="ws-1",
        components=[
            {"component_kind": "lexical_index", "component_revision": "lex-v2"},
            {"component_kind": "dense_index", "component_revision": "dense-v2"},
        ],
        actor="tester",
    )
    store.validate_cortex_release(rel2["release_id"], {"passed": True}, actor="tester")

    dense.activate_should_raise = True

    with pytest.raises(InvariantViolation, match="external index alias promotion failed"):
        service.activate_cortex_release(rel2["release_id"], CortexReleaseActivateRequest(actor="admin"))


    # Verify compensation restored previous lexical alias to lex-v1
    assert lexical.get_active_alias("lexical") == "lex-v1"
    # Verify previous active release remains active in database
    active_rel = store.get_active_cortex_release("ws-1")
    assert active_rel["release_id"] == rel1["release_id"]
    # Candidate release failed
    rel2_status = store.get_cortex_release(rel2["release_id"])
    assert rel2_status["status"] == "failed"


