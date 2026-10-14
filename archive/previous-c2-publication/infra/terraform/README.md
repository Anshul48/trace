# Trace GCP Mumbai profile

This Terraform profile is intentionally region-pinned to `asia-south1`. It
creates CMEK/versioned attachment storage, Cloud SQL with HA backups,
Memorystore, a private Cloud Run API, and managed instance groups for workers
and the fallback three-node data plane. Supply region-pinned managed
OpenSearch/Qdrant/NATS endpoints together, or set `self_hosted_data_plane=true`.

It refuses a non-Mumbai region and refuses a partial data-plane configuration.
Supply a runtime-role Cloud SQL DSN through `runtime_postgres_dsn`, a private
LiteLLM `/v1` endpoint through `model_gateway_url`, and either all three
managed data-plane endpoints or all three self-hosted private endpoints. The
Cloud Run API receives no provider key; only the private model-gateway service
does. The profile injects forced-RLS/runtime-role, GCS/CMEK, Redis, revisioned
OpenSearch/Qdrant, NATS, and webhook-KMS settings required by the application.

Run migration and release-gate jobs separately; `terraform apply` alone is not
approval to serve production workspaces.
