output "dataset_id" {
  description = "Identyfikator telemetrycznego zbioru danych BigQuery"
  value       = google_bigquery_dataset.telemetry.dataset_id
}

output "sink_writer_identity" {
  description = "Konto serwisowe używane przez Cloud Logging do zapisu logów do BigQuery"
  value       = google_logging_project_sink.telemetry_sink.writer_identity
}
