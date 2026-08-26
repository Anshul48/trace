# Independent Verification Report: <packet-id>

> **Verifier packet:** <V0 / V1a / V1b>
>
> **State:** planned | executed | blocked | repair-requested | accepted
>
> **Independence:** verifier worktree <path>; base <commit>; implementer
> worktree <different path>.

## 1. Scope and claim under test

- Candidate/implementation packet: <...>.
- Exact claim(s): <...>.
- Out of scope: <...>.
- Fixed input manifest: <path and SHA-256>.
- Relevant decisions/risks: <...>.

## 2. Environment and source identity

| Item | Value | Evidence |
| --- | --- | --- |
| Component root | <...> | <repository-state.json> |
| Implementation commit | <...> | <...> |
| Verifier worktree clean | <yes/no> | <command output> |
| Migration/index/runtime versions | <...> | <...> |
| Dataset/evaluator manifest | <...> | <...> |

## 3. Test matrix

| Case ID | Precondition/fault | Expected behavior | Command/fixture | Result | Evidence |
| --- | --- | --- | --- | --- | --- |
| <...> | <...> | <...> | <...> | pass/fail/blocked | <...> |

Select case families based on packet:

- evaluator: missing data, invalid checksum, mock/synthetic/flat fallback,
  stage error, empty result, TLS error, missing judgment;
- lifecycle: candidate write, partial build, validation failure, policy change,
  external activation failure, restart/retry, pointer rollback;
- temporal: as_of_event, valid-time interval, late correction, supersession,
  revoked/tombstoned/denied historical source.

## 4. Evidence observations

- Active/candidate/release IDs before/after: <...>.
- Source/projection hashes before/after: <...>.
- Sample evidence bundle/release receipt: <...>.
- Error receipts or fault logs: <...>.
- Unsupported infrastructure conditions: <...>.

## 5. Outcome

**Disposition:** accept for named evidence | repair requested | reject | defer.

**What is verified:** <...>.

**What remains observed or untested:** <...>.

**Claim boundary:** <no claim beyond exact cases/environment>.

## 6. Follow-up

- Required repair packet or human decision: <...>.
- Risk updates: <...>.
- Re-verification command set: <...>.
