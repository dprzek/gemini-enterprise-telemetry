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
- **Konwersacyjny Agent Telemetrii i Obserwowalności**: Agent AI wdrożony bezpośrednio w silniku Gemini Enterprise (`rossmann-agent-designer` / Agent Builder), który rozpoczyna każdą konwersację od **oświadczenia przedstawiającego zakres oferowanych metryk** i odpowiada na zapytania administratorów w języku naturalnym.
- **Wizualny Dashboard Cloud Monitoring**: Wykresy i panele przedstawiające limity kwotowe vs. bieżące użycie, opóźnienia TTFT, liczbę sesji i tur oraz wykorzystanie narzędzi.
- **Kompletny Podręcznik Wdrożenia (Runbook)**: Szczegółowa instrukcja wdrożenia krok po kroku dla administratorów klienta opisana w pliku [MANUAL.md](MANUAL.md).
- **Automatyczne Wdrożenie Jednym Poleceniem**: Skrypt powłoki (`deploy_pipeline.sh`) oraz moduł Terraform (`terraform/`) umożliwiający natychmiastowe uruchomienie w dowolnym projekcie Google Cloud.
- **Umiejętność Antigravity (Skill)**: Gotowy skill wielokrotnego użytku spakowany w katalogu `skills/gemini-enterprise-telemetry/`.

---

## Architektura Rozwiązania

```
                                  Gemini Enterprise
                            (rossmann-agent-designer w eu)
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

## Szybki Start: Wdrożenie Jednym Poleceniem

Aby wdrożyć cały potok telemetryczny w dowolnym projekcie Google Cloud:

```bash
# Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# Uruchom automatyczne wdrożenie end-to-end
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

### Przykład dla środowiska w regionie UE:
```bash
./scripts/deploy_pipeline.sh adk-dev-485808 eu rossmann-agent-designer_1784194686764 gemini_enterprise_telemetry
# lub z przyjazną nazwą aplikacji:
./scripts/deploy_pipeline.sh dprzek-vertex eu test-app-123 gemini_enterprise_telemetry
```

> [!TIP]
> **Automatyczne Rozpoznawanie Nazwy Silnika**: W parametrze `<ENGINE_ID>` możesz podać przyjazną nazwę aplikacji z konsoli (np. `test-app-123`) lub pełny identyfikator zasobu z sufiksem timestampu (np. `test-app-123_1789757145270`). Skrypty oraz narzędzie CLI automatycznie dopasują właściwy identyfikator zasobu w Discovery Engine.

---

## Wykorzystanie CLI dla Administratorów

Repozytorium zawiera narzędzie wiersza poleceń w katalogu `cli/` umożliwiające szybkie badanie telemetrii:

### 1. Utylizacja Użytkownika w Rozbiciu na Poszczególne Dni (`--daily`)
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@dprzek.altostrat.com
```
*Przykładowy wynik:*
```text
=== Raport Dziennej Utylizacji Użytkownika (8 wpisów dziennych) ===
Data         | Identyfikator Użytkownika    | Zdarzenia | Zapytania | Deep Rsrch | Agenty  | Tokeny    
----------------------------------------------------------------------------------------------
2026-09-18   | admin@dprzek.altostrat.com   | 14        | 2         | 0          | 2       | 0         
2026-09-14   | admin@dprzek.altostrat.com   | 1         | 0         | 0          | 0       | 0         
2026-09-11   | admin@dprzek.altostrat.com   | 4         | 0         | 0          | 1       | 0         
2026-09-09   | admin@dprzek.altostrat.com   | 3         | 0         | 0          | 0       | 0         
2026-08-27   | admin@dprzek.altostrat.com   | 3         | 2         | 0          | 0       | 12,434    
2026-08-26   | admin@dprzek.altostrat.com   | 18        | 5         | 0          | 0       | 0         
2026-08-25   | admin@dprzek.altostrat.com   | 31        | 9         | 0          | 2       | 0         
2026-08-23   | admin@dprzek.altostrat.com   | 3         | 0         | 0          | 1       | 0         
```

### 2. Metryki Obserwowalności, Zaangażowania i Ślady OpenTelemetry
```bash
python3 cli/telemetry_cli.py observability --traces
```
*Przykładowy wynik:*
```text
=== Gemini Enterprise: Metryki Obserwowalności i OpenTelemetry ===
• Identyfikator Silnika:       rossmann-agent-designer_1784194686764
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
2026-09-18 11:43:09  | 5379e14ddba2e5c1860cefde7554f4c3   | StreamAssist   | admin@dprzek.altostrat.com | SUCCESS 
2026-09-18 11:31:08  | bd5b4d06073dd350c3cbe37912532b4c   | StreamAssist   | admin@dprzek.altostrat.com | SUCCEEDED
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
FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_daily_utilization`
WHERE activity_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
ORDER BY activity_date DESC, total_events DESC;
```

---

## Agent Telemetrii w Gemini Enterprise

Agent został wdrożony bezpośrednio w silniku Gemini Enterprise za pośrednictwem API Discovery Engine:

- **Wyświetlana Nazwa**: `Gemini Enterprise Telemetry & Adoption Monitor`
- **Lokalizacja**: `eu`
- **Identyfikator Silnika**: `rossmann-agent-designer_1784194686764`
- **Model**: `gemini-2.5-flash`
- **Oświadczenie Powitalne**: Przy rozpoczęciu konwersacji agent natychmiast przedstawia 4 filary oferowanych metryk (utylizacja dzienna per-user, adopcja/zaangażowanie, obserwowalność i ślady, limity kwotowe).
- **Zdolności Konwersacyjne**: Odpowiada na zapytania w języku naturalnym, generuje tabele dzień-po-dniu dla podanego użytkownika, analizuje TTFT i czasy odpowiedzi oraz ostrzega o limitach kwotowych.

Aby zaktualizować lub ponownie wdrożyć agenta:
```bash
GOOGLE_CLOUD_PROJECT=adk-dev-485808 \
GOOGLE_CLOUD_LOCATION=eu \
GEMINI_ENGINE_ID=rossmann-agent-designer_1784194686764 \
python3 agent/deploy_agent.py
```

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
│   ├── telemetry_agent_definition.json # Wyeksportowana definicja agenta w JSON
│   └── deploy_agent.py         # Skrypt wdrażający agenta z oświadczeniem powitalnym
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
