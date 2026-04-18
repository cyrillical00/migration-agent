# Prod environment -- Terraform skeleton
# Manual dispatch only; never applied from CI automatically.

terraform {
  required_version = ">= 1.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # backend "gcs" {
  #   bucket = "BUCKET_NAME"
  #   prefix = "migration-agent/prod"
  # }
}

variable "project" {
  type        = string
  description = "GCP project ID for prod"
}

variable "region" {
  type    = string
  default = "us-central1"
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_cloud_run_v2_service" "agent" {
  name     = "migration-agent"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project}/migration-agent:latest"

      env {
        name  = "MIGRATION_AGENT_ENV"
        value = "prod"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
  }
}
