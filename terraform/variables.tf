variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "adk-dev-485808"
}

variable "region" {
  description = "The Google Cloud location/region for Gemini Enterprise and BigQuery"
  type        = string
  default     = "EU"
}

variable "dataset_id" {
  description = "The BigQuery dataset ID for Gemini Enterprise telemetry"
  type        = string
  default     = "gemini_enterprise_telemetry"
}

variable "sink_name" {
  description = "The Cloud Logging Sink name"
  type        = string
  default     = "gemini-enterprise-telemetry-sink"
}
