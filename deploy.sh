#!/usr/bin/env bash
# ==============================================================================
# Gemini Enterprise Telemetry Suite - Zero-Touch One-Command Deployment Wrapper
# Sposób użycia:
#   ./deploy.sh [ID_SILNIKA_LUB_NAZWA] [--engine <ENGINE_ID>] [--project <PROJECT_ID>] [--location <LOC>]
# Przykłady:
#   # Wdrożenie ze wskazaniem dokładnego ID silnika:
#   ./deploy.sh ge-dprzek_1789915910154 --project ge-test-dprzek --location eu
#   ./deploy.sh --engine ge-dprzek_1789915910154
#
#   # Wdrożenie po nazwie aplikacji (jeśli w projekcie jest 1 dopasowanie):
#   ./deploy.sh ge-dprzek
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/deploy.py" "$@"
