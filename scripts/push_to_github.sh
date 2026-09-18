#!/usr/bin/env bash
# ==============================================================================
# Helper Script to Push Gemini Enterprise Telemetry to dprzek@ GitHub Repository
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${REPO_DIR}"

GITHUB_USER="dprzek"
REPO_NAME="gemini-enterprise-telemetry"
GITHUB_TOKEN="${1:-${GITHUB_PAT:-}}"

echo "======================================================================"
echo "Publishing Gemini Enterprise Telemetry Suite to GitHub (${GITHUB_USER}/${REPO_NAME})"
echo "======================================================================"

if [[ -n "${GITHUB_TOKEN}" ]]; then
  echo "--> Using provided GitHub Token..."
  git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
  git branch -M main
  git push -u origin main
  # Clean token from remote url for security
  git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
  echo "✔ Successfully pushed to https://github.com/${GITHUB_USER}/${REPO_NAME}!"
else
  echo "--> Checking SSH authentication to GitHub..."
  if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -q "successfully authenticated"; then
    git remote set-url origin "git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
    git branch -M main
    git push -u origin main
    echo "✔ Successfully pushed via SSH to git@github.com:${GITHUB_USER}/${REPO_NAME}.git!"
  else
    echo "Notice: GitHub requires authentication (Personal Access Token or SSH Key)."
    echo ""
    echo "To push with your GitHub Personal Access Token:"
    echo "  ./scripts/push_to_github.sh <YOUR_GITHUB_PAT>"
    echo ""
    echo "Or set remote to SSH once your key is added:"
    echo "  git remote set-url origin git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
    echo "  git push -u origin main"
  fi
fi
