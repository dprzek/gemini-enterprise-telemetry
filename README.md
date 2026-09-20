# Monitoring Telemetrii, Adopcji i Obserwowalności Gemini Enterprise

Gotowe do wdrożenia produkcyjnego rozwiązanie do monitorowania, analizy i raportowania telemetrii wykorzystania usługi Google Cloud **Gemini Enterprise** w całej organizacji.

Pakiet obejmuje automatyczną strumieniową i wsadową ingestję logów do BigQuery, dedykowane widoki analityczne SQL, śledzenie limitów kwotowych (quotas) i opóźnień w czasie rzeczywistym w Cloud Monitoring, CLI dla administratorów oraz konwersacyjnego agenta AI wdrożonego bezpośrednio w **Gemini Enterprise Agent Designer**.

---

## Główne Funkcjonalności

- **Śledzenie Utylizacji Użytkowników (w Ujęciu Dziennym)**: Precyzyjny pomiar aktywności użytkowników, zapytań do asystenta, wywołań Deep Research, liczby tworzonych agentów oraz zużycia tokenów modeli w pełnym rozbiciu na poszczególne dni (`--daily`) lub w zadanych przedziałach czasowych.
- **Obserwowalność OpenTelemetry i Rozproszone Ślady (Distributed Tracing)**: Natywne wsparcie dla konfiguracji obserwowalności Gemini Enterprise (`observabilityConfig`), rozproszone ślady i spany w Cloud Trace (`AssistantService.StreamAssist`, `execute_tool`, `invoke_connector`) oraz widok analityczny BigQuery `v_observability_traces`.
- **Wskaźniki Zaangażowania i Adopcji UX**: Śledzenie głębokości konwersacji (Conversational Depth: liczba tur/interakcji na sesję), wskaźnika adopcji narzędzi (Tool Adoption Rate: % sesji z narzędziami) oraz postrzeganej responsywności (Time to First Token - TTFT).
- **Analityka Adopcji w Skali Organizacji**: Monitorowanie liczby aktywnych użytkowników: DAU (Daily Active Users), WAU (Weekly) i MAU (Monthly), łącznego wolumenu promptów oraz trendów retencji.
- **Monitoring Limitów Kwotowych (Pooled Quotas & Overages)**: Bieżące śledzenie limitów puli organizacji i tempa ich zużycia (zapytania asystenta, Agent Builder, Deep Research, generowanie obrazów i wideo, kredyty WTU dla narzędzi deweloperskich, przestrzeń dyskowa).
- **Konwersacyjny Agent Telemetrii i Obserwowalności**: Agent AI wdrożony bezpośrednio w silniku Gemini Enterprise (Discovery Engine / Agent Builder), który rozpoczyna każdą konwersację od **oświadczenia przedstawiającego zakres oferowanych metryk** i odpowiada na zapytania administratorów w języku naturalnym.
- **Wizualny Dashboard Cloud Monitoring**: Wykresy i panele przedstawiające limity kwotowe vs. bieżące użycie, opóźnienia TTFT, liczbę sesji i tur oraz wykorzystanie narzędzi.
- **Kompletny Podręcznik Wdrożenia (Runbook)**: Szczegółowa instrukcja wdrożenia krok po kroku dla administratorów klienta opisana w pliku [MANUAL.md](MANUAL.md).
- **Automatyczne Wdrożenie Jednym Poleceniem**: Skrypt powłoki (`deploy_pipeline.sh`) oraz moduł Terraform (`terraform/`) umożliwiający natychmiastowe uruchomienie w dowolnym projekcie Google Cloud.
- **Umiejętność Antigravity (Skill)**: Gotowy skill wielokrotnego użytku spakowany w katalogu `skills/gemini-enterprise-telemetry/`.

---

## Architektura Oparta na Oficjalnych Usługach Google Cloud (Zero Regex)

> [!IMPORTANT]
> **Natywna Architektura Telemetrii zamiast Parsowania Surowego Tekstu**:
> Rozwiązanie **nie wyciąga ani nie odgrzebuje danych z nieustrukturyzowanych logów za pomocą wyrażeń regularnych (regex)**. Zostało zaprojektowane w 100% w oparciu o oficjalne usługi, standardy i interfejsy API obserwowalności Google Cloud Gemini Enterprise:
> - 📘 [Manage observability settings](https://cloud.google.com/gemini/enterprise/docs/manage-observability-settings) ([wersja devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/manage-observability-settings))
> - 📘 [Access traces and spans](https://cloud.google.com/gemini/enterprise/docs/access-traces-and-spans) ([wersja devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/access-traces-and-spans))
> - 📘 [Access metrics](https://cloud.google.com/gemini/enterprise/docs/access-metrics) ([wersja devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/access-metrics))

### 3 Filary Oficjalnej Integracji Google Cloud:

1. ⚙️ **Konfiguracja Obserwowalności Silnika ([Manage observability settings](https://cloud.google.com/gemini/enterprise/docs/manage-observability-settings))**:
   - Skrypt instalacyjny (`deploy.py` / `deploy.sh`) oraz moduł `TelemetryService` konfigurują silnik Gemini Enterprise za pośrednictwem Discovery Engine API (`PATCH ...?updateMask=observabilityConfig`).
   - Włączane są natywne flagi platformy:
     * `observabilityConfig.observabilityEnabled = true` — automatyczna emisja rozproszonych śladów OpenTelemetry do Google Cloud Trace.
     * `observabilityConfig.sensitiveLoggingEnabled = true` — ustrukturyzowane logowanie zapytań i odpowiedzi modelu w formacie JSON/ProtoPayload.

2. ⏱️ **Rozproszone Ślady i Spany OpenTelemetry ([Access traces and spans](https://cloud.google.com/gemini/enterprise/docs/access-traces-and-spans))**:
   - Gemini Enterprise emituje standardowe spany OpenTelemetry dla każdej tury konwersacji (`AssistantService.StreamAssist`), wywołania narzędzia (`execute_tool`) i konektora (`invoke_connector`).
   - **Deterministyczne złączenia w BigQuery**: Zamiast dopasowywać ciągi znaków wyrażeniami regularnymi, widoki SQL (`v_observability_traces`, `v_user_daily_utilization`) korelują zdarzenia użytkownika z wnioskowaniem LLM (`gen_ai_client_inference_operation_details`) **ściśle po unikalnym identyfikatorze `trace_id` i `session_id` OpenTelemetry**.
   - **Zero Double-Counting**: Zastosowanie kluczy śladów i okien analitycznych (`ROW_NUMBER() OVER ...`) całkowicie eliminuje duplikaty i iloczyny kartezjańskie, zapewniając pełną spójność matematyczną.

3. 📊 **Natywne Metryki Operacyjne Cloud Monitoring ([Access metrics](https://cloud.google.com/gemini/enterprise/docs/access-metrics))**:
   - Wszystkie metryki operacyjne są odpytywane bezpośrednio z Cloud Monitoring API (`monitoring.googleapis.com`) z oficjalnej przestrzeni nazw `discoveryengine.googleapis.com/`:
     * `agent/session_count` — łączna liczba sesji agentów,
     * `agent/turn_count` — liczba tur konwersacyjnych (Conversational Depth),
     * `agent/session_with_tool_count` — wskaźnik użycia narzędzi (Tool Adoption Rate),
     * `engine/time_to_first_token_latency` — rozkład statystyczny opóźnień TTFT (Time to First Token),
     * `quota/*` — monitorowanie limitów puli organizacji w czasie rzeczywistym.
   - Metryki te są agregowane bezpośrednio w silniku platformy Google Cloud, a nie szacowane z logów.

---

## Architektura Rozwiązania

```
                                  Gemini Enterprise
                       (Dowolny silnik w wybranym regionie)
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
     Cloud Logging & Ślady Audytowe                  Cloud Monitoring (Czas Rzeczywisty)
     - discoveryengine_googleapis_com_*              - discoveryengine.googleapis.com/quota/*
     - cloudaudit_googleapis_com_activity            - agent_session_count & agent_turn_count
     - gen_ai.client.inference.operation.details     - agent_session_with_tool_count
                  │                                  - engine/time_to_first_token_latency (TTFT)
                  ▼ (Zlew Logów / Log Sink)          - agent_total_latencies & tool_latencies
       Zbiór Telemetryczny BigQuery                               │
       (gemini_enterprise_telemetry w EU)                         │
       - Tabele partycjonowane i klastrowane                      │
       - 6 Widoków Analitycznych:                                 │
         * v_user_daily_utilization (rozbicie dzienne per user)   │
         * v_observability_traces (ślady i spany OpenTelemetry)   │
         * v_user_summary (agregaty per user od początku)         │
         * v_daily_adoption (trendy DAU/WAU/MAU)                  │
         * v_feature_usage (wykorzystanie modułów i funkcji)      │
         * v_token_telemetry (tokeny wejściowe, wyjściowe, cache) │
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                      Usługa Telemetrii i CLI Administratora
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
     Agent Gemini Enterprise                           Narzędzia CLI i Monitoring
     (Wdrożony w Agent Designerze)                     - Zapytania per user po dniach (--daily)
     - Rozpoczyna oświadczeniem o metrykach            - Metryki obserwowalności i ślady
     - Pełna historia utylizacji po dniach             - Alerty limitów kwotowych
     - Raportowanie obserwowalności i TTFT             - Wizualny dashboard Cloud Monitoring
```

---

## Śledzone Wymiary Telemetryczne

| Kategoria Metryki | Badany Wymiar | Źródło Danych | Reset i Egzekwowanie Limitów |
| :--- | :--- | :--- | :--- |
| **Zapytania Asystenta** | Prompty użytkowników i odpowiedzi modelu | BigQuery + Cloud Monitoring | Codziennie o północy PT (Pula organizacji wg edycji) |
| **Tworzenie Agentów** | Agenty no-code utworzone / modyfikowane | Cloud Audit Logs (`CreateAgent`) + Quotas | Codziennie o północy PT (Pula organizacji wg edycji) |
| **Deep Research** | Uruchomione analizy Deep Research | BigQuery + Cloud Monitoring | Codziennie o północy PT (Pula organizacji wg edycji) |
| **Generowanie Obrazów**| Wygenerowane obrazy | BigQuery + Cloud Monitoring | Codziennie o północy PT (Pula organizacji wg edycji) |
| **Generowanie Wideo** | Wygenerowane wideo | BigQuery + Cloud Monitoring | Codziennie o północy PT (Pula organizacji wg edycji) |
| **Narzędzia AI Dev** | Zużycie kredytów WTU (Antigravity / IDE) | Cloud Monitoring (`ai_dev_tool_wtu_*`) | Kroczące okno 7-dniowe (Pula organizacji) |
| **Pojemność Danych** | GiB zindeksowane w magazynach danych | Cloud Monitoring (`total_document_size`) | Ciągła pula regionalna |
| **Utylizacja Użytkowników**| Zdarzenia, zapytania, agenty, tokeny | BigQuery (`v_user_daily_utilization`) | Dowolny filtr dat i rozbicie na poszczególne dni |
| **Głębokość Konwersacji**| Średnia liczba tur (turns) na sesję | Cloud Monitoring (`agent_turn_count`) | Okno kroczące |
| **Adopcja Narzędzi** | % sesji z wywołaniem narzędzi zewnętrznych | Cloud Monitoring (`agent_session_with_tool_count`) | Okno kroczące |
| **Opóźnienie TTFT** | Czas do wygenerowania pierwszego tokena | Cloud Monitoring (`engine/time_to_first_token_latency`)| Rozkład statystyczny opóźnień |
| **Ślady Rozproszone** | Ślady i spany OpenTelemetry w Cloud Trace | BigQuery (`v_observability_traces`) | Retencja 30 dni w Cloud Trace |
| **Zużycie Tokenów** | Tokeny promptu, odpowiedzi i buforowane (cache) | BigQuery (`v_token_telemetry`) | W czasie rzeczywistym i zagregowane |

---

## Szybki Start: Wdrożenie Jednym Poleceniem (Zero-Touch)

Aby wdrożyć cały potok telemetryczny w dowolnym projekcie Google Cloud:

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Uruchom automatyczne wdrożenie end-to-end
./deploy.sh <NAZWA_LUB_ID_APLIKACJI>

# Przykład:
./deploy.sh test-test-test
# Lub ze wskazaniem konkretnego projektu i lokalizacji:
./deploy.sh test-test-test --project dprzek-prod --location eu
```

> [!TIP]
> **Co automatyzuje `deploy.sh` (lub `python3 deploy.py`)?**
> - **Zero kroków manualnych**: Automatycznie włącza `observabilityConfig` na silniku bez potrzeby ręcznego wysyłania zapytań cURL czy klikania w panelu.
> - **Automatyczne rozpoznawanie silnika**: Dopasowuje przyjazną nazwę aplikacji (np. `test-test-test`) do właściwego identyfikatora zasobu (`test-test-test_1789816756559`).
> - **Automatyczny setup BigQuery & IAM**: Tworzy zbiór danych, zlew logów, nadaje uprawnienia `roles/bigquery.dataEditor`, przeprowadza backfill i kompiluje zdeduplikowane widoki SQL.
> - **Wdrożenie Agenta i Dashboardu**: Tworzy dashboard operacyjny w Cloud Monitoring i publikuje Agenta Telemetrii w Gemini Enterprise.

---

## Wykorzystanie CLI dla Administratorów

Repozytorium zawiera narzędzie wiersza poleceń w katalogu `cli/` umożliwiające szybkie badanie telemetrii:

### 1. Utylizacja Użytkownika w Rozbiciu na Poszczególne Dni (`--daily`)
```bash
python3 cli/telemetry_cli.py utilization --daily --user user@example.com
```
*Przykładowy wynik:*
```text
=== Raport Dziennej Utylizacji Użytkownika (5 wpisów dziennych) ===
Data         | Identyfikator Użytkownika    | Zdarzenia | Zapytania | Deep Rsrch | Agenty  | Tokeny    
------------------------------------------------------------------------------------------------
2026-09-19   | user@example.com             | 8         | 5         | 0          | 2       | 39,643    
2026-09-18   | user@example.com             | 4         | 2         | 0          | 2       | 16,840    
2026-09-15   | user@example.com             | 3         | 2         | 1          | 0       | 28,150    
2026-09-12   | user@example.com             | 4         | 3         | 0          | 1       | 23,920    
2026-09-08   | user@example.com             | 2         | 2         | 0          | 0       | 15,410    
```
> [!NOTE]
> **Zgodność Matematyczna**: Liczba `Zdarzenia` odpowiada rzeczywistej sumie akcji użytkownika (`Zapytania + Deep Rsrch + Agenty + Zdarzenia Audytu silnika`). W każdym dniu z zarejestrowanymi zapytaniami do asystenta lub zadaniami badawczymi generowane jest ściśle dodatnie zużycie `Tokenów` (tokeny promptu, odpowiedzi oraz buforowane).

### 2. Metryki Obserwowalności, Zaangażowania i Ślady OpenTelemetry
```bash
python3 cli/telemetry_cli.py observability --traces
```
*Przykładowy wynik:*
```text
=== Gemini Enterprise: Metryki Obserwowalności i OpenTelemetry ===
• Identyfikator Silnika:       <ENGINE_ID> (np. my-gemini-app_1234567890)
• Lokalizacja:                 eu
• Obserwowalność Włączona:     True
• Wrażliwe Logowanie Włączone: True
• Typ Aplikacji:               APP_TYPE_INTRANET
--------------------------------------------------------------------
• Liczba Sesji Agenta:         4600
• Liczba Tur Konwersacyjnych:  8360
• Głębokość Konwersacji:       1.82 tury/sesję
• Sesje z Użyciem Narzędzi:    0
• Wskaźnik Adopcji Narzędzi:   0.0%
• Łączna Liczba Zapytań:       9067
• Średni Czas do 1. Tokena:    47747.19 ms
• Średni Czas Całkowity:       208540.94 ms

=== Ostatnie Rozproszone Ślady OpenTelemetry (2 wpisy) ===
Czas (UTC)           | Identyfikator Śladu (Trace ID)     | Metoda         | Użytkownik                 | Status  
--------------------------------------------------------------------------------------------------------------
2026-09-18 11:43:09  | 5379e14ddba2e5c1860cefde7554f4c3   | StreamAssist   | user@example.com           | SUCCESS 
2026-09-18 11:31:08  | bd5b4d06073dd350c3cbe37912532b4c   | StreamAssist   | user@example.com           | SUCCEEDED
```

### 3. Trendy Adopcji Organizacji (DAU, Zdarzenia, Zapytania)
```bash
python3 cli/telemetry_cli.py adoption --days 14
```

### 4. Bieżące Limity Kwotowe i Zasady Resetu
```bash
python3 cli/telemetry_cli.py quotas
```

### 5. Eksport Pełnego Raportu Markdown
```bash
python3 cli/telemetry_cli.py report --output raport_adopcji.md
```

---

## Widoki Analityczne SQL w BigQuery

Zbiór danych `gemini_enterprise_telemetry` udostępnia 6 zoptymalizowanych widoków analitycznych:

1. **`v_user_daily_utilization`**: Dokładne rozbicie utylizacji każdego użytkownika na poszczególne dni (zdarzenia, zapytania, deep research, agenty, tokeny). Automatycznie łączy strumienie w czasie rzeczywistym z historią.
2. **`v_observability_traces`**: Rozproszone ślady OpenTelemetry łączące `trace_id`, `span_id`, użytkownika, wywołaną metodę oraz status wykonania odpowiedzi.
3. **`v_user_summary`**: Całościowe zagregowane statystyki per użytkownik od początku rejestracji.
4. **`v_daily_adoption`**: Wskaźniki adopcji organizacji (DAU, łączna liczba interakcji, zapytań i spalonych tokenów).
5. **`v_feature_usage`**: Wykorzystanie poszczególnych modułów i funkcji Gemini Enterprise.
6. **`v_user_utilization`**: Widok kompatybilności wstecznej (alias do `v_user_daily_utilization`).

Przykładowe zapytanie analityczne SQL:
```sql
SELECT 
  activity_date,
  user_id, 
  total_events,
  assistant_queries, 
  agents_created,
  total_tokens
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_user_daily_utilization`
WHERE activity_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
ORDER BY activity_date DESC, total_events DESC;
```

---

## Dynamiczny Agent Telemetrii w Gemini Enterprise (Google ADK & Agent Runtime)

W odróżnieniu od statycznych promptów snapshotowych, to rozwiązanie wdraża **w pełni autonomicznego i dynamicznego Agenta ADK (Google Agent Development Kit)**, hostowanego w zarządzanym środowisku **Vertex AI Agent Runtime (Reasoning Engine)** i zintegrowanego natywnie z aplikacją **Gemini Enterprise**:

- **Oficjalna Nazwa**: `Gemini Enterprise Telemetry & Adoption Agent`
- **Środowisko Uruchomieniowe**: Vertex AI Agent Runtime (Reasoning Engine w regionie aplikacji, np. `europe-west1` dla silników `eu`)
- **Silnik Bazowy**: `gemini-2.5-flash`
- **Architektura Dynamicznych Narzędzi (Zero Prompt Injection)**:
  Agent nie posiada zahardkodowanych danych ani jednorazowych zrzutów w instrukcji systemowej. Przy **każdym pytaniu użytkownika** agent w czasie rzeczywistym autonomicznie wybiera i wywołuje jedno lub więcej narzędzi w Pythonie, bezpośrednio odpytując BigQuery oraz Cloud Monitoring API:
  
  1. `get_user_daily_utilization(user_email, days)`: Pobiera dokładne dzienne rozbicie aktywności wskazanego użytkownika z widoku BigQuery `v_user_daily_utilization` (zapytania, tokeny prompt/response/cache, Deep Research, agenty).
  2. `get_user_summary(user_email)`: Zwraca łączne statystyki dla danego użytkownika lub generuje ranking najbardziej aktywnych użytkowników w organizacji.
  3. `get_daily_adoption(days)`: Pobiera trendy DAU (Daily Active Users), łączną liczbę interakcji, sesji badawczych i spalonych tokenów z widoku `v_daily_adoption`.
  4. `get_realtime_quotas()`: Bada w czasie rzeczywistym stan limitów kwotowych (RPM, TPM, headroom) oraz utylizację w Google Cloud Monitoring.
  5. `get_observability_traces(days)`: Bada rozproszone ślady OpenTelemetry, liczbę zapytań w oknach czasowych, stany odpowiedzi oraz błędy z widoku `v_observability_traces`.

### Wdrożenie Agenta ADK:
```bash
python3 agent/deploy_adk_agent.py \
    --project=<PROJECT_ID> \
    --location=eu \
    --vertex-location=europe-west1 \
    --engine=<ENGINE_ID>
```
Agent jest automatycznie rejestrowany w silniku Gemini Enterprise (`default_assistant/agents`) ze stanem `ENABLED` i natychmiast gotowy do obsługi zapytań użytkowników i administratorów.

---

## Struktura Katalogów Repozytorium

```text
gemini-enterprise-telemetry/
├── README.md                   # Główny opis projektu i dokumentacja (PL)
├── MANUAL.md                   # Szczegółowy podręcznik wdrożenia i procedury operacyjne (PL)
├── LICENSE                     # Licencja Apache 2.0
├── .gitignore                  # Reguły ignorowania plików git
├── scripts/
│   ├── deploy_pipeline.sh      # Główny skrypt automatycznego wdrożenia potoku
│   ├── setup_bigquery_sink.sh  # Konfiguracja zbioru BigQuery i zlewu Cloud Logging
│   ├── backfill_logs_to_bigquery.py # Wsadowe uzupełnienie logów historycznych
│   └── push_to_github.sh       # Bezpieczny skrypt publikacji do repozytorium GitHub
├── bigquery/
│   └── telemetry_views.sql     # Definicje 6 widoków analitycznych SQL w BigQuery
├── monitoring/
│   └── gemini_enterprise_telemetry_dashboard.json # Definicja dashboardu Cloud Monitoring
├── cli/
│   ├── telemetry_service.py    # Moduł integrujący BigQuery i Cloud Monitoring
│   └── telemetry_cli.py        # Interfejs wiersza poleceń (CLI) dla administratorów
├── agent/
│   ├── adk_telemetry_agent.py  # Autonomiczny Agent ADK z dynamicznymi narzędziami BigQuery/Monitoring
│   ├── deploy_adk_agent.py     # Skrypt wdrażający agenta do Vertex AI Reasoning Engine i rejestrujący w Gemini
│   ├── telemetry_agent_definition.json # Kopia zapasowa konfiguracji agenta w formacie JSON
│   └── deploy_agent.py         # Skrypt pomocniczy / legacy
├── deploy.py                   # Główny zintegrowany instalator potoku Zero-Touch
├── terraform/                  # Moduł Infrastructure-as-Code (Terraform)
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── skills/
    └── gemini-enterprise-telemetry/
        └── SKILL.md            # Umiejętność Antigravity do powielania wdrożeń
```

---

## Licencja

Oprogramowanie udostępniane na licencji Apache License 2.0. Szczegóły w pliku [LICENSE](LICENSE).
