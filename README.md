# <img src="assets/google-cloud.svg" alt="Google Cloud" width="32" height="32" valign="middle"> Gemini Enterprise Telemetry Agent

Kompletne, produkcyjne rozwiązanie do monitorowania, analizy i raportowania telemetrii wykorzystania **Google Cloud Gemini Enterprise** w organizacji.

Pakiet opiera się na oficjalnych mechanizmach platformy (OpenTelemetry, Cloud Audit Logs, Cloud Monitoring Quotas), zdeduplikowanych widokach BigQuery, bezserwerowym mikroserwisie na **Cloud Run** oraz autonomicznym agencie ADK wdrożonym w **Vertex AI Reasoning Engine** (domyślnie w bezpiecznym trybie `RESTRICTED`).

---

## 🚀 Szybki start (wdrożenie w 1 kroku)

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Uruchom automatyczne wdrożenie:
./deploy.sh <ID_SILNIKA> --project <PROJECT_ID> --location eu

# Opcjonalne flagi:
./deploy.sh <ID_SILNIKA> --recreate              # Wymuszenie ponownej kompilacji Agenta w Vertex AI
./deploy.sh <ID_SILNIKA> --share-with-all-users  # Udostępnienie agenta w portalu całej organizacji (domyślnie: RESTRICTED)
./deploy.sh <ID_SILNIKA> --keep-raw-prompts      # Zachowanie pełnych promptów w Cloud Logging (domyślnie: Exclusion Filter)
./deploy.sh <ID_SILNIKA> --skip-auto-observability # Pominięcie automatu Cloud Run dla nowych agentów
```

---

## 🏛️ Architektura i Komponenty

```text
[Gemini Enterprise Engine] (OpenTelemetry + Audit Logs)
           │
           ├─► Cloud Logging Sink ────► BigQuery (gemini_enterprise_telemetry: 7 widoków SQL)
           ├─► Cloud Logging Audit ───► Pub/Sub ──► Cloud Run (Auto-Observability Enabler)
           ├─► Cloud Monitoring    ───► Quotas API, TTFT, Sesje & Dashboard operacyjny
           │
           └─► Vertex AI Reasoning Engine (ADK Agent: gemini-2.5-flash)
                    │
                    └─► Gemini Enterprise Assistant (Prywatny: RESTRICTED lub ALL_USERS)
```

1. **Cloud Run (`ge-auto-observability-enabler`)**:
   - Bezserwerowa funkcja Cloud Run (2nd gen) podłączona przez Pub/Sub pod zdarzenia audytowe `AgentService.CreateAgent`.
   - **Automatyzacja**: w czasie rzeczywistym włącza flagę `observabilityEnabled: true` dla każdego nowo utworzonego customowego agenta Low-Code, gwarantując pomiar 100% adopcji bez interwencji administratora.
   - **Wsteczna synchronizacja**: przy instalacji weryfikuje i uaktualnia wszystkich istniejących agentów w silniku.
   - **Koszt**: **$0.00 / mc** (skalowanie do zera, w 100% mieści się w pakiecie GCP Always Free Tier).

2. **Vertex AI Reasoning Engine**:
   - Bezpieczne środowisko wykonawcze dla Agenta ADK (`adk_telemetry_agent.py`), łączące model `gemini-2.5-flash` z dynamicznymi narzędziami analitycznymi BigQuery i Cloud Monitoring.

3. **BigQuery & Cloud Logging**:
   - Dedykowany zbiór danych w regionie `EU` z partycjonowanymi tabelami oraz 7 zoptymalizowanymi widokami SQL eliminującymi duplikaty (`QUALIFY ROW_NUMBER()`).
   - Brak parsowania tekstu wyrażeniami regularnymi — ścisłe powiązanie po unikalnych kluczach OpenTelemetry (`trace_id`, `session_id`).

---

## 🛡️ AI Governance, Bezpieczeństwo i Idempotencja

- **Enterprise Governance (Zero Prompt & Zero M365 Storage + Pełna atrybucja UPN)**:
  Instalator aktywuje `sensitiveLoggingEnabled: true` na silniku (co zapobiega anonimizacji UPN do `<elided>`), jednocześnie konfigurując **Exclusion Filter** na zlewie `_Default` w Cloud Logging. Treści promptów (`gen_ai.user.message`) oraz odpowiedzi i fragmenty dokumentów M365/SharePoint/Drive (`gen_ai.choice`) **są odrzucane na bramce Logging i nie trafiają do BigQuery**.
- **Izolacja IAM (Domyślny Tryb RESTRICTED)**:
  Wdrożony agent telemetrii jest prywatny (`sharingConfig: RESTRICTED`) — dostęp ma wyłącznie wdrażający. W dowolnej chwili można go udostępnić w konsoli lub flagą `--share-with-all-users`.
- **Pełna Idempotencja (CI/CD Ready)**:
  Skrypt można bezpiecznie uruchamiać wielokrotnie na tym samym projekcie:
  - Weryfikuje istnienie zasobów GCP (`describe`) przed ich utworzeniem.
  - Nadawanie uprawnień IAM (`add-iam-policy-binding`) jest z natury bezkonfliktowe.
  - Nowe wdrożenia Cloud Run Function tworzą kolejne bezprzerwowe rewizje.
  - Wykrywa zdrowy kontener Vertex AI Reasoning Engine i unika zbędnego przebudowywania.
  - Mechanizm Self-Healing automatycznie zapobiega kolizjom schematu tabel BigQuery (`query: STRING`).

---

## 💬 Przykładowe zapytania do Agenta

Agent telemetrii odpytuje BigQuery i Cloud Monitoring w czasie rzeczywistym. Przykładowe pytania:

- **Propozycja startowa (Bottom 10 adopcji)**:
  - *"Dzień dobry"* — Agent wita oświadczeniem o metrykach i generuje tabelę 10 najmniej aktywnych użytkowników w organizacji do onboardingu.
  - *"Pokaż najmniej aktywnych użytkowników (Bottom 10) ze statystykami użycia platformy."*
- **Autorskie agenty użytkowników (dwufazowy cykl życia)**:
  - *"Ile razy jan.kowalski@twoja-firma.com edytował prompt swojego agenta w edytorze (`agent_updates`)?"*
  - *"W ilu sesjach autor używał własnych agentów (`author_agent_sessions`), a w ilu inni pracownicy (`org_agent_sessions`)?"*
- **Utylizacja użytkowników i trendy**:
  - *"Przedstaw aktywność jan.kowalski@twoja-firma.com z ostatnich 14 dni z rozbiciem na dni."*
  - *"Ile badań Deep Research i wygenerowanych grafik odnotowano w tym miesiącu?"*
  - *"Jak kształtuje się wskaźnik DAU i konsumpcja tokenów w porównaniu do ubiegłego tygodnia?"*

---

## 📊 Śledzone metryki w BigQuery (`gemini_enterprise_telemetry`)

| Kategoria (Kolumna) | Mierzone wymiary i definicja | Źródło danych |
| :--- | :--- | :--- |
| **Zapytania asystenta (czat)** | Zapytania czatu ogólnego (bez wywołań customowych agentów i Deep Research) | BigQuery (`is_assistant_query`) |
| **Zadań Deep Research** | Unikalne sesje wieloetapowego badania rynku i syntezy wiedzy | BigQuery (`agents/deep_research`) |
| **Wygenerowane obrazy** | Liczba wygenerowanych grafik i zdjęć (modele Imagen) | BigQuery (`is_image_generation`) |
| **Utworzone agenty** | Liczba pomyślnie stworzonych agentów w Agent Designerze | Cloud Audit Logs (`CreateAgent`) |
| **Edycje agentów (agent_updates)** | Liczba zapisanych iteracji i modyfikacji promptu agenta w edytorze | BigQuery & Audit (`UpdateAgent`) |
| **Odsłony agentów (agent_views)** | Liczba wyświetleń profilu/karty agenta w portalu | BigQuery (`WriteUserEvent`) |
| **Czaty z agentami autora (`author_agent_sessions`)** | W ilu sesjach autor korzystał ze swoich agentów (bez Agenta Telemetrii) | BigQuery (`v_author_agent_usage`) |
| **Czaty z agentami w org (`org_agent_sessions`)** | W ilu sesjach agenci autora byli wywoływani przez wszystkich pracowników | BigQuery (`v_author_agent_usage`) |
| **Konsumpcja tokenów** | Wolumen tokenów promptu, odpowiedzi i całkowitych (`total_tokens`) | BigQuery (`gen_ai_client_inference`) |
| **Adopcja & Quotas** | DAU/WAU/MAU, retencja, pule kwotowe i czas do 1. tokena (TTFT) | Cloud Monitoring & Trace |

---

## 📁 Struktura repozytorium

```text
gemini-enterprise-telemetry/
├── deploy.sh                   # Szybki skrypt uruchomieniowy
├── deploy.py                   # Główny zintegrowany instalator Zero-Touch (kroki 1-8)
├── MANUAL.md                   # Kompletny podręcznik dla administratorów
├── agent/
│   ├── adk_telemetry_agent.py  # Kod Agenta ADK i definicje narzędzi
│   └── deploy_adk_agent.py     # Wdrożenie do Vertex AI Reasoning Engine
├── functions/
│   └── auto_observability_enabler/ # Cloud Run Function automatyzująca obserwowalność agentów
│       ├── main.py
│       └── requirements.txt
├── scripts/
│   ├── setup_auto_observability.py # Moduł instalacji Cloud Run i zdarzeń Pub/Sub
│   ├── backfill_logs_to_bigquery.py # Idempotentny backfill historii logów
│   └── fix_user_activity_schema.py  # Samonaprawa schematu tabeli BigQuery
├── bigquery/
│   └── telemetry_views.sql     # 7 analitycznych widoków SQL
├── cli/
│   ├── telemetry_service.py    # Warstwa analityczna (BigQuery / Monitoring)
│   └── telemetry_cli.py        # Narzędzie konsolowe CLI
├── monitoring/
│   └── gemini_enterprise_telemetry_dashboard.json # Dashboard Cloud Monitoring
└── tests/
    └── test_suite.py           # Zestaw testów jednostkowych i integracyjnych
```

---

## Licencja

Apache License 2.0. Szczegóły w pliku [LICENSE](LICENSE).
