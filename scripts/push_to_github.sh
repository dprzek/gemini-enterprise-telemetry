#!/usr/bin/env bash
# ==============================================================================
# Skrypt pomocniczy do publikacji repozytorium do GitHub (dprzek)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${REPO_DIR}"

GITHUB_USER="dprzek"
REPO_NAME="gemini-enterprise-telemetry"
ARG="${1:-${GITHUB_PAT:-}}"

echo "======================================================================"
echo "Publikacja pakietu telemetrii Gemini Enterprise do GitHub (${GITHUB_USER}/${REPO_NAME})"
echo "======================================================================"

# Ustawienie czystego zdalnego adresu origin
git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

# Wykrycie, czy argument został omyłkowo przekazany jako adres URL
if [[ "${ARG}" =~ ^https?:// ]] || [[ "${ARG}" =~ \.git$ ]]; then
  echo "⚠️  Przekazano adres URL repozytorium (${ARG}) zamiast osobistego tokenu dostępu GitHub (PAT)."
  echo ""
  echo "Sposób użycia:"
  echo "  ./scripts/push_to_github.sh <TWÓJ_TOKEN_GITHUB_PAT>"
  echo ""
  echo "Przykład:"
  echo "  ./scripts/push_to_github.sh ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  echo ""
  echo "Jeśli jeszcze nie posiadasz tokenu:"
  echo "1. Utwórz repozytorium na GitHubie: https://github.com/new"
  echo "   Nazwa: ${REPO_NAME}"
  echo "2. Wygeneruj token w: https://github.com/settings/tokens (wybierz uprawnienie 'repo')"
  echo "3. Uruchom ten skrypt z tokenem."
  exit 1
fi

GITHUB_TOKEN="${ARG}"

if [[ -n "${GITHUB_TOKEN}" ]]; then
  echo "--> Sprawdzanie, czy repozytorium ${GITHUB_USER}/${REPO_NAME} istnieje na GitHub..."
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}" || true)

  if [[ "${HTTP_STATUS}" == "404" ]]; then
    echo "--> Repozytorium jeszcze nie istnieje. Tworzenie https://github.com/${GITHUB_USER}/${REPO_NAME} przez API GitHub..."
    CREATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Authorization: token ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github.v3+json" \
      https://api.github.com/user/repos \
      -d "{\"name\":\"${REPO_NAME}\",\"description\":\"Pakiet monitorowania telemetrii, kwot, adopcji i obserwowalności Gemini Enterprise\",\"private\":false}")

    if [[ "${CREATE_STATUS}" == "201" ]]; then
      echo "✔ Pomyślnie utworzono zdalne repozytorium na GitHub!"
    else
      echo "⚠️ Nie udało się automatycznie utworzyć repozytorium (HTTP ${CREATE_STATUS}). Utwórz je ręcznie na https://github.com/new z nazwą '${REPO_NAME}'."
    fi
  elif [[ "${HTTP_STATUS}" == "200" ]]; then
    echo "✔ Znaleziono istniejące repozytorium ${GITHUB_USER}/${REPO_NAME} na GitHub."
  fi

  echo "--> Wypychanie commitów do GitHub..."
  git remote set-url origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
  git branch -M main
  git push -u origin main
  # Czyszczenie tokenu ze zdalnego adresu ze względów bezpieczeństwa
  git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
  echo ""
  echo "======================================================================"
  echo "✔ Pomyślnie opublikowano w https://github.com/${GITHUB_USER}/${REPO_NAME}!"
  echo "======================================================================"
  exit 0
fi

# Ścieżka alternatywna: sprawdzenie uwierzytelniania SSH
echo "--> Sprawdzanie uwierzytelniania SSH do GitHub..."
if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -q "successfully authenticated"; then
  git remote set-url origin "git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
  git branch -M main
  git push -u origin main
  echo "✔ Pomyślnie wypchnięto przez SSH do git@github.com:${GITHUB_USER}/${REPO_NAME}.git!"
  exit 0
fi

echo ""
echo "Uwaga: GitHub wymaga uwierzytelnienia (osobistego tokenu dostępu PAT lub klucza SSH)."
echo ""
echo "Opcja 1 (Zalecana - Token):"
echo "  1. Jeśli repozytorium jeszcze nie istnieje, utwórz je na https://github.com/new (Nazwa: ${REPO_NAME})"
echo "  2. Wygeneruj token na https://github.com/settings/tokens (zakres: 'repo')"
echo "  3. Uruchom: ./scripts/push_to_github.sh <TWÓJ_TOKEN>"
echo ""
echo "Opcja 2 (Klucz SSH):"
echo "  git remote set-url origin git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
echo "  git push -u origin main"
echo ""
echo "Opcja 3 (Interaktywny git push):"
echo "  git push -u origin main"
