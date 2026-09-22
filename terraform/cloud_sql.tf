resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "google_sql_database_instance" "ecom_instance" {
  project             = var.project_id
  name                = var.database_instance_name
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.database_tier
    availability_type = "ZONAL"
    disk_autoresize   = true
    disk_size         = 10
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
      # No authorized_networks: the only supported access path is the
      # Cloud SQL Auth Proxy used automatically by Cloud Run's Cloud SQL
      # connection integration (IAM-authenticated, no public TCP ACL needed).
    }

    maintenance_window {
      day          = 7
      hour         = 3
      update_track = "stable"
    }

    user_labels = local.labels
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "ecom_database" {
  project  = var.project_id
  name     = var.database_name
  instance = google_sql_database_instance.ecom_instance.name
}

resource "google_sql_user" "ecom_user" {
  project  = var.project_id
  name     = var.database_user
  instance = google_sql_database_instance.ecom_instance.name
  password = random_password.db_password.result
}
