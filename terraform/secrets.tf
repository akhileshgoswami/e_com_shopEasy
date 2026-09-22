resource "random_password" "flask_secret_key" {
  length  = 64
  special = true
}

locals {
  secrets = merge(
    {
      "ecom-db-password"             = random_password.db_password.result
      "ecom-flask-secret-key"        = random_password.flask_secret_key.result
      "ecom-razorpay-key-id"         = var.razorpay_key_id != "" ? var.razorpay_key_id : "REPLACE_ME"
      "ecom-razorpay-key-secret"     = var.razorpay_key_secret != "" ? var.razorpay_key_secret : "REPLACE_ME"
      "ecom-razorpay-webhook-secret" = var.razorpay_webhook_secret != "" ? var.razorpay_webhook_secret : "REPLACE_ME"
    },
    # Only provisioned when "Sign in with Google" is actually configured —
    # Cloud Run reads their presence to decide whether to show the button.
    var.google_oauth_client_id != "" ? {
      "ecom-google-oauth-client-id"     = var.google_oauth_client_id
      "ecom-google-oauth-client-secret" = var.google_oauth_client_secret
    } : {}
  )
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secrets
  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }

  labels = local.labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "secret_versions" {
  for_each    = local.secrets
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value

  # Razorpay credentials and rotated passwords are typically updated
  # out-of-band with `gcloud secrets versions add` after go-live; don't let
  # a routine `terraform apply` silently roll them back to this initial value.
  lifecycle {
    ignore_changes = [secret_data]
  }
}
