#!/usr/bin/env python3
"""
Deploy the Gemini Enterprise Telemetry & Adoption Agent to Discovery Engine.
Deploys to the specified engine and assistant (default: rossmann-agent-designer in eu).
Grounds the agent with real-time BigQuery metrics including DAY-BY-DAY user activity.
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
print("Deploying Gemini Enterprise Telemetry & Adoption Agent (with Daily Breakdown)")
print(f"  Project ID:   {PROJECT_ID}")
print(f"  Location:     {LOCATION}")
print(f"  Engine ID:    {ENGINE_ID}")
print(f"  Assistant ID: {ASSISTANT_ID}")
print("======================================================================")

# 1. Fetch current telemetry data from BigQuery & Monitoring
print("--> Fetching live telemetry metrics from BigQuery & Monitoring...")
service = TelemetryService(project_id=PROJECT_ID)
users_summary = service.get_user_summary()
users_daily = service.get_user_daily_breakdown()
adoption = service.get_daily_adoption(days=14)
quotas = service.get_realtime_quotas()

telemetry_data = {
    "total_tracked_users": len(users_summary),
    "user_summary_all_time": users_summary,
    "user_daily_activity_breakdown": users_daily,
    "organization_daily_adoption": adoption[:10],
    "quotas": quotas
}

instruction_text = f"""
Jesteś Ekspertem ds. Telemetrii i Adopcji Gemini Enterprise (Gemini Enterprise Telemetry & Adoption Specialist).
Twój cel to monitorowanie, analiza i raportowanie wskaźników adopcji, limitów kwot (quotas) oraz utylizacji per-user w zadanym przedziale czasowym (w tym w dokładnym rozbiciu na poszczególne dni) dla administratorów organizacji.

### BIEŻĄCE DANE TELEMETRYCZNE Z BIGQUERY I CLOUD MONITORING:
```json
{json.dumps(telemetry_data, indent=2)}
```

### TWOJE ZADANIA I REGUŁY ODPOWIADANIA:
1. **Analiza Utylizacji Per-User w Rozbiciu na Poszczególne Dni**:
   - Gdy użytkownik/administrator pyta o aktywność lub adopcję konkretnego użytkownika po dniach (np. "powiedz mi jak wygląda adopcja użytkownika admin@dprzek.altostrat.com po konkretnych dniach"):
     * **ZAWSZE przedstaw tabelę rozbitą na poszczególne daty** z danymi z sekcji `user_daily_activity_breakdown`.
     * Tabela musi zawierać kolumny: `Data (YYYY-MM-DD)`, `Liczba Zdarzeń (Events)`, `Zapytania Asystenta (Queries)`, `Deep Research`, `Utworzone Agenty`, `Zużyte Tokeny`.
     * Pod tabelą dodaj krótkie podsumowanie trendu (np. w które dni użytkownik był najbardziej aktywny, jakie narzędzia wykorzystywał).
     * **NIGDY nie mów, że brakuje danych dziennych** - posiadasz pełną historię każdego dnia w `user_daily_activity_breakdown`.

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
   - Analizuj trendy adopcji: dynamika wzrostu zapytań, wskaźnik wykorzystania narzędzi zaawansowanych.

4. **Wskazówki dla Administratorów**:
   - Gdy administrator potrzebuje zapytać BigQuery bezpośrednio, wskaż zbiór `{PROJECT_ID}.gemini_enterprise_telemetry`:
     * `v_user_daily_utilization` - utylizacja per-user rozbita na poszczególne dni
     * `v_user_summary` - zagregowane statystyki użytkowników
     * `v_daily_adoption` - trendy adopcyjne DAU/WAU organizacji
     * `v_feature_usage` - podział na funkcjonalności
     * `v_token_telemetry` - zużycie tokenów modeli i finish reasons

5. **Styl Komunikacji**:
   - Odpowiadaj profesjonalnie, czytelnie, używając estetycznych tabel markdown i punktorów.
   - Pytania po polsku obsługuj po polsku, pytania po angielsku po angielsku.
""".strip()

node = {
    "id": "telemetry_coordinator",
    "displayName": "Koordynator Telemetrii i Adopcji",
    "llmAgentNode": {
        "model": "gemini-2.5-flash",
        "description": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji i analizy utylizacji użytkowników (w tym w ujęciu dziennym).",
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
    "description": "Administrator agent providing telemetry reporting, user adoption metrics, quota monitoring, and detailed per-user daily utilization tracking.",
    "state": "ENABLED",
    "lowCodeAgentDefinition": {
        "nodes": [node],
        "rootAgentId": "telemetry_coordinator",
        "deployedNodes": [node],
        "deployedRootAgentId": "telemetry_coordinator",
        "draftDisplayName": "Koordynator Telemetrii i Adopcji",
        "draftDescription": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji i analizy utylizacji użytkowników (w tym w ujęciu dziennym)."
    }
}

# 2. Authenticate and POST to Discovery Engine API
print("--> Deploying agent to Discovery Engine AgentService...")
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
