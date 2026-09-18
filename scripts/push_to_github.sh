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
ARG="${1:-${GITHUB_PAT:-}}"

echo "======================================================================"
echo "Publishing Gemini Enterprise Telemetry Suite to GitHub (${GITHUB_USER}/${REPO_NAME})"
echo "======================================================================"

# Reset clean origin remote
git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

# Detect if argument was accidentally passed as a URL
if [[ "${ARG}" =~ ^https?:// ]] || [[ "${ARG}" =~ \.git$ ]]; then
  echo "⚠️  You passed a repository URL (${ARG}) instead of a GitHub Personal Access Token."
  echo ""
  echo "Usage:"
  echo "  ./scripts/push_to_github.sh <YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>"
  echo ""
  echo "Example:"
  echo "  ./scripts/push_to_github.sh ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  echo ""
  echo "If you don't have a token yet:"
  echo "1. Create the repository on GitHub at: https://github.com/new"
  echo "   Name: ${REPO_NAME}"
  echo "2. Generate a token at: https://github.com/settings/tokens (select 'repo' scope)"
  echo "3. Run this script with the token."
  exit 1
fi

GITHUB_TOKEN="${ARG}"

if [[ -n "${GITHUB_TOKEN}" ]]; then
  echo "--> Checking if repository ${GITHUB_USER}/${REPO_NAME} exists on GitHub..."
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}" || true)

  if [[ "${HTTP_STATUS}" == "404" ]]; then
    echo "--> Repository does not exist yet. Creating https://github.com/${GITHUB_USER}/${REPO_NAME} via GitHub API..."
    CREATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Authorization: token ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github.v3+json" \
      https://api.github.com/user/repos \
      -d "{\"name\":\"${REPO_NAME}\",\"description\":\"Gemini Enterprise Telemetry, Quota & Adoption Monitoring Suite\",\"private\":false}")

    if [[ "${CREATE_STATUS}" == "201" ]]; then
      echo "✔ Successfully created remote repository on GitHub!"
    else
      echo "⚠️ Could not auto-create repository (HTTP ${CREATE_STATUS}). Please create it manually at https://github.com/new with name '${REPO_NAME}'."
    fi
  elif [[ "${HTTP_STATUS}" == "200" ]]; then
    echo "✔ Found existing repository ${GITHUB_USER}/${REPO_NAME} on GitHub."
  fi

  echo "--> Pushing commits to GitHub..."
  git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
  git branch -M main
  git push -u origin main
  # Clean token from remote url for security
  git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
  echo ""
  echo "======================================================================"
  echo "✔ Successfully published to https://github.com/${GITHUB_USER}/${REPO_NAME}!"
  echo "======================================================================"
  exit 0
fi

# Fallback: check if SSH authentication is available
echo "--> Checking SSH authentication to GitHub..."
if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -q "successfully authenticated"; then
  git remote set-url origin "git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
  git branch -M main
  git push -u origin main
  echo "✔ Successfully pushed via SSH to git@github.com:${GITHUB_USER}/${REPO_NAME}.git!"
  exit 0
fi

echo ""
echo "Notice: GitHub requires authentication (Personal Access Token or SSH Key)."
echo ""
echo "Option 1 (Recommended - Token):"
echo "  1. If you haven't created the repo yet, do it at https://github.com/new (Name: ${REPO_NAME})"
echo "  2. Generate a token at https://github.com/settings/tokens (scope: 'repo')"
echo "  3. Run: ./scripts/push_to_github.sh <YOUR_TOKEN>"
echo ""
echo "Option 2 (SSH Key):"
echo "  git remote set-url origin git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
echo "  git push -u origin main"
echo ""
echo "Option 3 (Interactive git push):"
echo "  git push -u origin main"
