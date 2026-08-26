# Foundation Capability Matrix: <release-id>

> **State:** draft | proposed | human-reviewed
>
> Each row describes a bounded capability. Supported requires linked
> independent evidence; it never means future scale or SOTA.

| Capability | Component | Supported state | Evidence/verifier | Preconditions | Explicit exclusions | Claim boundary |
| --- | --- | --- | --- | --- | --- | --- |
| Source ingestion/replay | TL / Trace | planned | <...> | <...> | <...> | <...> |
| Candidate/active isolation | TL / Trace | planned | <...> | <...> | <...> | <...> |
| Fail-closed runner | trace-bench | planned | <...> | <...> | <...> | <...> |
| Real-data evaluation | trace-bench | blocked | P-001 | admitted data | no SOTA/scale claim | <...> |
| Temporal/as-of | Trace | observed | <...> | <...> | valid-time/revocation pending | <...> |
| 100K real corpus | all | not started | <...> | P-005 | 1M/distributed excluded | <...> |
| Consumer shadowing | Reflex/Entorhinal | blocked | <...> | conformance + gates | no canonical authority | <...> |

## Unsupported / intentionally excluded

- <list items>.

## Non-certifying evidence retained

- <internal fixture/mock/synthetic fault test with reason>.
