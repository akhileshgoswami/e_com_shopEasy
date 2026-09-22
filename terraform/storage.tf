resource "google_storage_bucket" "product_images" {
  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.labels

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# Product/category images must be publicly readable so they can be embedded
# directly in storefront pages without proxying through the app.
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.product_images.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
