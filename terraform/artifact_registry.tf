resource "google_artifact_registry_repository" "ecom_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo_name
  description   = "Docker images for the e-commerce Flask application."
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.apis]
}
