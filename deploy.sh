#!/usr/bin/env bash
# ==============================================================================
# Gemini Enterprise Telemetry Suite - Zero-Touch One-Command Deployment Wrapper
# Sposób użycia:
#   ./deploy.sh [NAZWA_LUB_ID_SILNIKA] [--project ID] [--location LOC]
# Przykład:
#   ./deploy.sh test-test-test
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/deploy.py" "$@"
