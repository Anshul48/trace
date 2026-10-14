# TL2 command log

## Preflight

- Read the required bootstrap and TL2 prompt in the user-specified order.
- Read the shared launch protocol, governing program documents, P-002 decision,
  TL2 packet, L1 handoff, and control-plane snapshot.
- Reconciled canonical Trace-Lite checkout, expired L1 worktree, Git worktrees,
  control-plane tree, runtime versions, dependency locks, and target path.
- No mutation, provider, network, or external data acquisition was used during
  preflight.
- Created fresh exclusive worktree `C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-lite-tl2`
  on branch `feat/s2-tl2-bounded-graph` at `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d`;
  post-create status was clean.

## Mutation and verification

All product commands below ran in the fresh TL2 worktree with Python 3.12.0,
uv 0.12.2, network/providers disabled, and test databases confined to the
packet preflight scratch root. Exit status was 0 for every command listed.

| Check | Exact command | Result / duration | Evidence |
| --- | --- | --- | --- |
| Compile | `uv run --project . --extra dev python -m compileall -q src` | pass; duration not separately captured | committed source tree |
| Graph regression | `uv run --project . --extra dev pytest -q tests/test_graph.py` | 6 passed | test output; committed test |
| TL2 contract | `uv run --project . --extra dev pytest -q tests/test_tl2_bounded_graph.py` | 6 passed | test output; committed test |
| Lifecycle | `uv run --project . --extra dev pytest -q tests/test_cortex_lifecycle.py tests/test_lifecycle.py` | 15 passed | test output |
| Engine compatibility | `uv run --project . --extra dev pytest -q tests/test_engines.py` | 7 passed | test output |
| Final focused set | `uv run --project . --extra dev pytest -q tests/test_graph.py tests/test_tl2_bounded_graph.py tests/test_cortex_lifecycle.py tests/test_lifecycle.py tests/test_engines.py` | 27 passed in 8.73s | test output |
| Full suite | `uv run --project . --extra dev pytest -q --basetemp "$env:TEMP\\trace-s2-tl2-full-final-2"` | 159 passed, 1 warning in 87.10s | test output; warning is the known FastAPI/Starlette httpx deprecation |
| Adversarial measurement | `uv run --project . --extra dev python scripts/measure_tl2_bounded_graph.py --output "$env:TEMP\\trace-s2-tl2-100k-receipt-final-v2.json"` | pass; build 4,490.487ms | `evidence/measurement-receipt.md`; raw receipt SHA-256 `c4f99b0ef4fae3a4de8990632fb8ae7fad9d42701df71c012215f83ecf012fb3` |
| Patch hygiene | `git diff --check` | pass; only LF-to-CRLF normalization warnings | TL2 worktree |

The measurement fixture is deterministic and generated locally: 100,000 atoms,
one df=100,000 boilerplate term, and one df=100 bounded group. It measured
202,548 bounded edges, max soft degree 50, serialized projection estimate
58,838,370 bytes, complete-query receipt 1.683ms, and an explicit structural
overflow receipt with status `bounded_incomplete`; no fallback traversal ran.

## Final identities

- Base commit: `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d`
- Head commit: `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c`
- P-002 decision SHA-256: `ed4e8bb93e614169279f568eab5690280168de7b4339dc21f7638cc2acc8a129`
- Graph policy SHA-256: `5cb3ac89fefa03f6e3c015aa76b14cd4f60457b2a5f82b89cd9d032cd41fc4c1`
- Default configuration fingerprint: `43b640943d1fb3ce1e7042b53ce6ce6a590a979190a212e4304c69222f5ac1c2`
- Control-plane drift: snapshot whole-tree hash did not match the live tree because ten packet-local files were created after the lock timestamp; core decision/risk/registry identities matched and no global control-plane document was edited.
