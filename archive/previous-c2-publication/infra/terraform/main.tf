locals {
  name = "trace-${var.environment}"
  managed_data_plane = alltrue([
    var.managed_opensearch_endpoint != null,
    var.managed_qdrant_endpoint != null,
    var.managed_nats_endpoint != null,
  ])
  self_hosted_data_plane_ready = var.self_hosted_data_plane && alltrue([
    var.self_hosted_opensearch_endpoint != null,
    var.self_hosted_qdrant_endpoint != null,
    var.self_hosted_nats_endpoint != null,
  ])
  opensearch_endpoint = coalesce(var.managed_opensearch_endpoint, var.self_hosted_opensearch_endpoint)
  qdrant_endpoint     = coalesce(var.managed_qdrant_endpoint, var.self_hosted_qdrant_endpoint)
  nats_endpoint       = coalesce(var.managed_nats_endpoint, var.self_hosted_nats_endpoint)
}

resource "google_compute_network" "trace" {
  name                    = "${local.name}-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "trace" {
  name          = "${local.name}-subnet"
  region        = var.region
  network       = google_compute_network.trace.id
  ip_cidr_range = "10.42.0.0/20"
}

resource "google_compute_global_address" "private_services" {
  name          = "${local.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.trace.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.trace.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

resource "google_service_account" "runtime" {
  account_id   = "${local.name}-runtime"
  display_name = "Trace runtime service account"
}

resource "google_kms_key_ring" "trace" {
  name     = "${local.name}-keys"
  location = var.region
}

resource "google_kms_crypto_key" "trace" {
  name            = "workspace-data"
  key_ring        = google_kms_key_ring.trace.id
  rotation_period = "7776000s"
}

resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.trace.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket" "attachments" {
  name                        = "${var.project_id}-${local.name}-attachments"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
  encryption {
    default_kms_key_name = google_kms_crypto_key.trace.id
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "runtime" {
  bucket = google_storage_bucket.attachments.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_sql_database_instance" "trace" {
  name                = "${local.name}-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true
  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL"
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.trace.id
    }
    disk_autoresize = true
    disk_type       = "PD_SSD"
  }
  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "trace" {
  name     = "trace"
  instance = google_sql_database_instance.trace.name
}

resource "google_redis_instance" "trace" {
  name               = "${local.name}-redis"
  region             = var.region
  tier               = "STANDARD_HA"
  memory_size_gb     = 5
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.trace.id
}

resource "google_secret_manager_secret" "runtime" {
  secret_id = "${local.name}-runtime"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "runtime_postgres_dsn" {
  secret      = google_secret_manager_secret.runtime.id
  secret_data = var.runtime_postgres_dsn
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  secret_id = google_secret_manager_secret.runtime.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  template {
    service_account = google_service_account.runtime.email
    containers {
      image = var.api_image
      env {
        name  = "TRACE_DEPLOYMENT_PROFILE"
        value = "gcp_mumbai"
      }
      env {
        name  = "TRACE_GCP_REGION"
        value = var.region
      }
      env {
        name  = "TRACE_PRODUCTION_MODE"
        value = "true"
      }
      env {
        name  = "TRACE_AUTH_REQUIRED"
        value = "true"
      }
      env {
        name  = "TRACE_OBJECT_STORE"
        value = "gcs"
      }
      env {
        name  = "TRACE_REPOSITORY"
        value = "postgres"
      }
      env {
        name  = "TRACE_POSTGRES_RUNTIME_ROLE"
        value = var.postgres_runtime_role
      }
      env {
        name  = "TRACE_POSTGRES_MIGRATION_ROLE"
        value = var.postgres_migration_role
      }
      env {
        name  = "TRACE_POSTGRES_POOL_ENABLED"
        value = "true"
      }
      env {
        name  = "TRACE_GCS_BUCKET"
        value = google_storage_bucket.attachments.name
      }
      env {
        name  = "TRACE_WEBHOOK_KMS_KEY"
        value = google_kms_crypto_key.trace.id
      }
      env {
        name  = "TRACE_OPENSEARCH_URL"
        value = local.opensearch_endpoint
      }
      env {
        name  = "TRACE_OPENSEARCH_INDEX"
        value = var.opensearch_index
      }
      env {
        name  = "TRACE_QDRANT_URL"
        value = local.qdrant_endpoint
      }
      env {
        name  = "TRACE_QDRANT_COLLECTION"
        value = var.qdrant_collection
      }
      env {
        name  = "TRACE_NATS_URL"
        value = local.nats_endpoint
      }
      env {
        name  = "TRACE_REDIS_URL"
        value = "redis://${google_redis_instance.trace.host}:6379/0"
      }
      env {
        name  = "TRACE_MODEL_GATEWAY_URL"
        value = var.model_gateway_url
      }
      env {
        name = "TRACE_POSTGRES_DSN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.runtime.secret_id
            version = google_secret_manager_secret_version.runtime_postgres_dsn.version
          }
        }
      }
    }
    scaling {
      min_instance_count = 2
      max_instance_count = 30
    }
  }
}

resource "google_compute_instance_template" "workers" {
  name_prefix  = "${local.name}-workers-"
  machine_type = "e2-standard-4"
  region       = var.region
  disk {
    source_image = "projects/cos-cloud/global/images/family/cos-stable"
    boot         = true
    auto_delete  = true
  }
  network_interface {
    subnetwork = google_compute_subnetwork.trace.id
  }
  service_account {
    email  = google_service_account.runtime.email
    scopes = ["cloud-platform"]
  }
  metadata_startup_script = "#!/bin/sh\necho Trace worker image: ${var.worker_image}"
  lifecycle { create_before_destroy = true }
}

resource "google_compute_region_instance_group_manager" "workers" {
  name               = "${local.name}-workers"
  region             = var.region
  base_instance_name = "trace-worker"
  version { instance_template = google_compute_instance_template.workers.id }
  target_size = 3
}

resource "google_compute_instance_template" "data_plane" {
  count        = var.self_hosted_data_plane ? 1 : 0
  name_prefix  = "${local.name}-dataplane-"
  machine_type = "e2-standard-8"
  region       = var.region
  disk {
    source_image = "projects/cos-cloud/global/images/family/cos-stable"
    boot         = true
    auto_delete  = true
  }
  network_interface {
    subnetwork = google_compute_subnetwork.trace.id
  }
  metadata_startup_script = "#!/bin/sh\necho Run region-pinned OpenSearch, Qdrant, and NATS with three replicas."
  lifecycle { create_before_destroy = true }
}

resource "google_compute_region_instance_group_manager" "data_plane" {
  count              = var.self_hosted_data_plane ? 1 : 0
  name               = "${local.name}-data-plane"
  region             = var.region
  base_instance_name = "trace-data"
  version { instance_template = google_compute_instance_template.data_plane[0].id }
  target_size = 3
}

resource "terraform_data" "region_and_data_plane_gate" {
  input = var.region
  lifecycle {
    precondition {
      condition     = var.region == "asia-south1"
      error_message = "Refusing to provision Trace workspace data outside Mumbai."
    }
    precondition {
      condition     = local.managed_data_plane || local.self_hosted_data_plane_ready
      error_message = "Provide all Mumbai-pinned managed endpoints, or enable the three-node self-hosted data plane and provide all three private endpoints."
    }
  }
}
