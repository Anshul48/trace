# Trace production runbook

The deployment profiles are fixed: `self_hosted` and `gcp_mumbai`. A workspace
must exist entirely in one profile/location. Move it only by an offline export
of canonical events and attachments, then import and rebuild projections; do
not configure live cross-cloud reads.

## Self-hosted admission

Run `uv run python main.py preflight --data-path <data-volume>` before setting
`TRACE_PRODUCTION_MODE=true`. It rejects missing backup/replication targets,
less than the configured RAM/free-disk threshold, and an explicitly required
GPU. The default 64 GiB RAM and 500 GiB free-disk thresholds are admission
checks, not capacity proof.

For production set a non-owner PostgreSQL runtime role, a distinct migration
role, `TRACE_POSTGRES_POOL_ENABLED=true`, `TRACE_WEBHOOK_KMS_KEY`, private
object storage, both revisioned indexes, NATS, Redis, and the private model
gateway. Run migrations with the migration DSN, not the runtime DSN.

## Staged deployment

1. Run migrations and verify the runtime role has neither `SUPERUSER` nor
   `BYPASSRLS`.
2. Backfill an immutable lexical/vector revision for one workspace. Check
   parity before activating aliases; retain the prior revision for rollback.
3. Run the 100K baseline, then the 1M-atom production gate. Use
   `benchmarks/load/trace-v2.js` for the 70/20/5/5 non-deep mix and record
   queue age, index lag, graph degree, model cost, and stale-projection count.
4. Restore a backup into an isolated environment, replay/rebuild projections,
   kill workers during an index build, and record RPO/RTO/parity evidence.
5. Shadow retrieval, then enable per workspace at 5%, 25%, 50%, and 100%.
   Roll back automatically on a tenant leak, citation/freshness regression, or
   latency-gate failure.

Evaluate recorded evidence with:

```powershell
uv run python main.py release-gate benchmarks/release-evidence.template.json
```

The checked-in template is intentionally failing evidence. Replace it with
measured, reviewed results; a passing file is necessary but does not replace
operator approval.

The 10M-atom / 500-QPS target is deliberately not implied by this pilot. It
requires a separate scale-release program and a fresh measured baseline.
