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
# Domyślnie agent jest widoczny tylko dla osoby wdrażającej (RESTRICTED):
./deploy.sh <GE_APP_ID> --share-with-all-users

# Opcjonalnie: zachowanie treści promptów w Cloud Logging (domyślnie odrzucane przez Exclusion Filter):
./deploy.sh <GE_APP_ID> --keep-raw-prompts

# Opcjonalnie: tryb w pełni anonimowy (Google zamaskuje UPN użytkowników do <elided>):
./deploy.sh <GE_APP_ID> --disable-sensitive-logging
```

> [!IMPORTANT]
> **AI Governance, Ochrona Danych i Data Residency w EU**
> - **Enterprise Governance (Zero Prompt & Zero M365 Storage + Pełna atrybucja UPN)**: Domyślnie instalator konfiguruje silnik z `sensitiveLoggingEnabled: true` (co zapobiega maskowaniu przez Google tożsamości użytkowników do `"<elided>"` w logach aktywności), jednocześnie automatycznie konfigurując **Exclusion Filter** na zlewie `_Default` w Cloud Logging. Dzięki temu:
>   - Treść promptów użytkowników (`gen_ai.user.message`) oraz odpowiedzi i fragmenty dokumentów wewnętrznych M365 / SharePoint / Drive (`gen_ai.choice`) **są natychmiast odrzucane (drop) na bramce Cloud Logging i NIGDY nie trafiają do BigQuery ani do magazynu logów**.
>   - Jednocześnie telemetria, metryki tokenów, opóźnienia i aktywność użytkowników są precyzyjnie przypisywane do konkretnych kont UPN.
> - **Nienaruszalność audytu projektu (`auditConfigs`)**: Skrypt nie modyfikuje polityk IAM projektu GCP i **nie włącza** kosztownych logów `DATA_READ` dla Discovery Engine.
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

| Kategoria | Mierzone wymiary | Źródło danych |
| :--- | :--- | :--- |
| **Zapytania i czat** | Wolumen promptów, odpowiedzi, głębokość konwersacji (tury/sesję) | BigQuery + Cloud Monitoring |
| **Deep Research** | Unikalne sesje wieloetapowego badania rynku/wiedzy | BigQuery (`agents/deep_research`) |
| **Generowanie obrazów** | Liczba wygenerowanych grafik (modele graficzne) | BigQuery (`is_image_generation`) |
| **Tworzenie agentów** | Liczba utworzonych i edytowanych agentów customowych | Cloud Audit Logs (`CreateAgent`) |
| **Konsumpcja tokenów** | Tokeny wejściowe (prompt), wyjściowe i buforowane (cache) | BigQuery (`gen_ai_client_inference`) |
| **Adopcja UX** | Wskaźniki DAU / WAU / MAU, retencja użytkowników | BigQuery (`v_daily_adoption`) |
| **Limity kwotowe** | Zapytania, agenty, deep research, WTU developerów, storage | Cloud Monitoring (`quota/*`) |
| **Wydajność i błędy** | Czas do 1. tokena (TTFT), spany OTel, kody HTTP / statusy RPC | Cloud Trace & Audit Logs |

---

## 🏛️ Architektura w pigułce

```
[Gemini Enterprise Engine] (OpenTelemetry + Audit Logs)
           │
           ├─► Cloud Logging Sink ──► BigQuery (Partycjonowane tabele & 6 widoków SQL)
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

- **`v_user_daily_utilization`** — Dzienny profil utylizacji per użytkownik (zapytania, obrazy, badania, agenty, błędy, tokeny wejścia/wyjścia/cache).
- **`v_daily_adoption`** — Globalne trendy organizacji: DAU, łączna liczba akcji, zapytań, tokenów i unikalnych użytkowników.
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
│   └── telemetry_views.sql     # 6 analitycznych widoków SQL
├── agent/
│   ├── adk_telemetry_agent.py  # Kod Agenta ADK i definicje narzędzi
│   └── deploy_adk_agent.py     # Wdrożenie do Vertex AI Reasoning Engine (z health-checkiem)
├── cli/
│   ├── telemetry_service.py    # Warstwa dostępu do danych (BigQuery/Monitoring)
│   └── telemetry_cli.py        # Narzędzie konsolowe CLI
├── scripts/
│   ├── backfill_logs_to_bigquery.py  # Idempotentny backfill historii logów
│   └── simulate_mock_user_activity.py # Symulacja aktywności testowej
├── monitoring/
│   └── gemini_enterprise_telemetry_dashboard.json # Definicja dashboardu Cloud Monitoring
├── terraform/                  # Opcjonalne wdrożenie Infrastructure-as-Code
└── tests/
    └── test_suite.py           # Zestaw testów jednostkowych i integracyjnych
```

---

## Licencja

Apache License 2.0. Szczegóły w pliku [LICENSE](LICENSE).
