#!/usr/bin/env bash
# ==============================================================================
# Potok Telemetrii Gemini Enterprise - Konfiguracja BigQuery i Zlewu Cloud Logging
# ==============================================================================
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo '')}}"
if [ -z "${PROJECT_ID}" ]; then
  echo "Błąd: Brak identyfikatora projektu GCP. Podaj go jako 1. argument lub ustaw zmienną GOOGLE_CLOUD_PROJECT."
  exit 1
fi
LOCATION="${2:-EU}"
DATASET_ID="${3:-gemini_enterprise_telemetry}"
SINK_NAME="${4:-gemini-enterprise-telemetry-sink}"

echo "======================================================================"
echo "Konfiguracja potoku telemetrii Gemini Enterprise"
echo "  Projekt:      ${PROJECT_ID}"
echo "  Lokalizacja:  ${LOCATION}"
echo "  Zbiór danych: ${DATASET_ID}"
echo "  Nazwa zlewu:  ${SINK_NAME}"
echo "======================================================================"

# 1. Utworzenie zbioru BigQuery, jeśli jeszcze nie istnieje
echo "--> Sprawdzanie / tworzenie zbioru danych BigQuery '${DATASET_ID}' w lokalizacji '${LOCATION}'..."
if ! bq show --project_id="${PROJECT_ID}" "${DATASET_ID}" >/dev/null 2>&1; then
  bq --location="${LOCATION}" --project_id="${PROJECT_ID}" mk \
    --dataset \
    --description="Telemetria adopcji Gemini Enterprise, operacje wnioskowania i logi audytowe" \
    "${DATASET_ID}"
  echo "    Pomyślnie utworzono zbiór danych '${DATASET_ID}'."
else
  echo "    Zbiór danych '${DATASET_ID}' już istnieje."
fi

# 2. Definicja filtra Cloud Logging
# Filtry:
# - Logi aktywności użytkowników Gemini Enterprise (zapytania, deep research, sesje)
# - Szczegóły operacji wnioskowania (zużycie tokenów: prompt, response, cache, opóźnienia)
# - Działania Cloud Audit i dostęp do danych (tworzenie i modyfikacja agentów, uprawnienia)
LOG_FILTER='(resource.type="discoveryengine.googleapis.com/Agent" OR resource.type="consumed_api" OR resource.type="audited_resource" OR protoPayload.serviceName="discoveryengine.googleapis.com") AND (logName=~"discoveryengine.googleapis.com" OR logName=~"cloudaudit.googleapis.com")'

# 3. Utworzenie lub aktualizacja zlewu Cloud Logging
DESTINATION="bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${DATASET_ID}"
echo "--> Sprawdzanie / tworzenie zlewu Cloud Logging '${SINK_NAME}'..."

if gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "    Aktualizacja istniejącego zlewu '${SINK_NAME}'..."
  gcloud logging sinks update "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --use-partitioned-tables
else
  echo "    Tworzenie nowego zlewu '${SINK_NAME}'..."
  gcloud logging sinks create "${SINK_NAME}" "${DESTINATION}" \
    --project="${PROJECT_ID}" \
    --log-filter="${LOG_FILTER}" \
    --use-partitioned-tables
fi

# 4. Nadanie roli BigQuery Data Editor dla tożsamości zlewu logów
echo "--> Pobieranie tożsamości serwisowej zlewu (Writer Identity)..."
WRITER_IDENTITY=$(gcloud logging sinks describe "${SINK_NAME}" --project="${PROJECT_ID}" --format='value(writerIdentity)')
echo "    Tożsamość serwisowa: ${WRITER_IDENTITY}"

echo "--> Nadawanie roli BigQuery Data Editor dla konta serwisowego zlewu..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${WRITER_IDENTITY}" \
  --role="roles/bigquery.dataEditor" \
  --condition=None \
  --quiet >/dev/null

# Dodatkowe jawne nadanie uprawnień do samego zbioru BigQuery
WRITER_SA="${WRITER_IDENTITY#serviceAccount:}"
python3 -c "
from google.cloud import bigquery
try:
    c = bigquery.Client(project='${PROJECT_ID}')
    ds = c.get_dataset('${DATASET_ID}')
    entries = list(ds.access_entries)
    if not any(e.entity_id == '${WRITER_SA}' for e in entries):
        entries.append(bigquery.AccessEntry(role='roles/bigquery.dataEditor', entity_type='userByEmail', entity_id='${WRITER_SA}'))
        ds.access_entries = entries
        c.update_dataset(ds, ['access_entries'])
except Exception:
    pass
"

echo "======================================================================"
echo "✔ Zlew logów BigQuery został pomyślnie skonfigurowany!"
echo "  Miejsce docelowe: ${DESTINATION}"
echo "  Konto serwisowe:  ${WRITER_IDENTITY}"
echo "======================================================================"
