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
           - 7 Widoków Analitycznych:                                 │
             * v_user_daily_utilization (rozbicie dzienne per user)   │
             * v_author_agent_usage (wywołania agentów autorskich)   │
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

#### 2.1.1 Automat Auto-Observability Enabler dla Agentów Użytkownika (Event-Driven)
Domyślnie nowo tworzeni w interfejsie Gemini Enterprise agenci Low-Code (`Agent`) mają flagę `observabilityConfig` niezdefiniowaną (`null`), przez co zapytania kierowane bezpośrednio do nich nie emitują zdarzeń `StreamAssist` ani tokenów do Cloud Logging.

Aby administrator nie musiał ręcznie włączać obserwowalności dla każdego nowego agenta, instalator wdraża bezserwerowy automat oparty na architekturze Event-Driven:
1. **Cloud Audit Logs**: Gdy użytkownik tworzy nowego agenta przez UI lub API, Google Cloud generuje wpis audytowy `cloudaudit.googleapis.com/activity` z metodą `google.cloud.discoveryengine.v1main.AgentService.CreateAgent`.
2. **Cloud Logging Sink**: Zlew `gemini-enterprise-agent-events-sink` natychmiast przekazuje ten wpis do tematu Cloud Pub/Sub `gemini-enterprise-agent-events`.
3. **Cloud Run Function (2nd gen)**: Funkcja `ge-auto-observability-enabler` odbiera powiadomienie, pobiera identyfikator nowo utworzonego agenta i asynchronicznie wykonuje wywołanie `PATCH .../agents/{agent_id}?updateMask=observabilityConfig` z wartością `observabilityConfig.observabilityEnabled: true`.
4. **Wsteczna synchronizacja (Reconciliation)**: Podczas instalacji moduł natychmiast sprawdza wszystkich dotychczas istniejących agentów w silniku i włącza flagę obserwowalności na każdym z nich.
5. **Koszt operacyjny**: **\$0.00 USD / miesiąc**. Wszystkie elementy (Admin Activity Audit Logs, Pub/Sub do 10 GB, Cloud Run do 2M wywołań miesięcznie) mieszczą się w całości w bezpłatnym pakiecie *Google Cloud Always Free Tier*.

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
> 6. **Agent Telemetrii**: Tworzy i rejestruje Agenta w trybie prywatnym (`RESTRICTED` - dostęp tylko dla wdrażającego; opcjonalnie z flagą `--share-with-all-users`).

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
Wdraża Agenta ADK do Vertex AI Reasoning Engine i rejestruje go w Gemini Enterprise. Domyślnie agent rejestrowany jest w trybie prywatnym (`RESTRICTED` - dostępny tylko dla osoby wdrażającej). Aby udostępnić go w całej organizacji, należy dodać flagę `--share-with-all-users`:
```bash
python3 agent/deploy_adk_agent.py \
  --project="<PROJECT_ID>" \
  --location="<LOCATION>" \
  --vertex-location="europe-west1" \
  --engine="<ENGINE_ID>" \
  --dataset="gemini_enterprise_telemetry" \
  [--share-with-all-users]
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

#### 2. Raport Utylizacji Użytkowników i Wywołań Autorskich Agentów:
```bash
# Zbiorcze zestawienie wszystkich użytkowników wraz ze statystykami autorskich agentów:
python3 cli/telemetry_cli.py utilization

# Zestawienie 10 najmniej aktywnych użytkowników (Bottom 10):
python3 cli/telemetry_cli.py utilization --bottom 10

# Szczegółowa dzienna utylizacja konkretnego pracownika:
python3 cli/telemetry_cli.py utilization --daily --user admin@dprzek.altostrat.com
```
*Przykładowy wynik (zestawienie zbiorcze):*
```text
=== Podsumowanie Aktywności Użytkowników Gemini Enterprise ===
Identyfikator Użytkownika     | Zdarz. | Zapyt. | Deep Rsrch | Obrazy | Agenty | Wywoł. Autora | Wywoł. w Org | Tokeny 
-------------------------------------------------------------------------------------------------------------------------
admin@dprzek.altostrat.com    | 24     | 16     | 0          | 0      | 2      | 6 (2)         | 6 (2 / 1)    | 12,450 
damian.przekop@gmail.com      | 3      | 0      | 0          | 0      | 1      | 0 (0)         | 0 (0 / 0)    | 0      
```
*Opis nowych kolumn autorskich agentów:*
- **Wywoł. Autora (`author_agent_*`)**: Wywołania przez samego autora stworzonych przez niego agentów w formacie: `zapytania (sesje)`.
- **Wywoł. w Org (`org_agent_*`)**: Całkowite wywołania tych agentów w całej organizacji w formacie: `zapytania (sesje / unikalni użytkownicy)`.

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
```

#### 3. Zapytanie o Wywołania Autorskich Agentów (Self vs. Org):
```sql
SELECT
  creator_user_id,
  author_agent_invocations,
  author_agent_sessions,
  org_agent_invocations,
  org_agent_sessions,
  org_agent_unique_callers
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_author_agent_usage`
ORDER BY org_agent_invocations DESC;
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

## 8. Procedura Walidacji i Pakiet 22 Scenariuszy Testowych

Po wdrożeniu potoku i agenta w środowisku klienta, administrator może zweryfikować całe środowisko uruchamiając zautomatyzowany pakiet 22 testów:

```bash
python3 tests/test_suite.py
```

### Zestawienie 22 Scenariuszy Testowych:

1. **Test 01: Syntaktyka i Czystość Kodu Pythona (Multi-Tenant Hygiene)**
   - Weryfikuje kompilację plików Pythona i brak hardkodowanych ID projektów / klientów.
2. **Test 02: Schemat i Partycjonowanie Tabel BigQuery**
   - Potwierdza partycjonowanie dzienne po polu `timestamp` i klastrowanie po `user_id`.
3. **Test 03: Idempotentna Wsteczna Ingestja (Backfill & Deduplication)**
   - Weryfikuje parser logów audytowych, inferencji i eliminację duplikatów.
4. **Test 04: Kompilacja i Schemat 7 Widoków BigQuery (SQL DDL)**
   - Sprawdza poprawność kompilacji wszystkich 7 analitycznych widoków SQL w BigQuery.
5. **Test 05: Walidacja Agenta ADK (`google.adk.agents.Agent`) i Cloudpickle**
   - Potwierdza strukturę agenta ADK, obecność dynamicznych narzędzi i serializację binarną.
6. **Test 06: Uprawnienia IAM Konta Reasoning Engine oraz `sharingConfig`**
   - Bada uprawnienia IAM konta Vertex AI oraz domyślny tryb prywatny (`RESTRICTED` - tylko dla wdrażającego).
7. **Test 07: Odpowiedź Narzędzia `get_user_daily_utilization`**
   - Sprawdza poprawność generowania dziennej historii utylizacji dla aktywnego użytkownika.
8. **Test 08: Poprawność Zliczania Sesji Deep Research**
   - Weryfikuje izolację sesji i brak double-countingu przy retry zapytań badawczych.
9. **Test 09: Detekcja Generowania Grafik Imagen**
   - Potwierdza poprawność kategoryzacji zapytań generujących obrazy.
10. **Test 10: Zliczanie Utworzonych Agentów i Odrzucanie Błędów**
    - Sprawdza zliczanie zdarzeń `CreateAgent` i odrzucanie operacji zakończonych błędem.
11. **Test 11: Ranking Użytkowników i Trendy Adopcji DAU**
    - Potwierdza agregację danych w narzędziu `get_user_summary` i `get_daily_adoption`.
12. **Test 12: Limity Kwotowe i Headroom w Czasie Rzeczywistym**
    - Weryfikuje odczyt metryk Cloud Monitoring Quotas (RPM, TPM, headroom).
13. **Test 13: Ślady OpenTelemetry, Czasy TTFT i Błędy**
    - Bada czasy odpowiedzi do pierwszego tokena oraz korelacje spanów OTel.
14. **Test 14: Niezmienniki Matematyczne Zdarzeń i Tokenów**
    - Weryfikuje spójność: $\text{Zdarzenia} \ge \text{Zapytania} + \text{Deep Research} + \text{Agenty}$ oraz $\text{Tokeny} = \text{Input} + \text{Output}$.
15. **Test 15: Precyzja Przypisywania Tokenów po Śladach OTel**
    - Sprawdza brak duplikatów w korelacji tabeli wnioskowania modelu z sesjami asystenta.
16. **Test 16: Raportowanie Zerowej Utylizacji (Zero-Utilization Contract)**
    - Potwierdza poprawność kontraktu odpowiedzi dla użytkowników bez zarejestrowanej aktywności.
17. **Test 17: Niewrażliwość Resolwera Silników na Nazewnictwo**
    - Bada elastyczne dopasowywanie silników po `display_name`, pełnym ID, ze spacjami i pustym hincie.
18. **Test 18: Auto-detekcja Projektu GCP ze Środowiska**
    - Potwierdza odporność na brak zmiennych środowiskowych i auto-detekcję z `google.auth.default()`.
19. **Test 19: Odporność na Ewolucję Schematów Payloadów**
    - Weryfikuje parser logów w przypadku braku pól, zagnieżdżonych struktur i wariantów camelCase/lowercase.
20. **Test 20: Niewrażliwość na Konfiguracje Regionalne (eu, global, us)**
    - Sprawdza odporność komunikacji z endpointami regionalnymi Discovery Engine.
21. **Test 21: Reguły AI Governance i Privacy-by-Design**
    - Weryfikuje domyślne `sensitiveLoggingEnabled: True` + Exclusion Filter w Cloud Logging oraz `sharingConfig: RESTRICTED`.
22. **Test 22: Statystyki Wywołań Autorskich Agentów (Self-Usage & Org-Wide Invariants)**
    - Weryfikuje metryki wywołań agentów autora (`author_agent_*`) i organizacji (`org_agent_*`) oraz ich niezmienniki matematyczne.
23. **Test 23: Wyjściowa Propozycja Bottom 10 i Sortowanie Aktywności Użytkowników**
    - Potwierdza sortowanie rosnące (`order_by="bottom"` / `"asc"`), integralność kolumn tabeli wyjściowej oraz instrukcję systemową agenta ADK.

---

## 9. Rozwiązywanie Problemów (Troubleshooting & Self-Healing)

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

### Błąd Cloud Logging Sink: `table_invalid_schema: Cannot convert std::string to a record field ... query = 4`

#### Objaw:
Administrator projektu GCP otrzymuje powiadomienie e-mail:
```text
The following log sink in a project you own had errors while routing logs. Due to this error, logs are not being routed to the sink destination.
Project ID: prj-gemini-rossmann-global
Log Sink Name: gemini-enterprise-telemetry-sink
Sink Destination: bigquery.googleapis.com/projects/.../datasets/gemini_enterprise_telemetry
Error Code: table_invalid_schema
Error Detail: Cannot convert std::string to a record field:optional .Msg_0_CLOUD_QUERY_TABLE.Msg_1_CLOUD_QUERY_TABLE_jsonpayload.Msg_15_CLOUD_QUERY_TABLE_jsonpayload_request.Msg_22_CLOUD_QUERY_TABLE_jsonpayload_request_query query = 4;
```
Routing logów ze zdarzeniami aktywności użytkowników do BigQuery zostaje wstrzymany.

#### Diagnoza i Przyczyna Źródłowa:
W Google Cloud Discovery Engine pod tym samym zbiorem logów (`discoveryengine.googleapis.com/gemini_enterprise_user_activity`) operują dwa różne typy usług:
1. **SearchService** (metody wyszukiwarki: `Search`, `ConverseConversation`, `AnswerQuery`) – pole `query` w protobuf to prosty `std::string`.
2. **AssistantService** (metody Gemini Enterprise / Czat / Agenci: `StreamAssist`, `Assist`) – pole `query` w protobuf to obiekt `RECORD` ze strukturą `parts: repeated struct<text string>`.

BigQuery nie obsługuje unii typów (kolumn polimorficznych) na tym samym polu. Gdy do tabeli z kolumną `RECORD` wpada zapytanie wyszukiwarki (`Search`), Cloud Logging Sink zgłasza błąd `Cannot convert std::string to a record field`. Z kolei gdyby tabela miała typ `STRING`, zdarzenia czatowe `StreamAssist` zostają odrzucone do `export_errors` z błędem `This field: query is not a record`.

#### Rozwiązanie Architektoniczne:
Zastosowano model eliminacji kolizji u źródła (Log Router Sink Filter):
1. **Wykluczenie na zlewie logów (Sink Exclusion)**: Reguła `exclude-search-queries` na zlewie `gemini-enterprise-telemetry-sink` wyklucza zapytania tekstowe `Search`/`ConverseConversation`, które nie wchodzą w skład telemetrii agenta Gemini Enterprise.
2. **Schemat BigQuery**: Tabela `discoveryengine_googleapis_com_gemini_enterprise_user_activity` posiada natywny typ `RECORD` ze strukturą `parts`, co zapewnia 100% bezbłędną rejestrację interakcji asystenta, agentów i powiązanych tokenów LLM.

#### Rozwiązanie Zautomatyzowane (1 komenda – Self-Healing):
W repozytorium dostępny jest dedykowany skrypt autonaprawczy:
```bash
python3 scripts/fix_user_activity_schema.py --project <PROJECT_ID>
```
Skrypt automatycznie:
1. Konfiguruje regułę wykluczenia `exclude-search-queries` na zlewie Cloud Logging.
2. Weryfikuje i dostosowuje tabelę BigQuery do typu `RECORD` (obsługując ewentualne ograniczenia bufora streamingowego).
3. Rekompiluje widoki analityczne w BigQuery.
4. (Opcjonalnie) Umożliwia natychmiastowe wsteczne zaingestowanie danych z ostatnich N dni (`--backfill-days 30`).

Alternatywnie wystarczy uruchomić redeployment (`./deploy.sh <ENGINE_ID>`), który automatycznie zaktualizuje konfigurację zlewu i widoków.


