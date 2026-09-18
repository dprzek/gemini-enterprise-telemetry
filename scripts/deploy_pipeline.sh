#!/usr/bin/env bash
# ==============================================================================
# Potok Telemetrii Gemini Enterprise - Kompletne Automatyczne Wdrożenie End-to-End
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

# Automatyczne dopasowanie identyfikatora silnika (np. test-app-123 -> test-app-123_1789757145270)
RESOLVED_ENGINE_ID=$(python3 -c "
import sys
sys.path.insert(0, '${ROOT_DIR}/cli')
from telemetry_service import TelemetryService
try:
    svc = TelemetryService(project_id='${PROJECT_ID}', location='${LOCATION}', engine_id='${ENGINE_ID}')
    print(svc.engine_id)
except Exception:
    print('${ENGINE_ID}')
" 2>/dev/null || echo "${ENGINE_ID}")

if [ -n "${RESOLVED_ENGINE_ID}" ] && [ "${RESOLVED_ENGINE_ID}" != "${ENGINE_ID}" ]; then
  echo "--> Automatycznie dopasowano identyfikator silnika: '${ENGINE_ID}' -> '${RESOLVED_ENGINE_ID}'"
  ENGINE_ID="${RESOLVED_ENGINE_ID}"
  export GEMINI_ENGINE_ID="${ENGINE_ID}"
fi

echo "======================================================================"
echo "Rozpoczęcie automatycznego wdrożenia potoku telemetrii Gemini Enterprise"
echo "  Projekt:      ${PROJECT_ID}"
echo "  Lokalizacja:  ${LOCATION}"
echo "  Silnik:       ${ENGINE_ID}"
echo "  Zbiór danych: ${DATASET_ID}"
echo "======================================================================"

# 1. Konfiguracja zbioru BigQuery i zlewu Cloud Logging
echo -e "\n[Krok 1/5] Tworzenie zbioru BigQuery oraz zlewu Cloud Logging..."
"${SCRIPT_DIR}/setup_bigquery_sink.sh" "${PROJECT_ID}" "EU" "${DATASET_ID}" "gemini-enterprise-telemetry-sink"

# 2. Wsteczna ingestja logów z ostatnich 30 dni do BigQuery
echo -e "\n[Krok 2/5] Wsteczna ingestja logów historycznych do BigQuery..."
python3 "${SCRIPT_DIR}/backfill_logs_to_bigquery.py" "${PROJECT_ID}" "${DATASET_ID}" 30

# 3. Utworzenie widoków analitycznych SQL w BigQuery
echo -e "\n[Krok 3/5] Wdrażanie analitycznych widoków SQL w BigQuery..."
sed "s/adk-dev-485808/${PROJECT_ID}/g; s/gemini_enterprise_telemetry/${DATASET_ID}/g" \
  "${ROOT_DIR}/bigquery/telemetry_views.sql" | bq query --project_id="${PROJECT_ID}" --use_legacy_sql=false

# 4. Utworzenie Dashboardu w Cloud Monitoring
echo -e "\n[Krok 4/5] Wdrażanie dashboardu w Cloud Monitoring..."
if ! gcloud monitoring dashboards list --project="${PROJECT_ID}" --format='value(displayName)' | grep -q "Gemini Enterprise"; then
  gcloud monitoring dashboards create \
    --config-from-file="${ROOT_DIR}/monitoring/gemini_enterprise_telemetry_dashboard.json" \
    --project="${PROJECT_ID}"
else
  echo "    Dashboard w Cloud Monitoring już istnieje."
fi

# 5. Wdrożenie Agenta Telemetrii i Obserwowalności w Gemini Enterprise
echo -e "\n[Krok 5/5] Wdrażanie agenta telemetrii i adopcji w Gemini Enterprise..."
python3 "${ROOT_DIR}/agent/deploy_agent.py"

echo -e "\n======================================================================"
echo "✔ Wdrożenie zakończone pomyślnie! Potok telemetrii jest aktywny."
echo "======================================================================"
echo "Administratorzy mogą teraz:"
echo "1. Uruchomić CLI: python3 ${ROOT_DIR}/cli/telemetry_cli.py utilization --daily"
echo "2. Sprawdzić obserwowalność: python3 ${ROOT_DIR}/cli/telemetry_cli.py observability --traces"
echo "3. Odpytać BigQuery: \`${PROJECT_ID}.${DATASET_ID}.v_user_daily_utilization\`"
echo "4. Rozmawiać z Agentem w konsoli Gemini Enterprise:"
echo "   https://console.cloud.google.com/gemini-enterprise/locations/${LOCATION}/engines/${ENGINE_ID}/overview?project=${PROJECT_ID}"
echo "5. Otworzyć dashboard Cloud Monitoring:"
echo "   https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}"
echo "======================================================================"
