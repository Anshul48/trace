# S4 D2b bounded reconciliation note

## Scope

This is a read/reconciliation pass over the existing D2b candidate. It does
not overwrite the candidate, mutate raw data, call a provider, download data,
or change product/control-plane code. The existing owner-side PASS is treated
as evidence to recheck, not as independent acceptance.

## Fresh preflight

- UTC start: `2026-08-20T03:58:01.5664781Z`.
- Protected Trace checkout: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`,
  branch `main`, HEAD
  `c855bb06532b3b52b25f0bea969d2677e5049065`; dirty user snapshot preserved.
- D2b lease: `lease-s4-d2b-normalization-20260819`, SHA-256
  `508685c032b5b57eed7fcc976d2869a9cad31eb571075cc587737fa4d1ad3a43`,
  valid through `2026-08-20T12:40:55.1070524Z`, verifier
  `d2b-manifest-verifier-20260819`.
- Shared bootstrap SHA-256:
  `521c09d41efc81c72dfd54e2d509b7cb41d352ecf1d3795977cee0c919590a93`.
- Session prompt SHA-256:
  `c18f3f31eb501ddaf15fa7b0fa6f57b208462ae2e7e731408eeb593acbf15e91`.
- B1.1 handoff SHA-256:
  `abbee58abe0c700fa2dcb18c597dffeb721c601d1cf53aea268055dd3d7065b7`.
- B1.1 successor: `dcd32396f6430e6865176f053a3ce57112db6df3`; schema SHA-256:
  `a08918851cdeb32badbc2e732608d61763c3befd303291724fa86064218ae831`.
- D2a portfolio manifest SHA-256:
  `4e594992929c233ec4c95ad0541c09ae54a4e4e0b2d34c48d5ca910dcb0d41c5`.
- Raw root: `C:\Users\anshu\AppData\Local\trace-bench-data`; seven admitted
  roots present, 85 files, 1,523,873,466 bytes by the pinned inventory.
- Candidate root already exists at
  `C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819`;
  it is not overwritten. Prior replay and retained failures are also present
  under the leased verifier-scratch root.
- New reconciliation replay target checked absent before testing:
  `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\independent-replay-20260820`.

## Bounded actions

1. Recheck the pinned B1.1/D2a identities, output markers, and candidate
   self-excluded checksum inventory.
2. Run the packet normalizer once with the fixed timestamp into the new
   verifier-scratch replay target, with network/provider use disabled by scope.
3. Independently compare replay and candidate checksums/markers/manifests and
   inspect mapping-chain, namespace, atom-deferral, dataset-status, exclusion,
   and BigANN operations-only invariants without changing implementation.
4. Record any mismatch as blocked/failed; do not repair the candidate in this
   reconciliation pass.

## Stop conditions

Stop on raw drift, output collision, missing B1.1 schema, unadmitted input,
network/provider activity, checksum mismatch, malformed mapping chain, or an
attempt to write outside the lease and packet-local evidence directory.
