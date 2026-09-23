#!/usr/bin/env bash
# ==============================================================================
# Gemini Enterprise Telemetry Suite - Zero-Touch One-Command Deployment Wrapper
# Sposób użycia:
#   ./deploy.sh [ID_SILNIKA_LUB_NAZWA] [--project <PROJECT_ID>] [--location <LOC>] [--enable-sensitive-logging] [--recreate]
# Przykłady:
#   # Wdrożenie domyślne w trybie Privacy-by-Design (zalecane dla Governance AI):
#   ./deploy.sh ge-dprzek_1789915910154 --project ge-test-dprzek --location eu
#
#   # Opcjonalne wdrożenie z audytem pełnej treści promptów:
#   ./deploy.sh ge-dprzek_1789915910154 --enable-sensitive-logging
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Upewnij się, że zależności klienta są w 100% spójne z wersją środowiska Vertex AI Agent Runtime
if ! python3 -c "import google.adk, google.api_core; assert google.adk.__version__ == '2.9.0' and google.api_core.__version__ == '2.35.0'" 2>/dev/null; then
    echo "[*] Synchronizacja wersji bibliotek wykonawczych z Vertex AI Agent Runtime (google-adk==2.9.0)..."
    python3 -m pip install --quiet --upgrade \
        "google-adk==2.9.0" \
        "google-api-core==2.35.0" \
        "google-cloud-aiplatform>=1.70.0" \
        "google-cloud-bigquery>=3.25.0" \
        "google-cloud-monitoring>=2.21.0" \
        "cloudpickle>=3.0.0"
fi

exec python3 "${SCRIPT_DIR}/deploy.py" "$@"
