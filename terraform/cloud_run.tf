resource "google_cloud_run_v2_service" "ecom_web" {
  project  = var.project_id
  name     = var.cloud_run_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run_sa.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    containers {
      image = var.cloud_run_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
        cpu_idle = true
      }

      env {
        name  = "FLASK_ENV"
        value = "production"
      }
      env {
        name  = "BASE_URL"
        value = var.base_url
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "INSTANCE_CONNECTION_NAME"
        value = google_sql_database_instance.ecom_instance.connection_name
      }
      env {
        name  = "DB_NAME"
        value = var.database_name
      }
      env {
        name  = "DB_USER"
        value = var.database_user
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCS_ENABLED"
        value = "true"
      }
      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.product_images.name
      }
      env {
        name  = "RAZORPAY_CURRENCY"
        value = "INR"
      }

      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["ecom-db-password"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["ecom-flask-secret-key"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "RAZORPAY_KEY_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["ecom-razorpay-key-id"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "RAZORPAY_KEY_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["ecom-razorpay-key-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "RAZORPAY_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["ecom-razorpay-webhook-secret"].secret_id
            version = "latest"
          }
        }
      }

      # Only present when google_oauth_client_id was set — the app treats
      # "both env vars unset" as "Google login disabled", so we simply don't
      # wire these up at all rather than shipping empty/placeholder secrets.
      dynamic "env" {
        for_each = var.google_oauth_client_id != "" ? {
          GOOGLE_OAUTH_CLIENT_ID     = "ecom-google-oauth-client-id"
          GOOGLE_OAUTH_CLIENT_SECRET = "ecom-google-oauth-client-secret"
        } : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.secrets[env.value].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds = 30
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.ecom_instance.connection_name]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.secret_versions,
  ]
}
