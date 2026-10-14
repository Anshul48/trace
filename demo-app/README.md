# TRACE freeze-38 browser demo

A working localhost demo of the **actual frozen** STACK-FORK candidate
(SOURCEFREEZE sha256 `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54`,
207 files — a content digest, not a git commit).

## Launch (one command)

```bash
cd demo-app
python3 run_demo.py --port 8765   # clean checkout: auto-creates .venv with numpy only if needed
# then open http://127.0.0.1:8765/ in a browser
```

`TRACE_FREEZE_SRC` defaults to `../freeze-src/cand`. At startup the backend
verifies the SOURCEFREEZE manifest sha256 equals the approved
`38c66bef…a43a0d54` **and** rehashes all 207 actual frozen source files
against that manifest; any missing or modified file refuses startup (before
any frozen code is imported). Supported platforms: Linux and macOS (verified
on Linux); the launcher resolves the Windows venv layout
(`.venv/Scripts/python.exe`) too, but Windows is not verified. numpy is
required because the frozen engine requires it; `run_demo.py` creates
`./.venv` and installs only numpy when the current interpreter lacks it.

## Scope honesty

- **Vector-probe mode, not text QA.** There is no text encoder in this demo and
  no mock encoder. Queries are the 120 actual 384-d cached encoder probe
  vectors from the qualification receipts (`data/probes.json`, copied verbatim).
- **Sample corpus.** The live index is those same 120 vectors grouped into
  12 leaves / 4 parents. Live recall numbers are against an exact cosine
  oracle *over the 120-vector sample only* — they are not the 10M numbers.
- **Full 10M record is separate.** `/api/evidence` serves the recorded VM
  receipt values (10,003,381 tokens, 13,081 docs, 63,441 atoms, guided
  recall@10 0.73 vs matched flat 0.056 all-sources; 0.476 vs 0.048
  leave-source-out; oracle `VERIFIED_PASS_READONLY_ORACLE_REPLAY`, 240 queries).
  These are harness recall / oracle agreement, not semantic IR quality or nDCG,
  and are never recomputed here. Each query also shows that probe's recorded
  10M row from `result.json`.
- Sample atom "text" is a labelled receipt-probe description; the original
  chunk text is not in the recovered receipts, so none is invented.

## Architecture

- `backend.py` — stdlib `http.server` only (plus numpy via the frozen code).
  Loads the frozen source from `TRACE_FREEZE_SRC` and calls, per query:
  - `HierQuery.guided` — frozen `fork/tl-sys/tlsys/query.py:1617`
  - `HierQuery.flat` — frozen `fork/tl-sys/tlsys/query.py:1764` (matched budget)
  - `tie_recall` — frozen `tools/product_pilot.py:449`
  - exact sample oracle `mat @ qvec`, mirroring `evaluate_facade`
    (`tools/product_pilot.py:500`)
  The only non-frozen piece is a small in-memory index/artifact wrapper whose
  `read_artifact` verifies sha256 digests, as the frozen query path expects.
- `static/` — semantic HTML/CSS/JS frontend: labelled controls, visible focus,
  keyboard-operable form, `prefers-reduced-motion` support, responsive layout.
  Views: query form, guided/flat results with receipt paths, evidence/provenance.
- `data/` — verbatim receipts: `probes.json`, `result.json`, `ORACLE.json`,
  `VM-10M-ACCEPTANCE.json`, `SOURCEFREEZE.json`.
- API: `GET /api/health`, `GET /api/probes`, `GET /api/evidence`,
  `POST /api/query` `{probe_id, top_k, mode, leave_source_out}`; JSON errors
  (400 bad input, 404 unknown path, 500 engine error — never fake results).

## Tests

```bash
.venv/bin/python -m unittest discover tests -v
```

Includes a backend-vs-frozen-function comparison (direct `HierQuery.guided`
call must match the API rows/work exactly), API tests, error cases, and
freeze-verification tests (all 207 actual files match; a single modified
source byte refuses startup).
Screenshots from the staging verification run are in `screenshots/`.
