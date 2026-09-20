variable "project_id" {
  description = "Identyfikator projektu Google Cloud"
  type        = string
}

variable "region" {
  description = "Lokalizacja Google Cloud dla Gemini Enterprise i BigQuery"
  type        = string
  default     = "EU"
}

variable "dataset_id" {
  description = "Identyfikator zbioru danych BigQuery dla telemetrii Gemini Enterprise"
  type        = string
  default     = "gemini_enterprise_telemetry"
}

variable "sink_name" {
  description = "Nazwa zlewu Cloud Logging (Sink)"
  type        = string
  default     = "gemini-enterprise-telemetry-sink"
}
