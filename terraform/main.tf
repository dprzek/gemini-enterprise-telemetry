terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

# 1. BigQuery Dataset for Gemini Enterprise Telemetry
resource "google_bigquery_dataset" "telemetry" {
  dataset_id                  = var.dataset_id
  friendly_name               = "Gemini Enterprise Telemetry & Adoption"
  description                 = "Aggregated audit trails, user activity, and model inference telemetry"
  location                    = var.region
  default_table_expiration_ms = 7776000000 # 90 days retention (configurable)

  labels = {
    env       = "telemetry"
    managed_by = "terraform"
    service   = "gemini_enterprise"
  }
}

# 2. Cloud Logging Sink
resource "google_logging_project_sink" "telemetry_sink" {
  name                   = var.sink_name
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.telemetry.dataset_id}"
  filter                 = "(resource.type=\"discoveryengine.googleapis.com/Agent\" OR resource.type=\"consumed_api\" OR resource.type=\"audited_resource\" OR protoPayload.serviceName=\"discoveryengine.googleapis.com\") AND (logName=~\"discoveryengine.googleapis.com\" OR logName=~\"cloudaudit.googleapis.com\")"
  unique_writer_identity = true

  bigquery_options {
    use_partitioned_tables = true
  }
}

# 3. IAM Binding for Sink Service Account
resource "google_project_iam_member" "sink_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = google_logging_project_sink.telemetry_sink.writer_identity
}
