# <img src="assets/google-cloud.svg" alt="Google Cloud" width="32" height="32" valign="middle"> Gemini Enterprise Telemetry Agent

Gotowe do wdrożenia rozwiązanie do monitorowania, analizy i raportowania telemetrii wykorzystania **Google Cloud Gemini Enterprise** w organizacji.

Pakiet opiera się na oficjalnych mechanizmach obserwowalności platformy (OpenTelemetry, Cloud Audit Logs, Cloud Monitoring Quotas), zdeduplikowanych widokach BigQuery oraz **autonomicznym Agencie ADK**, wdrożonym w **Vertex AI Reasoning Engine** i rejestrowanym w Gemini Enterprise w trybie bezpiecznym (domyślnie dostępnym tylko dla wdrażającego: `RESTRICTED`).

---

## 🚀 Szybki start (wdrożenie w 1 kroku)

Instalator automatycznie konfiguruje wszystkie komponenty end-to-end:

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Uruchom automatyczne wdrożenie ze wskazaniem identyfikatora silnika (Engine ID):
# przykład: ./deploy.sh ge-dprzek_1789915910154 --project ge-test-dprzek --location eu
./deploy.sh <GE_APP_ID - nie mylić z APP_NAME> --project <PROJECT_ID> --location eu

# Wymuszenie ponownego wdrożenia Agenta (np. przy aktualizacji kodu):
./deploy.sh <GE_APP_ID - nie mylić z APP_NAME> --recreate

# Opcjonalnie: udostępnienie Agenta wszystkim użytkownikom w organizacji (ALL_USERS):
# Domyślnie agent jest wdrażany w trybie prywatnym (RESTRICTED - dostępny wyłącznie dla wdrażającego).
# W każdej chwili po wdrożeniu administrator może dodać użytkowników lub grupy w konsoli Gemini Enterprise:
./deploy.sh <GE_APP_ID> --share-with-all-users

# Opcjonalnie: zachowanie treści promptów w Cloud Logging (domyślnie odrzucane przez Exclusion Filter):
./deploy.sh <GE_APP_ID> --keep-raw-prompts

# Opcjonalnie: tryb w pełni anonimowy (Google zamaskuje UPN użytkowników do <elided>):
./deploy.sh <GE_APP_ID> --disable-sensitive-logging
```

> [!IMPORTANT]
> **Izolacja IAM i Bezpieczeństwo Wdrożenia (Domyślny Tryb RESTRICTED)**
> - W momencie wdrożenia Agent **NIE** jest udostępniany grupie *"all users"*.
> - Domyślna konfiguracja `sharingConfig: { "scope": "RESTRICTED" }` sprawia, że wyłącznie osoba wdrażająca posiada dostęp do Agenta Telemetrii.
> - **Elastyczne zarządzanie uprawnieniami**: Po wdrożeniu administrator może w dowolnym momencie w konsoli Google Cloud (*Discovery Engine* $\rightarrow$ *Assistants* $\rightarrow$ *Agents* $\rightarrow$ *Sharing*) udostępnić agenta konkretnym osobom, grupom domenowym Google Workspace/Cloud Identity lub całej organizacji.

> [!IMPORTANT]
> **AI Governance, Ochrona Danych i Data Residency w EU**
> - **Enterprise Governance (Zero Prompt & Zero M365 Storage + Pełna atrybucja UPN)**: Domyślnie instalator konfiguruje silnik z `sensitiveLoggingEnabled: true` (co zapobiega maskowaniu przez Google tożsamości użytkowników do `"<elided>"` w logach aktywności), jednocześnie automatycznie konfigurując **Exclusion Filter** na zlewie `_Default` w Cloud Logging. Dzięki temu:
>   - Treść promptów użytkowników (`gen_ai.user.message`) oraz odpowiedzi i fragmenty dokumentów wewnętrznych M365 / SharePoint / Drive (`gen_ai.choice`) **są natychmiast odrzucane (drop) na bramce Cloud Logging i NIGDY nie trafiają do BigQuery ani do magazynu logów**.
>   - Jednocześnie telemetria, metryki tokenów, opóźnienia i aktywność użytkowników są precyzyjnie przypisywane do konkretnych kont UPN.
> - **Nienaruszalność audytu projektu (`auditConfigs`)**: Skrypt nie modyfikuje polityk IAM projektu GCP i **nie włącza** kosztownych logów `DATA_READ` dla Discovery Engine.
> - **Odporność na błędy schematu zlewu logów (Self-Healing `query: STRING`)**: Instalator automatycznie tworzy i naprawia schemat tabeli aktywności użytkowników, definiując pole `query` jako `STRING` (zamiast `RECORD`), co zapobiega błędowi Cloud Logging `table_invalid_schema` (`Cannot convert std::string to a record field`) i automatycznie radzi sobie z buforem strumieniowym BigQuery.
> - **Suwerenność danych (100% EU Data Residency)**: Przy parametrze `--location eu`, wszystkie zasoby (silnik Gemini w `eu`, zbiór BigQuery w `EU`, Vertex AI Reasoning Engine, model wnioskowania i bucket stagingowy w `europe-west1`) przetwarzają i przechowują dane **wyłącznie w granicach Unii Europejskiej**.

> [!NOTE]
> **Obsługa wielu silników w projekcie (wielość aplikacji)**
> W środowiskach organizacji w jednym projekcie Google Cloud często funkcjonuje wiele silników Gemini Enterprise (np. dla różnych departamentów lub procesów).
> 
> Listę identyfikatorów silników w projekcie można sprawdzić poleceniem:
> ```bash
> gcloud discovery-engine engines list --location=eu
> ```
> Jeśli w projekcie skonfigurowano kilka silników, instalator wymaga wskazania docelowego `<ID_SILNIKA>` (jako argument pozycyjny, np. `./deploy.sh <ID_SILNIKA>`). W przypadku uruchomienia bez parametrów w środowisku z wieloma silnikami, skrypt wylistuje wszystkie wykryte silniki wraz z ich identyfikatorami.

> [!TIP]
> **Co automatyzuje instalator?**
> - Włącza `observabilityConfig` w silniku Gemini z zachowaniem Enterprise Governance.
> - Konfiguruje Exclusion Filter w Cloud Logging odrzucający surowe prompty i fragmenty M365.
> - Tworzy zbiór danych BigQuery w lokalizacji `EU`, zlew logów i nadaje uprawnienia IAM.
> - Przeprowadza idempotentny backfill historii i kompiluje zdeduplikowane widoki SQL.
> - Tworzy dashboard operacyjny w Cloud Monitoring.
> - Buduje i wdraża agenta ADK do Vertex AI Reasoning Engine w regionie `europe-west1` oraz rejestruje go w aplikacji w trybie prywatnym (`RESTRICTED` - dostęp ma tylko wdrażający; opcjonalnie `--share-with-all-users`).

Szczegółowy podręcznik procedur wdrożeniowych krok po kroku znajduje się w [MANUAL.md](MANUAL.md).

---

## 💬 O co możesz zapytać agenta? (przykładowe prompty)

Agent telemetrii (`Gemini Enterprise Telemetry & Adoption Agent`) korzysta z dynamicznych narzędzi Python i bezpośrednio odpytuje BigQuery oraz Cloud Monitoring API w czasie rzeczywistym. Możesz rozmawiać z nim w języku naturalnym:

### 🎯 Domyślna propozycja startowa i analiza adopcji (Bottom 10)
### 🎯 Domyślna propozycja startowa i analiza adopcji (Bottom 10)
- *"Dzień dobry / Cześć"* — Agent wita oficjalnym oświadczeniem o oferowanych metrykach i jako **wyjściową propozycję startową** natychmiast generuje tabelę **10 najmniej aktywnych użytkowników (Bottom 10)** w organizacji ze szczegółowymi statystykami użycia platformy, ułatwiając identyfikację obszarów wymagających szkoleń lub onboardingu. Tabela zawiera 10 spójnych kolumn:
  `| Użytkownik | Zapytania asystenta (czat) | Zadań Deep Research | Wygenerowane obrazy | Utworzone agenty | Edycje agentów (agent_updates) | Odsłony agentów (agent_views) | Czaty z agentami użytkownika (author_agent_sessions) | Czaty z agentami użytkownika (org_agent_sessions) | Konsumpcja tokenów |`
- *"Pokaż najmniej aktywnych użytkowników (Bottom 10) ze statystykami użycia platformy."*
- *"Którzy pracownicy potrzebują wsparcia adopcyjnego lub szkoleń z Gemini Enterprise?"*
- *"Ilu użytkowników w ogóle nie korzysta z platformy (zerowa utylizacja)?"*

### 🤖 Autorskie agenty użytkowników (dwufazowy cykl życia i użycie własne vs organizacja)
- *"Ile razy jan.kowalski@twoja-firma.com modyfikował i iterował prompt swojego agenta w edytorze (`agent_updates`)?"*
- *"Ile razy wyświetlano kartę/profil agenta użytkownika (`agent_views`)?"*
- *"Ile razy jan.kowalski@twoja-firma.com korzystał ze swoich agentów biznesowych, a ile razy używali ich inni pracownicy w organizacji?"*
- *"W ilu sesjach/czatach autor używał własnych agentów, a w ilu cała organizacja?"*
- *"Pokaż statystyki wywołań agentów stworzonych przez zespół analityczny w podziale na sesje autora i organizacji."*

### 👤 Aktywność i utylizacja użytkowników
- *"Przedstaw aktywność użytkownika jan.kowalski@twoja-firma.com z ostatnich 14 dni z rozbiciem na poszczególne dni."*
- *"Ile zapytań i tokenów zużył jan.kowalski@twoja-firma.com w tym tygodniu?"*
- *"Kiedy użytkownik jan.kowalski@twoja-firma.com wykonał swoje pierwsze i ostatnie zapytanie?"*

### 🎨 Moduły i funkcje (Deep Research, obrazy, agenty)
- *"Ile badań Deep Research przeprowadzono w organizacji w tym miesiącu i kto je uruchamiał?"*
- *"Ile grafik wygenerowano za pomocą modeli graficznych w ostatnich 7 dniach?"*
- *"Pokaż listę użytkowników, którzy stworzyli własne agenty w Agent Designerze."*

### 📈 Adopcja i trendy w organizacji
- *"Pokaż ranking 5 najbardziej aktywnych użytkowników platformy pod względem zapytań i tokenów."*
- *"Jak kształtuje się wskaźnik DAU (Daily Active Users) w ciągu ostatnich 30 dni?"*
- *"Jak wygląda łączna dynamika zapytań i wolumenu tokenów w porównaniu do ubiegłego tygodnia?"*

---

## 📊 Śledzone metryki

> [!NOTE]
> **Dwufazowy Model Cyklu Życia Agenta: Prototypowanie vs Konsumpcja Produkcyjna**
> 1. **Faza Prototypowania (Agent Prototyping - stan `PRIVATE`)**:
>    - Gdy użytkownik tworzy agenta w Agent Designerze, testowe tury w podglądzie są traktowane przez platformę Google jako wewnętrzny sandbox roboczy (niegenerujący zdarzeń produkcyjnych `StreamAssist`).
>    - Zaangażowanie twórcy w tej fazie jest mierzone poprzez: **`agents_created`** (utworzenie agenta), **`agent_updates`** (liczba edycji, iteracji instrukcji i promptu) oraz **`agent_views`** (otwarcia profilu agenta).
> 2. **Faza Konsumpcji Produkcyjnej (Agent Consumption - stan `ENABLED` / udostępniony organizacji)**:
>    - Po opublikowaniu agenta tury dialogowe trafiają do audytowanego strumienia asystenta i są raportowane w metrykach: **`author_agent_sessions`** (czaty autora z własnym agentem) oraz **`org_agent_sessions`** (czaty wszystkich pracowników z agentem).
> 3. **Wykluczenie Agenta Telemetrycznego**:
>    - Zapytania administracyjne do systemowego Agenta Telemetrii są wykluczone z `author_agent_sessions`, dzięki czemu odpytywanie o raporty nie zawyża sztucznie statystyk użycia agentów biznesowych twórcy.

> [!TIP]
> **Formalizacja pojęć: Zapytania / Wywołania (`queries` / `invocations`) vs Czaty / Sesje (`sessions`)**
> - **Zapytania / Wywołania (Invocations / Queries)**: Pojedyncze interakcje (prompty/requesty) przesłane przez użytkownika do asystenta lub agenta w ramach dialogu.
> - **Czaty / Sesje (Sessions)**: Kompletne wątki konwersacyjne (ciągłe dyskusje), które mogą obejmować od jednej do wielu tur dialogowych. W naturalny sposób liczba zapytań jest zawsze równa lub większa od liczby sesji ($N_{\text{queries}} \ge N_{\text{sessions}}$).

| Kategoria (Kolumna Tabeli) | Mierzone wymiary i definicja | Źródło danych |
| :--- | :--- | :--- |
| **Zapytania asystenta (czat)** | Zapytania czatu ogólnego (z wykluczeniem wywołań customowych agentów i Deep Research) | BigQuery (`is_assistant_query`) |
| **Zadań Deep Research** | Unikalne sesje wieloetapowego badania rynku i syntezy wiedzy | BigQuery (`agents/deep_research`) |
| **Wygenerowane obrazy** | Liczba wygenerowanych grafik i zdjęć (modele Imagen) | BigQuery (`is_image_generation`) |
| **Utworzone agenty** | Liczba autorskich agentów stworzonych w Agent Designerze (tylko udane: `status.code = 0`) | Cloud Audit Logs (`CreateAgent`) |
| **Edycje agentów (agent_updates)** | Liczba zapisanych iteracji i modyfikacji konfiguracji/promptu agenta w Agent Designerze | BigQuery & Audit (`UpdateAgent`) |
| **Odsłony agentów (agent_views)** | Liczba wyświetleń i wejść na profil/widok agenta w portalu | BigQuery (`WriteUserEvent` - `page_type = 'agent'`) |
| **Czaty z agentami użytkownika (author_agent_sessions)** | W ilu dyskusjach/sesjach autor korzystał ze stworzonych przez siebie agentów (Self-Usage; bez Agenta Telemetrii) | BigQuery (`v_author_agent_usage`) |
| **Czaty z agentami użytkownika (org_agent_sessions)** | W ilu dyskusjach/sesjach agenci stworzeni przez autora byli wywoływani w całej organizacji (autor + inni pracownicy) | BigQuery (`v_author_agent_usage`) |
| **Wywołania agentów (invocations)** | Łączna liczba promptów wysłanych do agentów autora: `author_agent_invocations` oraz `org_agent_invocations` | BigQuery (`v_author_agent_usage`) |
| **Konsumpcja tokenów** | Wolumen tokenów wejściowych (prompt), wyjściowych (odpowiedź) i całkowitych (`total_tokens`) | BigQuery (`gen_ai_client_inference`) |
| **Adopcja UX** | Wskaźniki DAU / WAU / MAU, retencja użytkowników i głębokość konwersacji | BigQuery (`v_daily_adoption`) |
| **Limity kwotowe** | Pule dzienne: zapytania, agenty, deep research, WTU developerów, storage | Cloud Monitoring (`quota/*`) |
| **Wydajność i obserwowalność** | Czas do 1. tokena (TTFT), spany OTel (`StreamAssist`), statusy RPC | Cloud Trace & Audit Logs |

---

## 🏛️ Architektura w pigułce

```
[Gemini Enterprise Engine] (OpenTelemetry + Audit Logs)
           │
           ├─► Cloud Logging Sink ──► BigQuery (Partycjonowane tabele & 7 widoków SQL)
           ├─► Cloud Monitoring   ──► Quotas API, TTFT, Sesje & Dashboard
           │
           └─► Vertex AI Reasoning Engine (ADK Agent: gemini-2.5-flash)
                    │
                    └─► Gemini Enterprise Assistant (Domyślnie: RESTRICTED / opcjonalnie ALL_USERS)
```

1. **Brak parsowania tekstu regexem**: Zdarzenia i tokeny są ściśle powiązane po natywnych identyfikatorach śladów OpenTelemetry (`trace_id`, `span_id`).
2. **Matematyczna integralność (zero double-counting)**: Klauzule `QUALIFY ROW_NUMBER() ...` gwarantują eliminację duplikatów i iloczynów kartezjańskich.
3. **Czystość statystyk adopcji**: Widoki automatycznie odrzucają wewnętrzne konta systemowe platformy Google Cloud (`@gcp-sa-*.iam.gserviceaccount.com`), dzięki czemu raporty i rankingi prezentują wyłącznie rzeczywistych pracowników.
4. **Idempotentność i Self-Healing**: Wszystkie operacje są w pełni powtarzalne bez duplikacji danych, a instalator aktywnie testuje kondycję Reasoning Engine przed rejestracją w Gemini Enterprise.

---

## 🔍 Widoki analityczne w BigQuery (`gemini_enterprise_telemetry`)

- **`v_user_daily_utilization`** — Dzienny profil utylizacji per użytkownik (zapytania, obrazy, badania, agenty, wywołania autorskich agentów, błędy, tokeny wejścia/wyjścia/cache).
- **`v_author_agent_usage`** — Wywołania agentów stworzonych przez danego użytkownika w dwóch ujęciach:
  1. **Self-usage (autor)**: ile razy autor rozmawiał ze swoimi agentami (`author_agent_invocations`) i w ilu dyskusjach/sesjach (`author_agent_sessions`).
  2. **Org-wide (cała organizacja)**: łączna liczba wywołań (`org_agent_invocations`), dyskusji/sesji (`org_agent_sessions`) oraz unikalnych użytkowników (`org_agent_unique_callers`).
- **`v_daily_adoption`** — Globalne trendy organizacji: DAU, łączna liczba akcji, zapytań, wywołań customowych agentów, tokenów i unikalnych użytkowników.
- **`v_user_summary`** — Zagregowane statystyki całokształtu aktywności per użytkownik (do rankingów i audytu).
- **`v_feature_usage`** — Wykorzystanie poszczególnych modułów (Czat, Deep Research, Modele graficzne, Agent Designer).
- **`v_observability_traces`** — Rozproszone ślady OpenTelemetry, korelacja spanów i czasy odpowiedzi.
- **`v_token_telemetry`** — Szczegółowe metryki zużycia tokenów modeli językowych.

---

## 👥 Uprawnienia IAM dla użytkowników

Aby użytkownicy w organizacji mogli korzystać z Agenta Telemetrii w portalu Gemini Enterprise, wystarczy nadać im role dostępowe do aplikacji:

```bash
# Dla pojedynczego użytkownika:
gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="user:uzytkownik@twoja-firma.com" \
    --role="roles/discoveryengine.user"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="user:uzytkownik@twoja-firma.com" \
    --role="roles/discoveryengine.agentspaceUser"
```

---

## 📁 Struktura repozytorium

```text
gemini-enterprise-telemetry/
├── deploy.sh                   # Szybki skrypt uruchomieniowy (auto-instalacja zależności)
├── deploy.py                   # Główny zintegrowany instalator Zero-Touch
├── requirements.txt            # Precyzyjne zależności wykonawcze środowiska
├── MANUAL.md                   # Podręcznik wdrożeniowy dla administratorów
├── bigquery/
│   └── telemetry_views.sql     # 7 analitycznych widoków SQL (w tym v_author_agent_usage)
├── agent/
│   ├── adk_telemetry_agent.py  # Kod Agenta ADK i definicje narzędzi
│   └── deploy_adk_agent.py     # Wdrożenie do Vertex AI Reasoning Engine (z health-checkiem)
├── cli/
│   ├── telemetry_service.py    # Warstwa dostępu do danych (BigQuery/Monitoring)
│   └── telemetry_cli.py        # Narzędzie konsolowe CLI
├── scripts/
│   ├── backfill_logs_to_bigquery.py  # Idempotentny backfill historii logów
│   ├── fix_user_activity_schema.py   # Narzędzie naprawy schematu BigQuery (Self-Healing query: STRING)
│   └── simulate_mock_user_activity.py # Symulacja aktywności testowej
├── monitoring/
│   └── gemini_enterprise_telemetry_dashboard.json # Definicja dashboardu Cloud Monitoring
├── terraform/                  # Opcjonalne wdrożenie Infrastructure-as-Code
└── tests/
    └── test_suite.py           # Zestaw testów jednostkowych i integracyjnych (24 testy)
```

---

## Licencja

Apache License 2.0. Szczegóły w pliku [LICENSE](LICENSE).
