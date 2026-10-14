# Packet Amendment: <packet-id> / <yyyymmdd>-<sequence>

> **Original packet:** <relative path and SHA-256>
>
> **State:** proposed | accepted | rejected
>
> **Authority:** coordinator plus human decision if scope/authority changes.

## Change requested

- Requested by: <...>.
- Date: <UTC>.
- Why original packet is insufficient: <evidence-based reason>.
- Environment/input change: <...>.

## Exact delta

| Field | Original | Proposed amendment | Effect |
| --- | --- | --- | --- |
| Base/identity | <...> | <...> | <...> |
| Allowed paths | <...> | <...> | <...> |
| Authority | <...> | <...> | <...> |
| Acceptance/verification | <...> | <...> | <...> |
| Deadline/lease | <...> | <...> | <...> |

## Safety review

- Does it add destructive operation? <yes/no>.
- Does it change evaluator/data/threshold after results? <yes/no>.
- Does it weaken provenance, candidate isolation, policy, or rollback? <yes/no>.
- New decision/risk required: <...>.

## Approval

<accepted/rejected and approving identity>.

Original packet remains intact. Workers read original plus every accepted
amendment chronologically.
