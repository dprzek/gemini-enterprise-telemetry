output "dataset_id" {
  description = "The ID of the BigQuery telemetry dataset"
  value       = google_bigquery_dataset.telemetry.dataset_id
}

output "sink_writer_identity" {
  description = "Service account used by Cloud Logging to write to BigQuery"
  value       = google_logging_project_sink.telemetry_sink.writer_identity
}
