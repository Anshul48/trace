# R1 Evidence Index

| Artifact | Purpose | Claim boundary |
| --- | --- | --- |
| `source-identity-manifest.json` | Live Trace, Trace-Lite, trace-bench, implementation-worktree, and D2a external-root identities | C0 identity observation |
| `status-board.md` | Exact next packets, hard dependencies, claim levels, and safe defaults | C0 control-plane state |
| `risk-state.md` | R1 risk and deferred-decision reconciliation | C0 risk state |
| `downstream-packet-classification.md` | Content-based classification of existing packet directories | C0 packet audit |
| `checksums.json` | Final hashes for R1 artifacts and changed control-plane records | Integrity metadata |
| `verification.md` | Packet-local structural and scope checks | C0 self-check only |

No runtime test result, benchmark score, provider result, database receipt, or
independent verifier receipt is stored in this packet. Raw data remains at the
external D2a root and is not copied into the control plane.
