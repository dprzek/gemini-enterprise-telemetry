#!/usr/bin/env bash
# ==============================================================================
# Gemini Enterprise Telemetry Pipeline - BigQuery & Cloud Logging Sink Setup
# ==============================================================================
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-adk-dev-485808}}"
LOCATION="${2:-EU}"
DATASET_ID="${3:-gemini_enterprise_telemetry}"
SINK_NAME="${4:-gemini-enterprise-telemetry-sink}"

echo "======================================================================"
echo "Configuring Gemini Enterprise Telemetry Pipeline"
echo "  Project ID:   ${PROJECT_ID}"
echo "  Location:     ${LOCATION}"
echo "  Dataset ID:   ${DATASET_ID}"
echo "  Sink Name:    ${SINK_NAME}"
echo "======================================================================"

# 1. Create BigQuery Dataset if it doesn't already exist
echo "--> Checking/Creating BigQuery Dataset '${DATASET_ID}' in location '${LOCATION}'..."
if ! bq show --project_id="${PROJECT_ID}" "${DATASET_ID}" >/dev/null 2>&1; then
  bq --location="${LOCATION}" --project_id="${PROJECT_ID}" mk \
    --dataset \
    --description="Gemini Enterprise adoption telemetry, inference operations, and audit logs" \
    "${DATASET_ID}"
  echo "    Successfully created dataset '${DATASET_ID}'."
else
  echo "    Dataset '${DATASET_ID}' already exists."
fi

# 2. Define the Logging Filter
# Filters:
# - Gemini Enterprise User Activity logs (queries, deep research, sessions)
# - Inference Operation Details (token usage: input, output, cache read, latencies)
# - Cloud Audit Activity & Data Access (agent creation, modifications, permissions)
LOG_FILTER='(resource.type="discoveryengine.googleapis.com/Agent" OR resource.type="consumed_api" OR resource.type="audited_resource" OR protoPayload.serviceName="discoveryengine.googleapis.com") AND (logName=~"discoveryengine.googleapis.com" OR logName=~"cloudaudit.googleapis.com")'

# 3. Create or Update Cloud Logging Sink
DESTINATION="bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${DATASET_ID}"
echo "--> Checking/Creating Cloud Logging Sink '${SINK_NAME}'..."

if gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "    Updating existing sink '${SINK_NAME}'..."
  gcloud logging sinks update "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --use-partitioned-tables
else
  echo "    Creating new sink '${SINK_NAME}'..."
  gcloud logging sinks create "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --use-partitioned-tables
fi

# 4. Grant BigQuery Data Editor to Sink Writer Identity
echo "--> Fetching Sink Writer Identity..."
WRITER_IDENTITY=$(gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" --format='value(writerIdentity)')
echo "    Writer Identity: ${WRITER_IDENTITY}"

echo "--> Granting BigQuery Data Editor role to sink service account..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${WRITER_IDENTITY}" \
  --role="roles/bigquery.dataEditor" \
  --condition=None \
  --quiet >/dev/null

echo "======================================================================"
echo "✔ BigQuery Logging Sink successfully configured!"
echo "  Destination: ${DESTINATION}"
echo "  Writer:      ${WRITER_IDENTITY}"
echo "======================================================================"
