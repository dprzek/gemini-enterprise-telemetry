---
name: gemini-enterprise-telemetry
description: >-
  Wdrażaj, konfiguruj i analizuj telemetrię, adopcję użytkowników oraz obserwowalność OpenTelemetry w Gemini Enterprise.
  Śledzi utylizację użytkowników z rozbiciem na poszczególne dni, rozproszone ślady i spany w Cloud Trace,
  metryki operacyjne (sesje, głębokość konwersacji, wskaźnik użycia narzędzi, czas do pierwszego tokena TTFT),
  limity kwotowe (zapytania asystenta, agenty, deep research, multimedia, kredyty WTU),
  widoki BigQuery, dashboardy Cloud Monitoring oraz agenta Gemini Enterprise.
---

# Umiejętność: Monitoring Telemetrii i Obserwowalności Gemini Enterprise

Niniejszy skill zawiera procedury, skrypty automatyzujące, widoki analityczne SQL oraz konfigurację agenta do monitorowania i raportowania telemetrii wykorzystania, adopcji i wydajności platformy **Gemini Enterprise** w organizacji.

## Architektura i Przepływ Danych

1. **Zlew Cloud Logging i Logów Audytowych (Sink)**: Automatycznie przechwytuje aktywność użytkowników, interakcje z promptami, tokeny modeli, spany OpenTelemetry oraz akcje administracyjne (`CreateAgent`, `UpdateAgent`).
2. **Zbiór Telemetryczny BigQuery (`gemini_enterprise_telemetry`)**: Przechowuje partycjonowane logi z 6 widokami analitycznymi:
   - `v_user_daily_utilization`: Dokładna aktywność per-user w rozbiciu na dni (zdarzenia, zapytania, deep research, tworzone agenty, zużyte tokeny).
   - `v_observability_traces`: Powiązania rozproszonych śladów OpenTelemetry (identyfikatory trace ID, span ID, metody, statusy wykonania).
   - `v_user_summary`: Zagregowane statystyki użytkowników od początku rejestracji.
   - `v_daily_adoption`: Wskaźniki adopcji organizacji (trendy DAU/WAU/MAU, zapytania, spalone tokeny).
   - `v_feature_usage`: Wykorzystanie poszczególnych modułów i funkcji Gemini Enterprise.
   - `v_token_telemetry`: Metryki tokenów wejściowych, wyjściowych i buforowanych.
3. **Integracja z Cloud Monitoring i OpenTelemetry (Oficjalne API Google Cloud, Zero Regex)**:
   - Ustawienia obserwowalności: [`observabilityConfig`](https://cloud.google.com/gemini/enterprise/docs/manage-observability-settings) (aktywacja śladów OpenTelemetry oraz wrażliwego logowania wejść/wyjść).
   - Rozproszone ślady i spany: [Cloud Trace OpenTelemetry Spans](https://cloud.google.com/gemini/enterprise/docs/access-traces-and-spans) łączone deterministycznie w BigQuery po `trace_id` i `session_id`.
   - Metryki operacyjne: [Cloud Monitoring](https://cloud.google.com/gemini/enterprise/docs/access-metrics) (`agent_session_count`, `agent_turn_count`, `agent_session_with_tool_count`, `engine/time_to_first_token_latency` TTFT).
   - Bieżące monitorowanie limitów kwotowych i tempa ich zużycia (`discoveryengine.googleapis.com/quota/*`).
4. **Agent Gemini Enterprise**: Wdrożony bezpośrednio w silniku Gemini Enterprise (Discovery Engine / Agent Builder).
   - Rozpoczyna konwersację od **oświadczenia o oferowanych metrykach** (utylizacja dzienna, adopcja/zaangażowanie, obserwowalność/ślady, limity kwotowe).
   - Odpowiada na zapytania o aktywność użytkowników w poszczególnych dniach, rankingi, opóźnienia i limity kwotowe.
5. **CLI Administratora**: Natychmiastowe badanie utylizacji po dniach (`--daily`), trendów adopcji i metryk obserwowalności (`python3 cli/telemetry_cli.py observability --traces`).

---

## Wymagania Wstępne i Role IAM

Aby wdrożyć potok telemetryczny w projekcie Google Cloud klienta, upewnij się, że przyznano następujące role:

| Rola IAM | Przeznaczenie |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Zarządzanie i wdrażanie agentów w Discovery Engine / Gemini Enterprise |
| `roles/logging.configWriter` | Tworzenie zlewu Cloud Logging przesyłającego logi do BigQuery |
| `roles/bigquery.admin` | Tworzenie zbioru BigQuery, tabel i widoków analitycznych SQL |
| `roles/monitoring.viewer` / `roles/monitoring.editor` | Odczyt metryk kwotowych i wdrożenie dashboardu Cloud Monitoring |
| `roles/cloudtrace.user` | Analiza rozproszonych śladów w Google Cloud Trace |
| `roles/resourcemanager.projectIamAdmin` | Nadanie uprawnień BigQuery Data Editor dla tożsamości zlewu logów |

---

## Automatyczne Wdrożenie Jednym Poleceniem

Uruchom skrypt wdrożeniowy wskazując projekt i identyfikator silnika klienta:

```bash
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

Przykład dla silnika `my-gemini-app` w regionie UE:
```bash
./scripts/deploy_pipeline.sh my-project-id eu my-gemini-app_1234567890 gemini_enterprise_telemetry
```

---

## Główne Komendy CLI dla Administratora

### 1. Metryki Obserwowalności i Rozproszone Ślady:
```bash
python3 cli/telemetry_cli.py observability --traces
```

### 2. Aktywność Użytkownika w Rozbiciu na Poszczególne Dni:
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@twojafirma.pl
```

### 3. Trendy Adopcji w Organizacji (DAU):
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

### 4. Stan Limitów Kwotowych i Puli:
```bash
python3 cli/telemetry_cli.py quotas
```
