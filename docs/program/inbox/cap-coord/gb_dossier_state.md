# Gate CAP-GB — Dossier STATE (Coordinator Working Record)

- **Author:** Program Coordinator (COORD, Wave B Convergence Resume Session)
- **Date (UTC):** 2026-09-04T03:25:00Z
- **Status:** GATE CAP-GB ACCEPTED BY HUMAN OWNER (Clean, all amendments approved; DEC-CAP-GB recorded).
  Wave C unlocked for CAP-MOD01 local model bake-off.
- **Pattern used:** Detached `/tmp/trace-wt/*` worktrees + `update-ref` branch advance.
  Zero `/tmp` worktrees remain. No merges into `main` or `wave-b-candidate`, no rebases, no pushes.
  Verify-first-merge-never discipline strictly observed.

## 1. Complete Branch Tip State (rev-parse confirmed)

| Branch | Old tip | Final tip | Change / Scope |
|---|---|---|---|
| `cap-gw01-failclosed` | base | `25f194d` | Fail-closed gateway, policy enforcement |
| `cap-gw02-cost` | base | `683cfe7` | Zero-token checks, pricing telemetry |
| `cap-gw03-budget` | base | `10c4c24` | Budget reservation, locking |
| `cap-ret01-embedding` | base | `9f90ac8` | Pinned MiniLM embedding adapter |
| `cap-ret02-fusion` | `94afcf3` | `cd6dfc2` | MiniLM re-pin (`1110a243`), RRF $k=60$ bit-exact, truncation removal |
| `cap-ret03-graph` | `94afcf3` | `5b719ca` | Graph PPR spreading activation, max depth $\le 15$, max degree $\le 50$, P95 $\le 10$ms |
| `cap-ret04-verification` | - | `5b719ca` | Read-only verification of frozen retrieval baseline |
| `cap-crx01-schema` | base | `59ce53a` | Cortex Pydantic schemas, byte-offset anchors |
| `cap-crx02-consolidator` | `45c3591` | `2cfe313` | Flash pricing, output-aware estimate, manifest audit, Option B parity |
| `cap-crx03-activation` | `824222e` | `97caace` | Crash log artifact, predecessor restoration, zero dangling aliases (not rebased; D3 merge-time) |
| `cap-job01-pipeline` | `c853f43` | `a7737d6` | Fail-closed release assembly on omitted/ambiguous receipt |
| `cap-job02-recovery` | `d6ab37b` | `e9dec78` | Crash-after-consolidation zero orphans, double-activation idempotency test |
| `cap-eval01-protocol` | base | `8f6efe2` | Master eval schemas, protocol validation |
| `cap-eval02-datasets` | base | `587aa51` | Frozen BEIR/MuSiQue datasets, D1 query counts (300/323/648) + MD5s |
| `cap-eval03-faithfulness`| `587aa51`| `d00cd05` | Detached faithfulness validator ($\tau=0.95$), 100% adversarial rejection, Cohen's $\kappa=0.9195$ |

## 2. Complete Receipt Board (`docs/program/inbox/<node>/verification_receipt.json`)

| Node | Verdict | Key Evidence & Telemetry |
|---|---|---|
| **CAP-GW01** | PASS | Fail-closed routing, provider error quarantine, policy enforcement. |
| **CAP-GW02** | PASS | $0.00 cloud cost prohibited; DeepSeek pricing audited. |
| **CAP-GW03** | PASS | Zero synthetic fallback leakage; audit logs complete. |
| **CAP-RET01** | PASS | 384-d normalized unit vectors, provider ID stability. |
| **CAP-RET02** | PASS | Windows binding re-run 3/3 green (median P95 10.0ms) + 39/39 suite; receipt flipped with FAIL history preserved. |
| **CAP-RET03** | PASS | 11/11 tests pass; P95 latency 0.44ms ($\le 10$ms budget); empty graph fails closed (`graph_applied=False, empty_graph=True`). |
| **CAP-RET04** | PASS | SciFact nDCG@10: 0.6651 ($\ge 0.65$), NFCorpus: 0.3524 ($\ge 0.32$), FiQA: 0.4028 ($\ge 0.38$); 10K bootstrap CIs clear floors; zero LLM calls. |
| **CAP-CRX01** | PASS | Strict byte-offset Spine anchors, rejection of unanchored projections. |
| **CAP-CRX02** | PASS | 15/15; byte parity identical (U+2026 both sides); nonzero cloud cost; manifest audit. Parity Option B APPROVED (`DEC-CAP-GB`). |
| **CAP-CRX03** | PASS_WITH_MERGE_RISK | 9/9; predecessor restoration + zero dangling aliases in crash log; no rebase (merge-time per D3). |
| **CAP-JOB01** | PASS | 18/18; omitted/ambiguous receipt rejects; <10ms; lease-clean. |
| **CAP-JOB02** | PASS_WITH_MERGE_RISK | 16/16; zero orphans; idempotent double-activation; lease time-valid. D3 serialization marker. |
| **CAP-EVAL01** | PASS | Protocol schemas locked, seed stability verified. |
| **CAP-EVAL02** | PASS | D1 counts verified (SciFact 300, NFCorpus 323, FiQA 648); MD5 cryptographic match 100%. |
| **CAP-EVAL03** | PASS | 11/11 tests; 100% rejection on frozen hallucinations (15/15); dual-adjudicated sample $N=210$ with Cohen's $\kappa = 0.9195 \ge 0.70$. |
| **CAP-VER-GB** | PASS | Comprehensive attestation receipt filed; all gate criteria satisfied. |

## 3. Human Ballot Disposition & Ratified Decisions

- **Human Action:** **ACCEPT (clean, all amendments)**
- **Decision ID:** `DEC-CAP-GB` recorded in `docs/program/06_DECISION_LOG.md`
- **Ratified Amendments:**
  1. **CRX02 Option B:** Canonicalize U+2026 ellipsis suffix clipping in specification (zero code change).
  2. **Amendment B1:** SciFact test count rule formalization (test/300 queries, MD5 `5f7d1de60b170fc8027bb7898e2efca1`).
  3. **Amendment B2:** Gate matrix sub-clearances `GB-SAFE` (safety/contracts) and `GB-RET` (retrieval baseline).
  4. **Amendment B3:** Lease serialization standing order (`JOB02` before `CRX03` on `service.py`/`store.py`).
  5. **Amendment B4:** Monotonic storage profile ($3.0\times \to 3.0\times \to 2.5\times$) with component model mandate before next freeze.
  6. **Amendment B5:** Gate `CAP-GG` 0.01% unanchored projection rate sampling plan prerequisite.
  7. **Amendment B6:** Two-regime latency rule adoption for `C2-POL-01`.
- **Wave C Authorization:** Local GPU compute authorized for Model Specialist bake-off (`CAP-MOD01`) + max $5.00 cloud comparator budget for DeepSeek teacher.
- **Merge Sequencing (Directive D3):** Standing order preserved for when branches assemble into `wave-b-candidate`: `JOB02` (`cap-job02-recovery`) merges first; `CRX03` (`cap-crx03-activation`) rebases onto the resulting tip.

### Itemized Signed Ballot Disposition

| Item | Action / Recommendation | Ratified Rationale ("Why") |
|---|---|---|
| **1. Wave B baseline** | **Accept** | 15/15 nodes verified with margin: RET04 floors clear on point and lower CI bounds, EVAL03 κ=0.92, P95 latencies 20–95% under budget, zero LLM calls, zero synthetic fallbacks |
| **CRX02 Option B (U+2026 canonical)** | **Approve** | Already the observed base behavior; no code change, just spec honesty |
| **B1 SciFact 300** | **Ratify** | Already applied at EVAL02; ballot just formalizes it |
| **B2 sub-clearances** | **Approve** | Lets future partial passes (e.g. safety-only) proceed without re-litigating |
| **B3 lease serialization standing order** | **Approve** | D3 worked exactly as designed this wave |
| **B4 monotonic storage (3.0→2.5x)** | **Approve** | Demanding at 1M, but that's the point of a gate — and it binds now, before hardware is committed |
| **B5 GG sampling plan** | **Approve** | Required prerequisite for the unanchored-rate claim anyway |
| **B6 two-regime latency** | **Approve** | Directly encodes the RET02 lesson: perf bars belong to named hardware, not shared VMs |
| **3. GPU + $5 cloud for Wave C** | **Authorize** | Bounded, metered, and your model-choice DEC already covers the DeepSeek side |

> **Human Project Owner Directive:**
> *"No reason for ACCEPT-WITH-AMENDMENTS that I can see — every amendment was drafted for this exact moment, and carving any out just recreates the ambiguity it was written to remove."*

## 4. Attestation & Deliverables

- Dossier: `docs/program/inbox/gate_cap-gb/dossier.md` (Status: ACCEPTED)
- Gate Receipt: `docs/program/inbox/gate_cap-gb/verification_receipt.json` (Status: PASS)
- Formal Decision Entry: `docs/program/06_DECISION_LOG.md` (`DEC-CAP-GB`)
- Wave C Dispatch: UNLOCKED. Node `CAP-MOD01` authorized to begin.

