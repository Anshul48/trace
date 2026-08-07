output "attachments_bucket" {
  value = google_storage_bucket.attachments.name
}
output "postgres_connection_name" {
  value = google_sql_database_instance.trace.connection_name
}
output "redis_host" {
  value = google_redis_instance.trace.host
}
output "api_uri" {
  value = google_cloud_run_v2_service.api.uri
}
