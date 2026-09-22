variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  description = "GCP region for all regional resources."
  type        = string
  default     = "asia-south1"
}

variable "environment" {
  description = "Deployment environment name (e.g. production, staging)."
  type        = string
  default     = "production"
}

variable "database_instance_name" {
  description = "Cloud SQL instance name."
  type        = string
  default     = "ecom-db-instance"
}

variable "database_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "database_name" {
  description = "Application database name."
  type        = string
  default     = "ecom_db"
}

variable "database_user" {
  description = "Application database user."
  type        = string
  default     = "ecom_user"
}

variable "bucket_name" {
  description = "Globally-unique Cloud Storage bucket name for product/category images."
  type        = string
}

variable "artifact_repo_name" {
  description = "Artifact Registry Docker repository name."
  type        = string
  default     = "ecom-repo"
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "ecom-web"
}

variable "cloud_run_image" {
  description = "Full container image URI to deploy (e.g. REGION-docker.pkg.dev/PROJECT/REPO/ecom-web:TAG). Leave as the placeholder on first apply; Cloud Run will be updated by the deploy script afterwards."
  type        = string
  default     = "gcr.io/cloudrun/hello"
}

variable "cloud_run_min_instances" {
  description = "Minimum Cloud Run instances (0 allows scale-to-zero)."
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances."
  type        = number
  default     = 5
}

variable "cloud_run_cpu" {
  type    = string
  default = "1"
}

variable "cloud_run_memory" {
  type    = string
  default = "512Mi"
}

variable "base_url" {
  description = "Public base URL of the deployed application (set after the first deploy assigns a Cloud Run URL, or your custom domain)."
  type        = string
  default     = ""
}

variable "razorpay_key_id" {
  description = "Razorpay Key ID (not secret, but kept in Secret Manager for consistency)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "razorpay_key_secret" {
  description = "Razorpay Key Secret. Prefer leaving blank at apply time and setting it via `gcloud secrets versions add` instead of committing it to tfvars."
  type        = string
  default     = ""
  sensitive   = true
}

variable "razorpay_webhook_secret" {
  description = "Razorpay Webhook Secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_oauth_client_id" {
  description = "OAuth 2.0 Client ID for \"Sign in with Google\" (from Google Cloud Console > APIs & Services > Credentials). Leave blank to keep the Google login button disabled."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_oauth_client_secret" {
  description = "OAuth 2.0 Client Secret for \"Sign in with Google\". Prefer setting via `gcloud secrets versions add` over committing to tfvars."
  type        = string
  default     = ""
  sensitive   = true
}

variable "deletion_protection" {
  description = "Protect the Cloud SQL instance and database from accidental deletion."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Common resource labels."
  type        = map(string)
  default = {
    app = "ecom"
  }
}
