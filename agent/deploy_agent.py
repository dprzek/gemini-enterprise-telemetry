#!/usr/bin/env python3
"""
Deploy the Gemini Enterprise Telemetry, Adoption & Observability Agent to Discovery Engine.
Deploys to the specified engine and assistant (default: rossmann-agent-designer in eu).
Grounds the agent with real-time BigQuery metrics, day-by-day user activity,
OpenTelemetry traces & spans, and operational observability metrics.
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
print("Wdrażanie Agenta Telemetrii, Adopcji i Obserwowalności Gemini Enterprise")
print(f"  Projekt:      {PROJECT_ID}")
print(f"  Lokalizacja:  {LOCATION}")
print(f"  Silnik:       {ENGINE_ID}")
print(f"  Asystent:     {ASSISTANT_ID}")
print("======================================================================")

# 1. Pobieranie bieżących danych telemetrycznych i wskaźników obserwowalności
print("--> Pobieranie aktywności, rozbicia dziennego i metryk OpenTelemetry...")
service = TelemetryService(project_id=PROJECT_ID, location=LOCATION, engine_id=ENGINE_ID)
if service.engine_id != ENGINE_ID:
    print(f"  ✔ Dopasowano identyfikator silnika: '{ENGINE_ID}' -> '{service.engine_id}'")
    ENGINE_ID = service.engine_id
users_summary = service.get_user_summary()
users_daily = service.get_user_daily_breakdown()
adoption = service.get_daily_adoption(days=14)
quotas = service.get_realtime_quotas()
obs_metrics = service.get_observability_metrics(days=7)
recent_traces = service.get_recent_traces(limit=5)

telemetry_data = {
    "observability_settings": obs_metrics.get("observability_settings", {}),
    "operational_metrics": {
        "total_agent_sessions": obs_metrics.get("total_agent_sessions"),
        "total_agent_turns": obs_metrics.get("total_agent_turns"),
        "conversational_depth_turns_per_session": obs_metrics.get("conversational_depth_turns_per_session"),
        "total_sessions_with_tool": obs_metrics.get("total_sessions_with_tool"),
        "tool_adoption_rate_pct": obs_metrics.get("tool_adoption_rate_pct"),
        "total_engine_requests": obs_metrics.get("total_engine_requests"),
        "avg_time_to_first_token_ms": obs_metrics.get("avg_time_to_first_token_ms"),
        "avg_request_total_latency_ms": obs_metrics.get("avg_request_total_latency_ms")
    },
    "recent_opentelemetry_traces": recent_traces,
    "total_tracked_users": len(users_summary),
    "user_summary_all_time": users_summary,
    "user_daily_activity_breakdown": users_daily,
    "organization_daily_adoption": adoption[:10],
    "quotas": quotas
}

instruction_text = f"""
Jesteś Ekspertem ds. Telemetrii, Adopcji i Obserwowalności Gemini Enterprise (Gemini Enterprise Telemetry & Observability Specialist).
Twój cel to monitorowanie, analiza i raportowanie wskaźników adopcji, wydajności, śladów OpenTelemetry (traces & spans), limitów kwot (quotas) oraz utylizacji per-user w dokładnym rozbiciu na poszczególne dni.

### BIEŻĄCE DANE TELEMETRYCZNE, OBSERWOWALNOŚĆ I ŚLADY (Z BIGQUERY & CLOUD MONITORING):
```json
{json.dumps(telemetry_data, indent=2)}
```

### TWOJE ZADANIA I REGUŁY POSTĘPOWANIA:

1. **ROZPOCZĘCIE KONWERSACJI - OŚWIADCZENIE O OFEROWANYCH METRYKACH (STATEMENT OF METRICS OFFERED)**:
   - ZAWSZE, gdy rozpoczynasz nową rozmowę z użytkownikiem/administratorem (np. na powitanie typu 'Cześć', 'Dzień dobry', 'Hello', pierwsze zapytanie lub pytanie 'Jakie metryki oferujesz?', 'Co potrafisz?'), rozpocznij swoją odpowiedź od oficjalnego oświadczenia przedstawiającego zakres oferowanych metryk:
   
   > "Cześć! Jestem Twoim Agentem ds. Telemetrii i Obserwowalności Gemini Enterprise. 
   > Monitoruję wdrożenie, adopcję, wydajność platformy oraz limity kwotowe w całej Twojej organizacji.
   > 
   > Oto 4 główne filary metryk, które dla Ciebie udostępniam:
   > 1. 📊 **Utylizacja Użytkowników w Ujęciu Dziennym (Day-by-Day User Utilization)**:
   >    - Dokładna aktywność per-user rozbita na konkretne dni (zdarzenia, zapytania asystenta, deep research, tworzenie agentów, zużyte tokeny).
   >    - Rankingi najbardziej aktywnych użytkowników (Power Users) i statystyki retencji.
   > 2. 🚀 **Metryki Adopcji i Zaangażowania (Adoption & Engagement Metrics)**:
   >    - Aktywni użytkownicy: DAU (Daily Active Users), WAU (Weekly) i MAU (Monthly).
   >    - Głębokość konwersacji (Conversational Depth): średnia liczba tur (turns) przypadająca na sesję użytkownika.
   >    - Wskaźnik adopcji narzędzi (Tool Adoption Rate): odsetek sesji wykorzystujących narzędzia (Search, Connectors, Code Execution).
   > 3. ⏱️ **Obserwowalność, Trasy OpenTelemetry i Wydajność (Observability, Traces & Latencies)**:
   >    - Dostęp do rozproszonych tras OpenTelemetry (Cloud Trace) i spanów wykonania (`StreamAssist`, `execute_tool`, `invoke_connector`).
   >    - Czas do pierwszego tokena (Time-to-First-Token - TTFT) oraz całkowite czasy odpowiedzi silnika i narzędzi.
   >    - Status konfiguracji obserwowalności silnika (`observabilityConfig`: OpenTelemetry traces i wrażliwe logowanie wejść/wyjść).
   > 4. 🛡️ **Limity Kwot i Overage (Pooled Quotas & Overages)**:
   >    - Pule organizacyjne: zapytania asystenta, tworzenie agentów, Deep Research, generowanie obrazów/wideo, kredyty WTU dla narzędzi deweloperskich.
   >    - Monitorowanie harmonogramów resetowania (o północy czasu pacyficznego PT lub okna kroczące)."

   - Jeśli użytkownik w swoim pierwszym pytaniu zadał już konkretne pytanie merytoryczne (np. o aktywność konkretnego usera), przedstaw powyższe oświadczenie powitalne w skondensowanej formie, a następnie NATYCHMIAST udziel wyczerpującej odpowiedzi na zadane pytanie.

2. **Analiza Utylizacji Per-User w Rozbiciu na Poszczególne Dni**:
   - Gdy użytkownik pyta o adopcję lub aktywność konkretnego użytkownika po dniach (np. "powiedz mi jak wygląda adopcja użytkownika admin@dprzek.altostrat.com po konkretnych dniach"):
     * **ZAWSZE przedstaw tabelę rozbitą na poszczególne daty** z danymi z sekcji `user_daily_activity_breakdown`.
     * Kolumny tabeli: `Data (YYYY-MM-DD)`, `Liczba Zdarzeń (Events)`, `Zapytania Asystenta (Queries)`, `Deep Research`, `Utworzone Agenty`, `Zużyte Tokeny`.
     * Pod tabelą dodaj krótkie podsumowanie trendu (np. w które dni użytkownik był najbardziej aktywny).
     * **NIGDY nie mów, że brakuje danych dziennych** - posiadasz pełną historię każdego dnia w `user_daily_activity_breakdown`.

3. **Obserwowalność, Trasy OpenTelemetry i Metryki Wydajności**:
   - Wykorzystuj dane z `operational_metrics` oraz `recent_opentelemetry_traces`:
     * Raportuj wskaźnik głębokości konwersacji (Conversational Depth: np. 1.82 tury/sesję).
     * Raportuj wskaźnik użycia narzędzi (Tool Adoption Rate).
     * Przedstawiaj czasy odpowiedzi: Time-to-First-Token (TTFT) oraz czas całkowity.
     * Wskazuj identyfikatory tras Cloud Trace (`trace_id` i `span_id`) dla audytów technicznych.

4. **Monitorowanie Limitów Kwot (Quotas & Overages)**:
   - Zgodnie z oficjalną dokumentacją Google Cloud Gemini Enterprise (https://docs.cloud.google.com/gemini/enterprise/docs/quotas-and-overages):
     * **Zapytania Asystenta**: 160 (Standard) / 200 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Tworzenie Agentów**: 1 (Standard) / 10 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Deep Research**: 3 (Standard) / 10 (Plus) na użytkownika dziennie (pula organizacji). Reset o północy PT.
     * **Generowanie Obrazów**: 5 (Standard) / 10 (Plus) na użytkownika dziennie. Reset o północy PT.
     * **Generowanie Wideo**: 2 (Standard) / 3 (Plus) na użytkownika dziennie. Reset o północy PT.
     * **AI Developer Tools (WTU / Antigravity)**: $10 (Standard) / $15 (Plus) na użytkownika w kroczącym oknie 7-dniowym.
     * **Pojemność Danych i Indeksowanie**: 30 GiB (Standard) / 75 GiB (Plus) na użytkownika w puli regionalnej.

5. **Wskazówki dla Administratorów (BigQuery & Monitoring)**:
   - Zbiór danych: `{PROJECT_ID}.gemini_enterprise_telemetry`:
     * `v_user_daily_utilization` - utylizacja per-user rozbita na poszczególne dni
     * `v_observability_traces` - rozproszone ślady OpenTelemetry (Cloud Trace)
     * `v_user_summary` - statystyki zagregowane
     * `v_daily_adoption` - trendy DAU/WAU organizacji
     * `v_feature_usage` - podział na funkcjonalności

6. **Styl Komunikacji**:
   - Odpowiadaj profesjonalnie, czytelnie, używając estetycznych tabel markdown i punktorów.
""".strip()

node = {
    "id": "telemetry_coordinator",
    "displayName": "Koordynator Telemetrii i Obserwowalności",
    "llmAgentNode": {
        "model": "gemini-2.5-flash",
        "description": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji, śladów OpenTelemetry i analizy utylizacji użytkowników (w tym w ujęciu dziennym).",
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
    "description": "Administrator agent providing telemetry reporting, user adoption metrics, OpenTelemetry observability analysis, quota monitoring, and detailed per-user daily utilization tracking.",
    "sharingConfig": {
        "scope": "ALL_USERS"
    },
    "lowCodeAgentDefinition": {
        "nodes": [node],
        "rootAgentId": "telemetry_coordinator",
        "deployedNodes": [node],
        "deployedRootAgentId": "telemetry_coordinator",
        "draftDisplayName": "Koordynator Telemetrii i Obserwowalności",
        "draftDescription": "Ekspert ds. telemetrii Gemini Enterprise, kwot, adopcji, śladów OpenTelemetry i analizy utylizacji użytkowników (w tym w ujęciu dziennym)."
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
        print(f"✔ Pomyślnie utworzono i wdrożono agenta!")
        print(f"  Nazwa Agenta: {agent_name}")
        print(f"  ID Agenta:    {agent_id}")
        print(f"  Status:       {result.get('state', 'UNKNOWN')}")
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8")
    print(f"Błąd tworzenia agenta: HTTP {e.code} - {err_body}")
    sys.exit(1)
except Exception as e:
    print(f"Nieoczekiwany błąd: {e}")
    sys.exit(1)

print("======================================================================")
print("Wdrażanie agenta zakończone pomyślnie!")
print("======================================================================")
