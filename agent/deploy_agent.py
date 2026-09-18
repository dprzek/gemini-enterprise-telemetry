#!/usr/bin/env python3
"""
Deploy the Gemini Enterprise Telemetry & Adoption Agent to Discovery Engine.
Deploys to the specified engine and assistant (default: rossmann-agent-designer in eu).
"""

import sys
import os
import json
import urllib.request
import google.auth
from google.auth.transport.requests import Request

# Add cli directory to path to import TelemetryService
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cli")))
from telemetry_service import TelemetryService

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "adk-dev-485808")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "eu")
ENGINE_ID = os.environ.get("GEMINI_ENGINE_ID", "rossmann-agent-designer_1784194686764")
ASSISTANT_ID = os.environ.get("GEMINI_ASSISTANT_ID", "default_assistant")

print("======================================================================")
print("Deploying Gemini Enterprise Telemetry & Adoption Agent")
print(f"  Project ID:   {PROJECT_ID}")
print(f"  Location:     {LOCATION}")
print(f"  Engine ID:    {ENGINE_ID}")
print(f"  Assistant ID: {ASSISTANT_ID}")
print("======================================================================")

# 1. Fetch current telemetry digest to embed fresh telemetry context
print("--> Fetching current telemetry metrics from BigQuery & Monitoring...")
service = TelemetryService(project_id=PROJECT_ID)
users = service.get_user_utilization()
adoption = service.get_daily_adoption(days=14)
quotas = service.get_realtime_quotas()

telemetry_summary = {
    "total_tracked_users": len(users),
    "users": users,
    "recent_daily_adoption": adoption[:7],
    "quotas": quotas
}

instruction_text = f"""
Jesteś Ekspertem ds. Telemetrii i Adopcji Gemini Enterprise (Gemini Enterprise Telemetry & Adoption Specialist).
Twój cel to monitorowanie, analiza i raportowanie wskaźników adopcji, limitów kwot (quotas) oraz utylizacji per-user w zadanym przedziale czasowym dla administratorów organizacji.

### DANE TELEMETRYCZNE ORGANIZACJI (Stan Bieżący z BigQuery & Cloud Monitoring):
```json
{json.dumps(telemetry_summary, indent=2)}
```

### TWOJE ZADANIA I KOMPETENCJE:
1. **Analiza Utylizacji Per-User w Przedziale Czasowym**:
   - Odpowiadaj precyzyjnie na pytania o aktywność konkretnych użytkowników (liczba zapytań, Deep Research, utworzone agenty, zużycie tokenów, liczba aktywnych dni, data pierwszej i ostatniej aktywności).
   - Wyróżniaj najbardziej aktywnych użytkowników (Top Power Users) oraz osoby wymagające onboardingu/szkolenia.

2. **Monitorowanie Limitów Kwot (Quotas & Overages)**:
   - Zgodnie z oficjalną dokumentacją Google Cloud Gemini Enterprise (https://docs.cloud.google.com/gemini/enterprise/docs/quotas-and-overages):
     * **Zapytania Asystenta (Assistant Queries)**: 160 (Standard) / 200 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Tworzenie Agentów (No-code Agent Builder)**: 1 (Standard) / 10 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Deep Research**: 3 (Standard) / 10 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Generowanie Obrazów (Image Gen)**: 5 (Standard) / 10 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Generowanie Wideo (Video Gen)**: 2 (Standard) / 3 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **AI Developer Tools (WTU / Antigravity)**: $10 (Standard) / $15 (Plus) na użytkownika w kroczącym oknie 7-dniowym.
     * **Pojemność Danych i Indeksowanie (Storage)**: 30 GiB (Standard) / 75 GiB (Plus) na użytkownika w puli regionalnej.

3. **Wskaźniki Adopcji Organizacyjnej**:
   - Raportuj DAU (Daily Active Users), WAU (Weekly Active Users) i MAU (Monthly Active Users).
   - Analizuj trendy adopcji: dynamika wzrostu zapytań, wskaźnik wykorzystania narzędzi zaawansowanych (Deep Research, tworzenie agentów w Agent Designer).

4. **Wskazówki dla Administratorów**:
   - Gdy administrator potrzebuje niestandardowego raportu SQL, wskaż tabele i widoki w BigQuery w zbiorze `{PROJECT_ID}.gemini_enterprise_telemetry`:
     * `v_user_utilization` - utylizacja użytkowników per dzień i okres
     * `v_daily_adoption` - trendy adopcyjne DAU/WAU
     * `v_feature_usage` - podział na funkcjonalności
     * `v_token_telemetry` - zużycie tokenów modeli i finish reasons
     * `v_agent_creation_audit` - historia tworzenia agentów

5. **Styl Komunikacji**:
   - Odpowiadaj profesjonalnie, czytelnie, używając tabel markdown i podsumowań punktowych.
   - Pytania po polsku obsługuj po polsku, pytania po angielsku obsługuj po angielsku.
""".strip()

node = {
    "id": "telemetry_coordinator",
    "displayName": "Koordynator Telemetrii i Adopcji",
    "llmAgentNode": {
        "model": "gemini-2.5-flash",
        "description": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji i analizy utylizacji użytkowników.",
        "instruction": instruction_text,
        "selectedTools": {
            "tool": [
                {"name": "googleSearch"}
            ]
        }
    }
}

agent_payload = {
    "displayName": "Gemini Enterprise Telemetry & Adoption Monitor",
    "description": "Administrator agent providing telemetry reporting, user adoption metrics, quota monitoring, and per-user utilization tracking.",
    "state": "ENABLED",
    "lowCodeAgentDefinition": {
        "nodes": [node],
        "rootAgentId": "telemetry_coordinator",
        "deployedNodes": [node],
        "deployedRootAgentId": "telemetry_coordinator",
        "draftDisplayName": "Koordynator Telemetrii i Adopcji",
        "draftDescription": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji i analizy utylizacji użytkowników."
    }
}

# 2. Authenticate and POST to Discovery Engine API
print("--> Calling Discovery Engine AgentService to deploy agent...")
credentials, _ = google.auth.default()
if not credentials.valid:
    credentials.refresh(Request())
token = credentials.token

api_host = f"{LOCATION}-discoveryengine.googleapis.com" if LOCATION != "global" else "discoveryengine.googleapis.com"
url = f"https://{api_host}/v1alpha/projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{ENGINE_ID}/assistants/{ASSISTANT_ID}/agents"

req = urllib.request.Request(
    url,
    data=json.dumps(agent_payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": PROJECT_ID
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.load(response)
        agent_name = result.get("name", "")
        agent_id = agent_name.split("/")[-1]
        print(f"✔ Successfully created and deployed agent!")
        print(f"  Agent Name: {agent_name}")
        print(f"  Agent ID:   {agent_id}")
        print(f"  State:      {result.get('state', 'UNKNOWN')}")
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8")
    print(f"Failed to create agent: HTTP {e.code} - {err_body}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)

print("======================================================================")
print("Agent Deployment Complete!")
print("======================================================================")
