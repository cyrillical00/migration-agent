# Staging environment -- Terraform skeleton
# Actual apply blocked until staging GCP project ID is confirmed (QUESTIONS.md)

terraform {
  required_version = ">= 1.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Backend: uncomment and fill in once GCS bucket is provisioned (QUESTIONS.md)
  # backend "gcs" {
  #   bucket = "BUCKET_NAME"
  #   prefix = "migration-agent/staging"
  # }
}

variable "project" {
  type        = string
  description = "GCP project ID for staging"
}

variable "region" {
  type    = string
  default = "us-central1"
}

provider "google" {
  project = var.project
  region  = var.region
}

# Cloud Run service for the agent
resource "google_cloud_run_v2_service" "agent" {
  name     = "migration-agent"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project}/migration-agent:latest"

      env {
        name  = "MIGRATION_AGENT_ENV"
        value = "staging"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 3
    }
  }
}
