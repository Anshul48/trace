variable "project_id" {
  type = string
}
variable "region" {
  type    = string
  default = "asia-south1"
  validation {
    condition     = var.region == "asia-south1"
    error_message = "Trace gcp_mumbai deploys only to asia-south1."
  }
}
variable "environment" {
  type    = string
  default = "staging"
}
variable "api_image" {
  type = string
}
variable "worker_image" {
  type = string
}
variable "model_gateway_image" {
  type = string
}
variable "runtime_postgres_dsn" {
  description = "Runtime-role Cloud SQL DSN. Supply through a secret CI variable; Terraform stores only the Secret Manager version."
  type        = string
  sensitive   = true
}
variable "model_gateway_url" {
  description = "Private LiteLLM gateway base URL, including its /v1 path."
  type        = string
  sensitive   = true
}
variable "opensearch_index" {
  type    = string
  default = "trace-atoms-current"
}
variable "qdrant_collection" {
  type    = string
  default = "trace-vectors-current"
}
variable "postgres_runtime_role" {
  type    = string
  default = "trace_runtime"
}
variable "postgres_migration_role" {
  type    = string
  default = "trace_migrator"
}
variable "managed_opensearch_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
variable "managed_qdrant_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
variable "managed_nats_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
variable "self_hosted_data_plane" {
  type    = bool
  default = false
}
variable "self_hosted_opensearch_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
variable "self_hosted_qdrant_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
variable "self_hosted_nats_endpoint" {
  type      = string
  default   = null
  sensitive = true
}
