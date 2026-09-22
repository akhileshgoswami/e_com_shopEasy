terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Uncomment and configure for shared/team state storage:
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "ecom/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
