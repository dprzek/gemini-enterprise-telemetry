# Podręcznik Telemetrii, Adopcji i Obserwowalności Gemini Enterprise

Niniejszy podręcznik zawiera kompletne instrukcje wdrożenia, konfiguracji i eksploatacji pakietu **Gemini Enterprise Telemetry, Adoption, Quota & OpenTelemetry Observability Suite** w dowolnym środowisku klienta Google Cloud.

---

## 1. Architektura i Potok Telemetryczny

```
                                      Gemini Enterprise
                             (Silnik Enterprise / Agent Builder)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Cloud Logging i Ślady Audytowe                  Cloud Monitoring (Czas Rzeczywisty)
         - discoveryengine_googleapis_com_*              - discoveryengine.googleapis.com/quota/*
         - cloudaudit_googleapis_com_activity            - agent_session_count & agent_turn_count
         - gen_ai.client.inference.operation.details     - agent_session_with_tool_count
                      │                                  - engine/time_to_first_token_latency (TTFT)
                      ▼ (Zlew Logów / Sink)              - agent_total_latencies & tool_latencies
           Zbiór Danych BigQuery                                      │
           (gemini_enterprise_telemetry)                              │
           - Tabele partycjonowane i klastrowane                      │
           - 6 Widoków Analitycznych:                                 │
             * v_user_daily_utilization (rozbicie dzienne per user)   │
             * v_observability_traces (ślady i spany OpenTelemetry)   │
             * v_user_summary (statystyki per user od początku)       │
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
         - Pełna historia utylizacji po dniach             - Alerty limitów kwotowych w czasie rzecz.
         - Raportowanie obserwowalności i TTFT             - Wizualny dashboard Cloud Monitoring
```

---

## 2. Architektura Obserwowalności Gemini Enterprise

Rozwiązanie natywnie integruje się z trzema kluczowymi obszarami obserwowalności Google Cloud Gemini Enterprise. Całość opiera się na **oficjalnych interfejsach platformy, bez odgrzebywania logów czy parsowania surowego tekstu wyrażeniami regularnymi (Zero Regex)**:

### 2.1 Zarządzanie Ustawieniami Obserwowalności ([Oficjalna Dokumentacja](https://cloud.google.com/gemini/enterprise/docs/manage-observability-settings) / [Devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/manage-observability-settings))
Gemini Enterprise umożliwia precyzyjne sterowanie instrumentacją telemetrii na poziomie **Silnika (Aplikacji asystenta)** oraz **Pojedynczego Agenta**:

1. **Instrumentacja Śladów OpenTelemetry i Logów (`observabilityEnabled`)**:
   - Rejestruje rozproszone spany wykonania, ścieżki wywołań, kody błędów, czasy opóźnień (TTFT) oraz wolumeny tokenów (input, output, reasoning).
   - **Nie rejestruje** treści promptów ani odpowiedzi użytkownika. W pełni wystarcza do zasilania potoku telemetrii i analityki adopcji!
2. **Wrażliwe Logowanie Promptów i Odpowiedzi (`sensitiveLoggingEnabled`)**:
   - Zapisuje pełną treść promptów wprowadzanych przez użytkowników (`gen_ai.user.message`) oraz tekst wygenerowanych odpowiedzi (`gen_ai.choice`), w tym zacytowane fragmenty dokumentów z konektorów zewnętrznych (np. Microsoft 365, SharePoint, Google Drive).
   - *Uwaga Compliance/AI Governance*: Zgodnie z dokumentacją Google Cloud, dane wrażliwe nie są odfiltrowywane (*„Sensitive data isn't filtered out of the audit logs”*). W środowiskach korporacyjnych zaleca się utrzymywanie tej flagi jako `false` (Privacy-by-Design), chyba że organizacja prowadzi formalny audyt treści.

#### Włączenie przez Konsolę Google Cloud:
- Przejdź do: **Gemini Enterprise > Configurations > Observability** (lub **Agents > [Nazwa Agenta] > Configuration**).
- Włącz przełącznik: **Enable instrumentation of OpenTelemetry traces and logs**.
- (Opcjonalnie, tylko w celach audytu treści) Włącz przełącznik: **Enable logging of prompt inputs and response outputs**.

#### Włączenie za pośrednictwem API REST (Domyślny tryb Privacy-by-Design):
```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: <PROJECT_ID>" \
  "https://<LOCATION>-discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/<LOCATION>/collections/default_collection/engines/<ENGINE_ID>?updateMask=observabilityConfig" \
  -d '{
    "observabilityConfig": {
      "observabilityEnabled": true,
      "sensitiveLoggingEnabled": false
    }
  }'
```

---

### 2.2 Dostęp do Śladów i Spanów OpenTelemetry ([Oficjalna Dokumentacja](https://cloud.google.com/gemini/enterprise/docs/access-traces-and-spans) / [Devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/access-traces-and-spans))
Gdy instrumentacja jest aktywna, Gemini Enterprise emituje kompletne rozproszone ślady do usługi **Google Cloud Trace** (retencja 30 dni):

> [!NOTE]
> **Brak wyrażeń regularnych (Zero Regex)**:
> Korelacja zdarzeń w widokach SQL (`v_observability_traces`, `v_user_daily_utilization`) oraz łączenie logów asystenta z tabelą wnioskowania modelu (`gen_ai_client_inference_operation_details`) odbywa się **ściśle po natywnych kluczach OpenTelemetry `trace_id` oraz `session_id`**. Wyklucza to błędy parsowania tekstu, iloczyny kartezjańskie i podwójne zliczanie tokenów.

- **Kontekst Śladu**: Przekazywany za pośrednictwem nagłówka `x-cloud-trace-context` i rejestrowany w tabeli oraz widoku `v_observability_traces`.
- **Hierarchia Śladu i Spany**:
  * **Główny Span Tury (Root Turn Span)**: `AssistantService.StreamAssist` (lub `AssistantService.Assist`) reprezentujący całą turę konwersacji użytkownika.
  * **Spany Wykonania Narzędzi**: `execute_tool <tool_name>` (np. wyszukiwarka `googleSearch`, interpreter kodu Python, dedykowane narzędzia enterprise).
  * **Spany Konektorów Danych**: `invoke_connector <connector_name>` (np. konektory Salesforce, Jira, Google Drive).
  * **Spany Pod-Agentów**: `invoke_agent <agent_name>` (delegowanie zadań w strukturach multi-agent).
  * **Spany Wnioskowania Modeli**: `model_generate_content` (czas przetwarzania LLM, tokeny, powód zakończenia generowania).

---

### 2.3 Dostęp do Metryk Operacyjnych Cloud Monitoring ([Oficjalna Dokumentacja](https://cloud.google.com/gemini/enterprise/docs/access-metrics) / [Devsite](https://clouddocs.devsite.corp.google.com/gemini/enterprise/docs/access-metrics))
Metryki są automatycznie publikowane w przestrzeni nazw `discoveryengine.googleapis.com/` w Google Cloud Monitoring (retencja 6 tygodni). Narzędzia CLI i usługa telemetrii odpytują je bezpośrednio przez Cloud Monitoring API:

#### A. Wskaźniki Zaangażowania i Adopcji Konwersacyjnej:
- **`agent_session_count`**: Łączna liczba sesji konwersacyjnych nawiązanych z agentami.
- **`agent_session_with_tool_count`**: Liczba sesji, w których agent aktywnie wywołał przynajmniej jedno narzędzie.
  * **Wskaźnik Adopcji Narzędzi (%)** $= \frac{\text{agent\_session\_with\_tool\_count}}{\text{agent\_session\_count}} \times 100$
- **`agent_turn_count`**: Łączna liczba tur (pytań i odpowiedzi) w konwersacjach.
  * **Głębokość Konwersacji (Conversational Depth)** $= \frac{\text{agent\_turn\_count}}{\text{agent\_session\_count}}$ (mierzy zaangażowanie i długość dialogu vs. szybkie porzucenie sesji).

#### B. Postrzegana Responsywność i Jakość UX:
- **`engine/time_to_first_token_latency` (TTFT)**: Rozkład statystyczny czasu od wysłania pytania przez użytkownika do wygenerowania pierwszego tokena odpowiedzi.
- **`agent_total_latencies`**: Rozkład całkowitego czasu trwania tury konwersacyjnej.
- **`tool_total_latencies`**: Czas narzutu wykonania poszczególnych narzędzi zewnętrznych.

---

## 3. Wymagania Wstępne i Role IAM

Konto wdrażające rozwiązanie musi posiadać następujące role IAM w projekcie Google Cloud:

| Rola IAM | Przeznaczenie |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Zarządzanie i wdrażanie agentów w Gemini Enterprise / Agent Designerze |
| `roles/logging.configWriter` | Tworzenie zlewów Cloud Logging przesyłających logi do BigQuery |
| `roles/bigquery.admin` | Zarządzanie zbiorem danych, tabelami partycjonowanymi i widokami SQL |
| `roles/monitoring.editor` | Wdrażanie dashboardów i odczyt metryk w Cloud Monitoring |
| `roles/cloudtrace.user` | Dostęp i analiza rozproszonych śladów w Google Cloud Trace |
| `roles/resourcemanager.projectIamAdmin` | Nadanie uprawnień BigQuery Data Editor dla tożsamości zlewu Cloud Logging |

---

## 4. Szybkie Wdrożenie Jednym Poleceniem (Zero-Touch One-Command)

Cały potok (włączenie obserwowalności, konfiguracja BigQuery, zlew logów, uprawnienia IAM, wsteczna ingestja, widoki analityczne SQL, dashboard Cloud Monitoring oraz wdrożenie Agenta) uruchamiany jest jednym bezobsługowym poleceniem:

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Uruchom wdrożenie ze wskazaniem identyfikatora silnika (lub przyjaznej nazwy aplikacji)
./deploy.sh <ID_SILNIKA_LUB_NAZWA>

# Przykład ze wskazaniem dokładnego ID silnika:
./deploy.sh ge-dprzek_1789915910154 --project ge-test-dprzek --location eu

# Wymuszenie ponownego wdrożenia Agenta:
./deploy.sh ge-dprzek_1789915910154 --recreate
```

> [!TIP]
> **Co automatyzuje `deploy.sh` (lub `python3 deploy.py`)?**
> 1. **Auto-konfiguracja obserwowalności (Privacy-by-Design)**: Automatycznie włącza `observabilityEnabled: true` oraz `sensitiveLoggingEnabled: false` na silniku — chroniąc dane pracowników i fragmenty dokumentów Microsoft 365, jednocześnie zbierając 100% metryk operacyjnych i adopcyjnych. Pełny audyt promptów można opcjonalnie włączyć flagą `--enable-sensitive-logging`.
> 2. **Precyzyjne i elastyczne dopasowanie silnika**: Przyjmuje dokładny identyfikator silnika (`ENGINE_ID`, np. `ge-dprzek_1789915910154`) lub przyjazną nazwę. W projektach z wieloma silnikami chroni przed pomyłką i prezentuje listę dostępnych silników do wyboru.
> 3. **Zlew Cloud Logging i uprawnienia**: Automatycznie zakłada zbiór danych BigQuery w lokalizacji `EU`, zlew logów i nadaje uprawnienia `roles/bigquery.dataEditor`.
> 4. **Wsteczna ingestja logów**: Uzupełnia historię z ostatnich 30 dni.
> 5. **Analityka SQL i Dashboard**: Wdraża zdeduplikowane widoki SQL oraz tworzy dashboard w Cloud Monitoring.
> 6. **Agent Telemetrii**: Tworzy i publikuje Agenta z uprawnieniami publicznymi (`ALL_USERS`).

---

## 5. Ręczne Wdrożenie Krok po Kroku (Procedura Change Management)

W środowiskach korporacyjnych wymagających zatwierdzania poszczególnych etapów, wykonaj poniższe kroki:

### Krok 5.1: Włączenie Obserwowalności na Silniku (Privacy-by-Design)
```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: <PROJECT_ID>" \
  "https://<LOCATION>-discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/<LOCATION>/collections/default_collection/engines/<ENGINE_ID>?updateMask=observabilityConfig" \
  -d '{"observabilityConfig": {"observabilityEnabled": true, "sensitiveLoggingEnabled": false}}'
```

### Krok 5.2: Utworzenie Zbioru BigQuery i Zlewu Cloud Logging
```bash
./scripts/setup_bigquery_sink.sh <PROJECT_ID> <REGION> <DATASET_ID> <SINK_NAME>
```

### Krok 5.3: Wsteczna Ingestja Logów Historycznych (Backfill)
```bash
python3 scripts/backfill_logs_to_bigquery.py <PROJECT_ID> <DATASET_ID> 30
```

### Krok 5.4: Wdrożenie Widoków Analitycznych SQL w BigQuery
```bash
sed "s/{project_id}/<PROJECT_ID>/g; s/{dataset_id}/<DATASET_ID>/g" \
  bigquery/telemetry_views.sql | bq query --project_id=<PROJECT_ID> --use_legacy_sql=false
```

### Krok 5.5: Utworzenie Dashboardu w Cloud Monitoring
```bash
gcloud monitoring dashboards create \
  --config-from-file=monitoring/gemini_enterprise_telemetry_dashboard.json \
  --project=<PROJECT_ID>
```

### Krok 5.6: Wdrożenie Dynamicznego Agenta ADK (Vertex AI Agent Runtime) i Współdzielenie
Wdraża Agenta ADK do Vertex AI Reasoning Engine i rejestruje go w Gemini Enterprise z uprawnieniem współdzielenia dla wszystkich użytkowników (`ALL_USERS`):
```bash
python3 agent/deploy_adk_agent.py \
  --project="<PROJECT_ID>" \
  --location="<LOCATION>" \
  --vertex-location="europe-west1" \
  --engine="<ENGINE_ID>" \
  --dataset="gemini_enterprise_telemetry"
```

#### Nadanie Uprawnień Użytkownikom w Projekcie GCP:
Aby pracownicy mogli logować się do aplikacji Gemini Enterprise i widzieć Agenta Telemetrii, administrator przypisuje im role IAM:
```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="user:uzytkownik@twoja-firma.com" \
  --role="roles/discoveryengine.user"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="user:uzytkownik@twoja-firma.com" \
  --role="roles/discoveryengine.agentspaceUser"
```

---

## 6. Przewodnik Administratora: Eksploatacja Telemetrii i Obserwowalności

### A. Dynamiczny Agent ADK w Gemini Enterprise (Reasoning Engine)

Agent `Gemini Enterprise Telemetry & Adoption Agent` działa w zarządzanym środowisku **Vertex AI Agent Runtime (Reasoning Engine)**. W odróżnieniu od rozwiązań statycznych, nie wykorzystuje wstrzykiwania migawek danych do promptu. Zamiast tego, przy każdym pytaniu użytkownika dynamicznie wywołuje narzędzia w czasie rzeczywistym:

- **Narzędzia Czasu Rzeczywistego**:
  1. `get_user_daily_utilization(user_email, days)` — pobiera z BigQuery dokładną dzienną aktywność użytkownika (zapytania, tokeny, Deep Research, agenty).
  2. `get_user_summary(user_email)` — łączne statystyki lub ranking najaktywniejszych użytkowników.
  3. `get_daily_adoption(days)` — dzienne trendy DAU i wolumenu zapytań/tokenów.
  4. `get_realtime_quotas()` — sprawdzenie limitów kwotowych (RPM, TPM, headroom) w Cloud Monitoring API.
  5. `get_observability_traces(days)` — czasy odpowiedzi, stany błędów i ślady OpenTelemetry.

Gdy użytkownik lub administrator rozmawia z agentem, agent autonomicznie odpytuje odpowiednie usługi i prezentuje wyniki w ustrukturyzowanej formie tabel Markdown.

---

### B. Wykorzystanie Interfejsu CLI dla Administratorów

#### 1. Badanie Obserwowalności, Opóźnień i Śladów OpenTelemetry:
```bash
python3 cli/telemetry_cli.py observability --traces
```
*Przykładowa odpowiedź:*
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

#### 2. Dzienna Utylizacja Konkretnego Użytkownika:
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

#### 3. Trendy Adopcji w Organizacji (DAU):
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

#### 4. Weryfikacja Stanu Limitów Kwotowych (Quotas & Overages):
```bash
python3 cli/telemetry_cli.py quotas
```

---

### C. Przykładowe Zapytania SQL w BigQuery

#### 1. Zapytanie o Ostatnie Rozproszone Ślady OpenTelemetry:
```sql
SELECT
  timestamp,
  trace_id,
  span_id,
  user_id,
  method_name,
  answer_state,
  agent_display_name
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_observability_traces`
ORDER BY timestamp DESC
LIMIT 20;
```

#### 2. Zapytanie o Aktywność Użytkowników w Rozbiciu Dzień po Dniu:
```sql
SELECT
  activity_date,
  user_id,
  total_events,
  assistant_queries,
  deep_research_count,
  agents_created,
  total_tokens
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_user_daily_utilization`
WHERE activity_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
ORDER BY activity_date DESC, total_events DESC;
```

---

## 7. Oficjalne Zestawienie Limitów Kwotowych Gemini Enterprise

Poniższa tabela odzwierciedla oficjalne limity kwotowe Google Cloud dla edycji Gemini Enterprise:

| Usługa / Funkcjonalność | Edycja Standard | Edycja Plus | Cykl Resetowania | Zakres Egzekwowania |
| :--- | :--- | :--- | :--- | :--- |
| **Zapytania Asystenta** | 160 / user / dzień | 200 / user / dzień | Północ PT | Pula Organizacji |
| **Tworzenie Agentów** | 1 / user / dzień | 10 / user / dzień | Północ PT | Pula Organizacji |
| **Deep Research** | 3 / user / dzień | 10 / user / dzień | Północ PT | Pula Organizacji |
| **Generowanie Obrazów** | 5 / user / dzień | 10 / user / dzień | Północ PT | Pula Organizacji |
| **Generowanie Wideo** | 2 / user / dzień | 3 / user / dzień | Północ PT | Pula Organizacji |
| **Narzędzia AI Dev (WTU)**| $10 / user / cykl | $15 / user / cykl | Kroczące okno 7-dniowe | Pula Organizacji |
| **Pojemność i Indeksowanie**| 30 GiB / user | 75 GiB / user | Ciągła pula regionalna | Projekt / Region |

---

## 8. Procedura Walidacji i Pakiet 15 Scenariuszy Testowych

Po wdrożeniu potoku i agenta w środowisku klienta, administrator może zweryfikować całe środowisko uruchamiając zautomatyzowany pakiet 15 testów:

```bash
python3 -m unittest discover -s tests -p "test_suite.py" -v
```

### Zestawienie 15 Scenariuszy Testowych:

1. **Test 1: Syntaktyka i Czystość Kodu Pythona (Multi-Tenant Hygiene)**
   - Weryfikuje kompilację plików Pythona i brak hardkodowanych ID projektów / klientów.
2. **Test 2: Rozpoznawanie Silnika i Odporność na Błędy Nazewnictwa**
   - Sprawdza dynamiczne rozwiązywanie silników Discovery Engine na podstawie nazwy lub prefiksu.
3. **Test 3: Automatyczna Konfiguracja Uprawnień IAM Konta Reasoning Engine**
   - Bada czy konto `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` posiada role `bigquery.jobUser`, `monitoring.viewer` i dostęp `READER` do tabel BigQuery.
4. **Test 4: Idempotentność i Schemat Tabel BigQuery (Partycjonowanie po dacie)**
   - Potwierdza partycjonowanie dzienne po polu `timestamp` w tabelach telemetrii.
5. **Test 5: Idempotentna Wsteczna Ingestja (Backfill Parsing & Idempotency)**
   - Sprawdza parser zdarzeń audytowych, aktywności użytkowników oraz operacji inferencji tokenów.
6. **Test 6: Kompilacja i Parametryzacja Widoków BigQuery (SQL DDL Dry-Run)**
   - Potwierdza poprawność zapytań DDL 6 widoków analitycznych SQL.
7. **Test 7: Spójność Matematyczna Metryk (Niezmienniki Sum Zdarzeń i Tokenów)**
   - Weryfikuje reguły spójności: $\text{Zdarzenia} \ge \text{Zapytania} + \text{Deep Research} + \text{Agenty}$ oraz $\text{Tokeny} = \text{Input} + \text{Output}$.
8. **Test 8: Precyzja Przypisywania Tokenów po Śladach OTel (Zero Double-Counting)**
   - Potwierdza brak duplikatów i iloczynu kartezjańskiego w korelacji logów.
9. **Test 9: Rygorystyczna Separacja Funkcjonalności (Deep Research vs Zapytania)**
   - Weryfikuje prawidłową kategoryzację modułów Gemini Enterprise.
10. **Test 10: Integracja Metryk Cloud Monitoring i Tras OpenTelemetry**
    - Potwierdza pobieranie limitów kwotowych i okien śladów OpenTelemetry.
11. **Test 11: Walidacja Agenta ADK (`google.adk.agents.Agent`) i Serializacja Cloudpickle**
    - Potwierdza strukturę agenta ADK, obecność 5 dynamicznych narzędzi i binarną serializację dla Agent Runtime.
12. **Test 12: Weryfikacja Wdrożenia Vertex AI Reasoning Engine (Serving State)**
    - Sprawdza dostępność i stan wdrożonego zasobu Reasoning Engine w Vertex AI (`europe-west1`).
13. **Test 13: Rejestracja i Współdzielenie Agenta w Gemini Enterprise (`sharingConfig: ALL_USERS`)**
    - Bada czy agent w Discovery Engine jest w stanie `ENABLED` z konfiguracją udostępnienia `ALL_USERS`.
14. **Test 14: Dynamiczne Zapytanie Per-User i Filtrowanie po Dniach (Live Tool Invocation)**
    - Wykonuje zapytanie BigQuery dla użytkowników weryfikując dzienne rekordy utylizacji w czasie rzeczywistym.
15. **Test 15: Dynamiczne Zapytanie o Trendy Adopcji i Porównanie Użytkowników (Multi-User Ranking)**
    - Wykonuje zapytania agregujące rankingi adopcji w skali całej organizacji.

---

## 8. Rozwiązywanie Problemów (Troubleshooting & Self-Healing)

### Błąd 400 w Gemini Enterprise: `Reasoning Engine stream closed cleanly without producing any events`

#### Objaw:
W interfejsie webowym Gemini Enterprise przy próbie wysłania wiadomości do Agenta Telemetrii pojawia się komunikat:
```text
Agent returned an error (400): Agent failed with error: Reasoning Engine stream closed cleanly without producing any events (reasoning_engine=projects/.../locations/europe-west1/reasoningEngines/..., attempt=3/3)
```

#### Diagnoza i Przyczyna Źródłowa:
Podczas wywołania metody `streaming_agent_run_with_events()` (wykorzystywanej przez Gemini Enterprise AgentSpace) w kontenerze Vertex AI Reasoning Engine uruchamiana jest metoda runnera ADK (`google/adk/runners.py`). Sprawdza ona atrybut trybu pracy agenta: `if self.agent.mode is None: self.agent.mode = 'chat'`.
Jeśli obiekt agenta został zserializowany w środowisku klienta (np. starym obrazie Cloud Shell lub z inną wersją `google-adk`), w modelu Pydantic brakowało pola `mode`, co generowało błąd `AttributeError: 'LlmAgent' object has no attribute 'mode'` i zwrot zdarzenia o kodzie błędu 498. Ponieważ strumień nie zawierał treści tekstowej, Gemini Enterprise przerywało wywołanie błędem 400.

#### Automatyczne Rozwiązanie (Self-Healing w Instalatorze):
1. **Jawna deklaracja trybu**: W `agent/adk_telemetry_agent.py` obiekt `root_agent` ma jawnie zdefiniowany parametr `mode="chat"`, co gwarantuje jego obecność w słowniku atrybutów Pydantic i deserializację bez względu na środowisko.
2. **Synchronizacja zależności klienta**: Skrypty `deploy.sh` i `deploy.py` przed serializacją automatycznie instalują i weryfikują biblioteki wykonawcze (`google-adk==2.9.0`, `google-api-core==2.35.0`).
3. **Automatyczny Health-Check**: Podczas wdrożenia skrypt sprawdza istniejący Reasoning Engine wykonując testowe wywołanie `streaming_agent_run_with_events()`. Jeśli silnik zgłasza błąd (np. kod 498 lub brak atrybutu), instalator automatycznie odrzuca uszkodzoną instancję i wdraża nową, w pełni sprawną wersję.
4. **Wymuszone odtworzenie (`--recreate`)**: W razie potrzeby wymuszenia natychmiastowej rekompilacji kontenera można użyć flagi:
   ```bash
   ./deploy.sh <ENGINE_ID> --recreate
   ```


