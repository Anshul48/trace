"""Focused maintained tests: ingest shaping (chunking + op shape).

Pure-python; runs on any interpreter. Commit-path behavior is covered
by integration tests under the tl-sys venv (forthcoming).
Run: python3 tl-sys/tests/test_ingest_units.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.ingest import atom_op, chunk_text, holon_op

try:
    import blake3  # noqa: F401
    HAVE_BLAKE3 = True
except ImportError:
    HAVE_BLAKE3 = False

FAILS = []
BLOCKED = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def stub_prep(body, store_id):
    return {"artifact_id": f"ART-{len(body)}", "store_id": store_id,
            "extent": "whole-immutable-file", "length": len(body),
            "digest": "sha256:stub"}


# chunking: 200-token windows, 50 overlap ------------------------------
text = " ".join(f"w{i}" for i in range(500))
chs = chunk_text(text)
check("chunk-count", len(chs) == 3, f"{len(chs)}")
c0, c1, ct, b0, b1 = chs[0]
check("chunk-span-text", text[c0:c1] == ct and len(ct.split()) == 200,
      f"{len(ct.split())}")
check("chunk-overlap", chs[1][2].split()[:50] == ct.split()[-50:],
      "no 50-token overlap")
check("chunk-empty", chunk_text("   \n  ") == [], "empty text")
raw = text.encode("utf-8")
check("chunk-byte-span",
      all(raw[b0] and raw[b0:b1].decode("utf-8") == ct
          for (_c0, _c1, ct, b0, b1) in chs)
      and all(0 <= b0 < b1 <= len(raw)
              for (_c0, _c1, _ct, b0, b1) in chs),
      "byte span must slice the exact source bytes")
# non-ASCII: byte offsets diverge from char offsets; chunk text stays
# the verbatim source slice, boundaries stay code-point aligned.
uni = "naïve café " + " ".join(f"w{i} ünïcodé" for i in range(300))
uchs = chunk_text(uni)
uraw = uni.encode("utf-8")
check("chunk-utf8-verbatim",
      len(uchs) >= 1 and all(
          uraw[b0:b1].decode("utf-8") == ct == uni[c0:c1]
          and 0 <= b0 < b1 <= len(uraw)
          for (c0, c1, ct, b0, b1) in uchs)
      and any(b1 - b0 != c1 - c0 for (c0, c1, _t, b0, b1) in uchs),
      "non-ASCII must exercise byte!=char offsets")

# atom op: deterministic op_id, dual artifacts, non-consequential -----
if not HAVE_BLAKE3:
    BLOCKED.append("atom-op-shape (needs blake3; run under tl-sys/.venv)")
    print("RESULT: BLOCKED (no blake3) " + str(BLOCKED))
    sys.exit(2)
REV = "0193f4b2-7c1a-7e11-9a2b-3c4d5e6f7890"
op = atom_op("d1", 0, 1, (0, 5, 0, 5), b"hello", [0.1, 0.2], "s1",
             stub_prep, REV)
check("atom-kind", op["kind"] == "ACCEPT_ATOMS", op["kind"])
check("atom-opid-uuidv7",
      len(op["op_id"]) == 36 and op["op_id"][14] == "7"
      and op["op_id"] != atom_op("d1", 0, 1, (0, 5, 0, 5), b"hello",
                                 [0.1, 0.2], "s1",
                                 stub_prep, REV)["op_id"], op["op_id"])
from tlsys.identity import ATOMIZER_CONFIG, atom_id
REV2 = "0193f4b2-7c1a-7e11-9a2b-3c4d5e6f7891"
check("atom-v2-deterministic",
      op["payload"]["atom"]
      == atom_id(b"hello", "d1", (0, 5), REV) == atom_op(
          "d1", 0, 1, (0, 5, 0, 5), b"hello", [0.1, 0.2], "s1",
          stub_prep, REV)["payload"]["atom"],
      "identical bound inputs must reproduce the atom")
check("atom-v2-revision-sensitive",
      atom_id(b"hello", "d1", (0, 5), REV)
      != atom_id(b"hello", "d1", (0, 5), REV2),
      "revision must bind the id")
check("atom-v2-config-sensitive",
      atom_id(b"hello", "d1", (0, 5), REV)
      != atom_id(b"hello", "d1", (0, 5), REV, "other-config"),
      "atomizer config must bind the id")
check("atom-v2-config-default",
      ATOMIZER_CONFIG == "tlsys-chunk-c200-o50-v1", ATOMIZER_CONFIG)
check("atom-dual-artifacts", len(op["artifacts"]) == 2,
      f"{len(op['artifacts'])}")
check("atom-no-approval", op["approval_ref"] is None
      and "retires" not in op["payload"], f"{op['payload']}")

# holon op -------------------------------------------------------------
hop = holon_op("d1", ["a1", "a2"], [0.5], "s1", stub_prep)
check("holon-opid-uuidv7",
      len(hop["op_id"]) == 36 and hop["op_id"][14] == "7",
      hop["op_id"])
check("holon-meta-artifact", len(hop["artifacts"]) == 1
      and hop["payload"]["holon"] == "d1", f"{hop['payload']}")

print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
sys.exit(1 if FAILS else 0)
