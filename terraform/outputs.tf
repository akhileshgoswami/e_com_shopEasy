output "cloud_run_url" {
  description = "Public URL of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.ecom_web.uri
}

output "cloud_run_service_name" {
  value = google_cloud_run_v2_service.ecom_web.name
}

output "artifact_registry_repo_url" {
  description = "Docker repository URL to push images to (used by scripts/deploy.sh)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ecom_repo.repository_id}"
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name (PROJECT:REGION:INSTANCE)."
  value       = google_sql_database_instance.ecom_instance.connection_name
}

output "cloud_sql_instance_name" {
  value = google_sql_database_instance.ecom_instance.name
}

output "gcs_bucket_name" {
  value = google_storage_bucket.product_images.name
}

output "cloud_run_service_account_email" {
  value = google_service_account.cloud_run_sa.email
}

output "database_password_secret_name" {
  description = "Secret Manager secret holding the generated database password. Fetch with: gcloud secrets versions access latest --secret=ecom-db-password"
  value       = google_secret_manager_secret.secrets["ecom-db-password"].secret_id
}

output "next_steps" {
  value = <<-EOT
    Terraform provisioning complete. Next steps:
    1. Build and push the app image, then update Cloud Run:
       ./scripts/deploy.sh ${var.project_id} ${var.region} ${google_artifact_registry_repository.ecom_repo.repository_id} ${var.cloud_run_service_name}
    2. Run database migrations against Cloud SQL:
       ./scripts/migrate.sh ${var.project_id} ${var.region} ${google_sql_database_instance.ecom_instance.connection_name}
    3. Set real Razorpay secret values (if not passed via tfvars):
       gcloud secrets versions add ecom-razorpay-key-secret --data-file=-
       gcloud secrets versions add ecom-razorpay-webhook-secret --data-file=-
    4. Seed an admin user:
       gcloud run jobs execute ... or use `flask seed-admin` via Cloud Run's console/Cloud Shell proxy (see README).
  EOT
}
