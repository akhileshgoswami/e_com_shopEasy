resource "google_service_account" "cloud_run_sa" {
  project      = var.project_id
  account_id   = "ecom-cloud-run-sa"
  display_name = "E-commerce Cloud Run service account"

  depends_on = [google_project_service.apis]
}

# Cloud SQL client role to connect via the Cloud SQL Auth Proxy.
resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Read/write access to the product image bucket.
resource "google_storage_bucket_iam_member" "cloud_run_storage_object_admin" {
  bucket = google_storage_bucket.product_images.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Access to read secret values at runtime.
resource "google_secret_manager_secret_iam_member" "cloud_run_secret_access" {
  for_each  = google_secret_manager_secret.secrets
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Allow public (unauthenticated) HTTP access to the storefront/API, since
# this is a customer-facing website. Admin routes are protected in-app.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.ecom_web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
