# SPDX-License-Identifier: Apache-2.0
"""Validate staged receipt JSONs and the recorded gate values quoted in docs.

Run from the repo root:  python3 tools/check_receipts.py
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "receipts")
errors = []


def load(name):
    p = os.path.join(R, name)
    if not os.path.isfile(p):
        errors.append("missing receipts/" + name)
        return {}
    try:
        return json.load(open(p))
    except Exception as exc:  # pragma: no cover
        errors.append(f"receipts/{name}: {exc}")
        return {}


def expect(cond, msg):
    if not cond:
        errors.append(msg)


result = load("result.json")
accept = load("VM-10M-ACCEPTANCE.json")
audit = load("AUDIT-RESULT.json")
pin = load("source-pin.json")
caps = load("cap-derivation.json")

inp = result.get("input", {})
expect(inp.get("actual_tokens") == 10003381, "result input.actual_tokens != 10003381")
expect(inp.get("complete_documents") == 13081, "result complete_documents != 13081")
expect(inp.get("atoms") == 63441, "result atoms != 63441")
expect(inp.get("cache_misses") == 0, "result cache_misses != 0")
expect(result.get("final", {}).get("pending_documents") == 0, "final pending_documents != 0")
expect(result.get("repair_to_zero", {}).get("final_debt") == 0, "repair final_debt != 0")

summary = result.get("evaluation", {}).get("summary", {})
for mode in ("all_sources", "leave_source_out"):
    m = summary.get(mode)
    expect(isinstance(m, dict), f"evaluation.summary missing {mode}")
    if isinstance(m, dict):
        expect(m.get("probes") == 120, f"{mode} probes != 120")
        expect(
            m.get("mean_guided_scoring_rows") == m.get("mean_flat_scoring_rows"),
            f"{mode} guided/flat scoring rows not matched",
        )
        expect(m.get("matched_work_queries") == 120, f"{mode} matched_work_queries != 120")

expect(accept.get("status") == "PASS", "VM-10M-ACCEPTANCE status != PASS")
expect(accept.get("manifest_match") is True, "acceptance manifest_match != true")
expect(audit.get("status") == "VERIFIED_VM_10M_RECEIPT", "AUDIT-RESULT status unexpected")
expect(pin.get("frozen_ok") is True and pin.get("frozen_files") == 207, "source-pin frozen check failed")
expect(caps.get("outputs", {}).get("max_delta_entries") == 669436, "cap derivation max_delta_entries != 669436")

freeze = os.path.join(ROOT, "freeze-src", "cand", "SOURCEFREEZE.json")
digest = hashlib.sha256(open(freeze, "rb").read()).hexdigest()
expect(
    digest == "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54",
    "SOURCEFREEZE.json sha256 mismatch: " + digest,
)

before = os.path.join(R, "manifest-before.json")
after = os.path.join(R, "manifest-after.json")
if os.path.isfile(before) and os.path.isfile(after):
    expect(open(before, "rb").read() == open(after, "rb").read(), "manifest before != after")

if errors:
    print("RECEIPT CHECKS FAILED")
    for err in errors:
        print(" -", err)
    sys.exit(1)
print("receipts ok: gates, both probe modes, matched work, caps, freeze digest")
