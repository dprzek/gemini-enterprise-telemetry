# Gemini Enterprise Telemetry & Adoption

Gotowe do wdrożenia rozwiązanie do monitorowania, analizy i raportowania telemetrii wykorzystania **Google Cloud Gemini Enterprise** w organizacji.

Pakiet opiera się na oficjalnych mechanizmach obserwowalności platformy (OpenTelemetry, Cloud Audit Logs, Cloud Monitoring Quotas), zdeduplikowanych widokach BigQuery oraz **autonomicznym Agencie ADK**, wdrożonym w **Vertex AI Reasoning Engine** i dostępnym bezpośrednio dla użytkowników w Gemini Enterprise (`ALL_USERS`).

---

## 🚀 Szybki Start (Wdrożenie w 1 kroku)

Instalator automatycznie konfiguruje wszystkie komponenty end-to-end:

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Uruchom automatyczne wdrożenie
./deploy.sh <NAZWA_LUB_ID_APLIKACJI>

# Przykład ze wskazaniem projektu i lokalizacji:
./deploy.sh gemini-test-123 --project test-ge-demos --location eu
```

> [!TIP]
> **Co automatyzuje instalator?**
> - Włącza `observabilityConfig` (OpenTelemetry + logowanie) w silniku Gemini.
> - Tworzy zbiór danych BigQuery, zlew logów i nadaje wymagane uprawnienia IAM.
> - Przeprowadza idempotentny backfill historii i kompiluje zdeduplikowane widoki SQL.
> - Tworzy dashboard operacyjny w Cloud Monitoring.
> - Buduje i wdraża Agenta ADK do Vertex AI Reasoning Engine oraz publikuje go w aplikacji (`ALL_USERS`).

Szczegółowy podręcznik procedur wdrożeniowych krok po kroku znajduje się w [MANUAL.md](MANUAL.md).

---

## 💬 O co możesz zapytać Agenta? (Przykładowe Prompty)

Agent telemetrii (`Gemini Enterprise Telemetry & Adoption Agent`) korzysta z dynamicznych narzędzi Python i bezpośrednio odpytuje BigQuery oraz Cloud Monitoring API w czasie rzeczywistym. Możesz rozmawiać z nim w języku naturalnym:

### 👤 Aktywność i Utylizacja Użytkowników
- *"Przedstaw aktywność użytkownika jan.kowalski@twoja-firma.com z ostatnich 14 dni z rozbiciem na poszczególne dni."*
- *"Ile zapytań i tokenów zużył mock-analyst-user@test-ge-demos.iam.gserviceaccount.com w tym tygodniu?"*
- *"Kiedy użytkownik anna.nowak@twoja-firma.com wykonał swoje pierwsze i ostatnie zapytanie?"*

### 🎨 Moduły i Funkcje (Deep Research, Obrazy, Agenty)
- *"Ile badań Deep Research przeprowadzono w organizacji w tym miesiącu i kto je uruchamiał?"*
- *"Ile grafik wygenerowano za pomocą modeli Imagen w ostatnich 7 dniach?"*
- *"Pokaż listę użytkowników, którzy stworzyli własne agenty w Agent Designerze."*

### 📈 Adopcja i Trendy w Organizacji
- *"Pokaż ranking 5 najbardziej aktywnych użytkowników platformy pod względem zapytań i tokenów."*
- *"Jak kształtuje się wskaźnik DAU (Daily Active Users) w ciągu ostatnich 30 dni?"*
- *"Jak wygląda łączna dynamika zapytań i wolumenu tokenów w porównaniu do ubiegłego tygodnia?"*

### ⏱️ Limity Kwotowe i Stabilność Platformy
- *"Jaki jest bieżący stan limitów kwotowych (quotas) i czy zbliżamy się do limitów organizacji?"*
- *"Czy w ostatnich 24 godzinach odnotowano błędy zapytań lub anomalie czasów odpowiedzi (TTFT)?"*

---

## 📊 Śledzone Metryki

| Kategoria | Mierzone Wymiary | Źródło Danych |
| :--- | :--- | :--- |
| **Zapytania i Czat** | Wolumen promptów, odpowiedzi, głębokość konwersacji (tury/sesję) | BigQuery + Cloud Monitoring |
| **Deep Research** | Unikalne sesje wieloetapowego badania rynku/wiedzy | BigQuery (`agents/deep_research`) |
| **Generowanie Obrazów** | Liczba wygenerowanych grafik Imagen | BigQuery (`is_image_generation`) |
| **Tworzenie Agentów** | Liczba utworzonych i edytowanych agentów customowych | Cloud Audit Logs (`CreateAgent`) |
| **Konsumpcja Tokenów** | Tokeny wejściowe (prompt), wyjściowe i buforowane (cache) | BigQuery (`gen_ai_client_inference`) |
| **Adopcja UX** | Wskaźniki DAU / WAU / MAU, retencja użytkowników | BigQuery (`v_daily_adoption`) |
| **Limity Kwotowe** | Zapytania, agenty, deep research, WTU developerów, storage | Cloud Monitoring (`quota/*`) |
| **Wydajność i Błędy** | Czas do 1. tokena (TTFT), spany OTel, kody HTTP / statusy RPC | Cloud Trace & Audit Logs |

---

## 🏛️ Architektura w Pigułce

```
[Gemini Enterprise Engine] (OpenTelemetry + Audit Logs)
           │
           ├─► Cloud Logging Sink ──► BigQuery (Partycjonowane tabele & 6 widoków SQL)
           ├─► Cloud Monitoring   ──► Quotas API, TTFT, Sesje & Dashboard
           │
           └─► Vertex AI Reasoning Engine (ADK Agent: gemini-2.5-flash)
                    │
                    └─► Gemini Enterprise Assistant (Współdzielenie: ALL_USERS)
```

1. **Brak Parsowania Regexem Tekstu**: Zdarzenia i tokeny są ściśle powiązane po natywnych identyfikatorach śladów OpenTelemetry (`trace_id`, `span_id`).
2. **Matematyczna Integralność (Zero Double-Counting)**: Klauzule `QUALIFY ROW_NUMBER() ...` gwarantują eliminację duplikatów i iloczynów kartezjańskich.
3. **Idempotentność**: Każdy komponent instalatora oraz skryptu wstecznej ingestji (`backfill`) może być uruchamiany wielokrotnie bez powielania danych.

---

## 🔍 Widoki Analityczne w BigQuery (`gemini_enterprise_telemetry`)

- **`v_user_daily_utilization`** — Dzienny profil utylizacji per użytkownik (zapytania, obrazy, badania, agenty, błędy, tokeny wejścia/wyjścia/cache).
- **`v_daily_adoption`** — Globalne trendy organizacji: DAU, łączna liczba akcji, zapytań, tokenów i unikalnych użytkowników.
- **`v_user_summary`** — Zagregowane statystyki całokształtu aktywności per użytkownik (do rankingów i audytu).
- **`v_feature_usage`** — Wykorzystanie poszczególnych modułów (Czat, Deep Research, Imagen, Agent Designer).
- **`v_observability_traces`** — Rozproszone ślady OpenTelemetry, korelacja spanów i czasy odpowiedzi.
- **`v_token_telemetry`** — Szczegółowe metryki zużycia tokenów modeli językowych.

---

## 👥 Uprawnienia IAM dla Użytkowników

Aby użytkownicy w organizacji mogli korzystać z Agenta Telemetrii w portalu Gemini Enterprise, wystarczy nadać im role dostępowe do aplikacji:

```bash
# Dla pojedynczego użytkownika:
gcloud projects add-iam-policy-binding <PROJECT_ID>     --member="user:uzytkownik@twoja-firma.com"     --role="roles/discoveryengine.user"

gcloud projects add-iam-policy-binding <PROJECT_ID>     --member="user:uzytkownik@twoja-firma.com"     --role="roles/discoveryengine.agentspaceUser"
```

---

## 📁 Struktura Repozytorium

```text
gemini-enterprise-telemetry/
├── deploy.sh                   # Szybki skrypt uruchomieniowy
├── deploy.py                   # Główny zintegrowany instalator Zero-Touch
├── MANUAL.md                   # Podręcznik wdrożeniowy dla administratorów
├── bigquery/
│   └── telemetry_views.sql     # 6 analitycznych widoków SQL
├── agent/
│   ├── adk_telemetry_agent.py  # Kod Agenta ADK i definicje narzędzi
│   └── deploy_adk_agent.py     # Wdrożenie do Vertex AI Reasoning Engine
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
    └── test_suite.py           # Zestaw 15 zautomatyzowanych testów E2E
```

---

## Licencja

Apache License 2.0. Szczegóły w pliku [LICENSE](LICENSE).
