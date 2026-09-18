#!/usr/bin/env bash
# ==============================================================================
# Gemini Enterprise Telemetry Pipeline - Complete Automated End-to-End Deployment
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-adk-dev-485808}}"
LOCATION="${2:-eu}"
ENGINE_ID="${3:-rossmann-agent-designer_1784194686764}"
DATASET_ID="${4:-gemini_enterprise_telemetry}"

export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"
export GOOGLE_CLOUD_LOCATION="${LOCATION}"
export GEMINI_ENGINE_ID="${ENGINE_ID}"

echo "======================================================================"
echo "Starting End-to-End Gemini Enterprise Telemetry Pipeline Deployment"
echo "  Project:   ${PROJECT_ID}"
echo "  Location:  ${LOCATION}"
echo "  Engine:    ${ENGINE_ID}"
echo "  Dataset:   ${DATASET_ID}"
echo "======================================================================"

# 1. Setup BigQuery Dataset & Logging Sink
echo -e "\n[Step 1/5] Setting up BigQuery Dataset & Cloud Logging Sink..."
"${SCRIPT_DIR}/setup_bigquery_sink.sh" "${PROJECT_ID}" "EU" "${DATASET_ID}" "gemini-enterprise-telemetry-sink"

# 2. Backfill recent Cloud Logging records to BigQuery
echo -e "\n[Step 2/5] Backfilling historical logs into BigQuery..."
python3 "${SCRIPT_DIR}/backfill_logs_to_bigquery.py" "${PROJECT_ID}" "${DATASET_ID}" 30

# 3. Create BigQuery Analytical Views
echo -e "\n[Step 3/5] Deploying BigQuery Analytical Views..."
sed "s/adk-dev-485808/${PROJECT_ID}/g; s/gemini_enterprise_telemetry/${DATASET_ID}/g" \
  "${ROOT_DIR}/bigquery/telemetry_views.sql" | bq query --project_id="${PROJECT_ID}" --use_legacy_sql=false

# 4. Deploy Cloud Monitoring Dashboard
echo -e "\n[Step 4/5] Deploying Cloud Monitoring Dashboard..."
if ! gcloud monitoring dashboards list --project="${PROJECT_ID}" --format='value(displayName)' | grep -q "Gemini Enterprise - Quotas, Adoption & Telemetry"; then
  gcloud monitoring dashboards create \
    --config-from-file="${ROOT_DIR}/monitoring/gemini_enterprise_telemetry_dashboard.json" \
    --project="${PROJECT_ID}"
else
  echo "    Cloud Monitoring Dashboard already exists."
fi

# 5. Deploy Telemetry Agent to Discovery Engine / Gemini Enterprise
echo -e "\n[Step 5/5] Deploying Telemetry & Adoption Agent to Gemini Enterprise..."
python3 "${ROOT_DIR}/agent/deploy_agent.py"

echo -e "\n======================================================================"
echo "✔ Deployment Complete! Gemini Enterprise Telemetry Pipeline is Live."
echo "======================================================================"
echo "Admins can now:"
echo "1. Run CLI: python3 ${ROOT_DIR}/cli/telemetry_cli.py utilization"
echo "2. Query BigQuery: \`${PROJECT_ID}.${DATASET_ID}.v_user_utilization\`"
echo "3. Chat with Agent in Gemini Enterprise console:"
echo "   https://console.cloud.google.com/gemini-enterprise/locations/${LOCATION}/engines/${ENGINE_ID}/overview?project=${PROJECT_ID}"
echo "4. View Cloud Monitoring Dashboard:"
echo "   https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}"
echo "======================================================================"
