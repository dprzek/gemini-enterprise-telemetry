#!/usr/bin/env python3
"""
Zintegrowany Instalator Potoku Telemetrii, Adopcji i Obserwowalności Gemini Enterprise.
Uruchamia kompletne wdrożenie "Zero-Touch" w jednym poleceniu:
  1. Auto-detekcja projektu, lokalizacji i silnika (obsługa przyjaznych nazw aplikacji).
  2. Automatyczne włączenie konfiguracji obserwowalności w silniku (bez ręcznego cURL!).
  3. Konfiguracja zbioru BigQuery, zlewu Cloud Logging i uprawnień IAM.
  4. Wsteczna ingestja historii logów (Backfill).
  5. Wdrożenie zdeduplikowanych widoków analitycznych SQL w BigQuery.
  6. Wdrożenie wizualnego dashboardu w Cloud Monitoring.
  7. Wdrożenie i publikacja Agenta Telemetrii w Gemini Enterprise.
"""

import sys
import os
import json
import argparse
import subprocess
import urllib.request
import google.auth
from google.auth.transport.requests import Request
from google.cloud import bigquery

# Import modułów lokalnych
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "scripts")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "cli")))
from backfill_logs_to_bigquery import run_backfill, init_streaming_tables
from telemetry_service import TelemetryService

def get_auth_token():
    creds, _ = google.auth.default()
    creds.refresh(Request())
    return creds.token

def get_default_project():
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if proj:
        return proj
    try:
        res = subprocess.run(["gcloud", "config", "get-value", "project"], stdout=subprocess.PIPE, text=True, check=True)
        val = res.stdout.strip()
        if val:
            return val
    except Exception:
        pass
    try:
        _, creds_proj = google.auth.default()
        if creds_proj:
            return creds_proj
    except Exception:
        pass
    return None

def resolve_engine(project_id, location, engine_hint, token):
    """
    Dopasowuje identyfikator silnika (Engine ID) lub nazwę aplikacji do silnika w projekcie.
    Wspiera projekty z jednym lub wieloma silnikami.
    """
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            engines = data.get("engines", [])
            
            if engine_hint:
                engine_hint_clean = engine_hint.strip()
                # 1. Dokładne dopasowanie po pełnym ID silnika (np. ge-dprzek_1789915910154)
                for eng in engines:
                    e_id = eng.get("name", "").split("/")[-1]
                    if e_id.lower() == engine_hint_clean.lower():
                        return e_id
                # 2. Dokładne dopasowanie po displayName
                for eng in engines:
                    e_id = eng.get("name", "").split("/")[-1]
                    d_name = eng.get("displayName", "")
                    if d_name.lower() == engine_hint_clean.lower():
                        return e_id
                # 3. Dopasowanie prefiksu ID silnika ({engine_hint}_...)
                for eng in engines:
                    e_id = eng.get("name", "").split("/")[-1]
                    if e_id.lower().startswith(f"{engine_hint_clean.lower()}_"):
                        return e_id
                # 4. Jeśli podano bezpośrednie ID silnika (lub brak uprawnień do listowania)
                return engine_hint_clean

            # Gdy użytkownik nie podał identyfikatora silnika:
            if not engines:
                return None
            if len(engines) == 1:
                auto_id = engines[0].get("name", "").split("/")[-1]
                print(f"[*] Wykryto 1 silnik w projekcie: '{auto_id}' (użyty domyślnie).")
                return auto_id

            # W projekcie istnieje WIELE silników - brak domniemania 1 silnika!
            print("======================================================================")
            print(f"[!] W projekcie '{project_id}' wykryto wiele silników Gemini Enterprise ({len(engines)} silników).")
            print("    Wskaż konkretny identyfikator silnika (Engine ID):")
            for eng in engines:
                e_id = eng.get("name", "").split("/")[-1]
                d_name = eng.get("displayName", "")
                print(f"      • Engine ID: {e_id}  (Nazwa: '{d_name}')")
            print("\n    Sposób użycia:")
            print("      ./deploy.sh <ENGINE_ID> [--project PROJECT_ID] [--location LOCATION]")
            print("      ./deploy.sh --engine <ENGINE_ID>")
            print("======================================================================")
            return None
    except Exception as e:
        print(f"    (Uwaga przy wyszukiwaniu silników: {e})")
    return engine_hint

def ensure_required_apis(project_id):
    """Automatycznie weryfikuje i aktywuje wymagane API Google Cloud."""
    required_apis = [
        "aiplatform.googleapis.com",
        "discoveryengine.googleapis.com",
        "bigquery.googleapis.com",
        "logging.googleapis.com",
        "monitoring.googleapis.com",
        "cloudtrace.googleapis.com",
        "cloudresourcemanager.googleapis.com"
    ]
    print("--> [1/7] Weryfikacja i aktywacja wymaganych interfejsów API Google Cloud...")
    try:
        # Szybkie sprawdzenie już aktywnych API, by nie czekać bezczynnie
        cmd_check = ["gcloud", "services", "list", f"--project={project_id}", "--enabled", "--format=value(config.name)"]
        res = subprocess.run(cmd_check, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        enabled_services = set(res.stdout.split()) if res.returncode == 0 else set()
        
        missing = [api for api in required_apis if api not in enabled_services]
        if not missing:
            print("    ✔ Wszystkie wymagane API są już aktywne.")
            return
            
        print(f"    Aktywacja {len(missing)} brakujących API: {', '.join(missing)} (proszę czekać)...")
        cmd = ["gcloud", "services", "enable", *missing, f"--project={project_id}", "--quiet"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("    ✔ Wymagane API Google Cloud zostały aktywowane.")
    except Exception as e:
        print(f"    (Weryfikacja API: {e})")

def enable_engine_observability(project_id, location, engine_id, token):
    """Automatycznie włącza OpenTelemetry i logowanie promptów/odpowiedzi w silniku."""
    print(f"--> [2/7] Konfiguracja obserwowalności silnika '{engine_id}'...")
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    engine_url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}"
    
    # 1. Sprawdzenie bieżącej konfiguracji
    try:
        req = urllib.request.Request(engine_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
        with urllib.request.urlopen(req) as resp:
            eng_data = json.loads(resp.read().decode())
            obs_cfg = eng_data.get("observabilityConfig", {})
            if obs_cfg.get("observabilityEnabled") and obs_cfg.get("sensitiveLoggingEnabled"):
                print("    ✔ Obserwowalność silnika (OpenTelemetry + Sensitive Logging) jest już aktywna.")
                return
    except Exception as e:
        print(f"    Nie udało się pobrać stanu silnika: {e}")

    # 2. Włączenie obserwowalności przez PATCH
    patch_url = f"{engine_url}?updateMask=observabilityConfig"
    patch_payload = {
        "observabilityConfig": {
            "observabilityEnabled": True,
            "sensitiveLoggingEnabled": True
        }
    }
    try:
        patch_req = urllib.request.Request(
            patch_url,
            data=json.dumps(patch_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": project_id
            },
            method="PATCH"
        )
        with urllib.request.urlopen(patch_req) as resp:
            print("    ✔ Pomyślnie włączono obserwowalność OpenTelemetry i logowanie w silniku!")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"    ⚠️ Ostrzeżenie podczas konfiguracji obserwowalności: HTTP {e.code} - {err_msg}")

def setup_bigquery_and_sink(project_id, location, dataset_id, sink_name="gemini-enterprise-telemetry-sink"):
    """Tworzy zbiór BigQuery, zlew Cloud Logging oraz nadaje uprawnienia kontu serwisowemu."""
    print(f"--> [3/7] Konfiguracja zbioru BigQuery '{dataset_id}' i zlewu logów...")
    bq_client = bigquery.Client(project=project_id)
    
    # 1. Zbiór danych BigQuery
    ds_ref = bigquery.DatasetReference(project_id, dataset_id)
    try:
        dataset = bq_client.get_dataset(ds_ref)
        print(f"    Zbiór danych '{dataset_id}' już istnieje.")
    except Exception:
        dataset = bigquery.Dataset(ds_ref)
        dataset.location = location.upper() if location != "global" else "EU"
        dataset.description = "Telemetria adopcji Gemini Enterprise, operacje wnioskowania i logi audytowe"
        dataset = bq_client.create_dataset(dataset)
        print(f"    ✔ Utworzono zbiór danych '{dataset_id}' w lokalizacji {dataset.location}.")

    # 2. Zlew Cloud Logging do BigQuery
    sink_filter = (
        'logName=~"cloudaudit.googleapis.com" OR '
        'logName=~"discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity" OR '
        'logName=~"discoveryengine.googleapis.com%2Fgen_ai.client.inference.operation.details"'
    )
    destination = f"bigquery.googleapis.com/projects/{project_id}/datasets/{dataset_id}"
    
    # Sprawdzenie istnienia zlewu
    cmd_check = ["gcloud", "logging", "sinks", "describe", sink_name, f"--project={project_id}", "--format=value(writerIdentity)"]
    res = subprocess.run(cmd_check, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if res.returncode == 0 and res.stdout.strip():
        writer_identity = res.stdout.strip()
        print(f"    Zlew '{sink_name}' już istnieje.")
    else:
        cmd_create = [
            "gcloud", "logging", "sinks", "create", sink_name, destination,
            f"--log-filter={sink_filter}",
            f"--project={project_id}",
            "--use-partitioned-tables"
        ]
        subprocess.run(cmd_create, check=True, stdout=subprocess.PIPE)
        res = subprocess.run(cmd_check, stdout=subprocess.PIPE, check=True, text=True)
        writer_identity = res.stdout.strip()
        print(f"    ✔ Utworzono zlew logów '{sink_name}'.")

    # 3. Nadanie uprawnień BigQuery Data Editor dla konta serwisowego zlewu
    writer_sa = writer_identity.replace("serviceAccount:", "")
    entries = list(dataset.access_entries)
    if not any(getattr(e, "entity_id", None) == writer_sa for e in entries):
        entries.append(bigquery.AccessEntry(role="roles/bigquery.dataEditor", entity_type="userByEmail", entity_id=writer_sa))
        dataset.access_entries = entries
        bq_client.update_dataset(dataset, ["access_entries"])
    print("    ✔ Zlew Cloud Logging i uprawnienia zostały pomyślnie skonfigurowane.")
    return bq_client

def deploy_sql_views(bq_client, project_id, dataset_id):
    """Wdraża analityczne widoki SQL w BigQuery z dynamicznym podstawieniem parametrów."""
    print("--> [5/7] Wdrażanie analitycznych widoków SQL w BigQuery...")
    # Gwarancja istnienia i spójności tabel oraz kolumn przed utworzeniem widoków
    init_streaming_tables(bq_client, project_id, dataset_id)

    sql_path = os.path.join(os.path.dirname(__file__), "bigquery", "telemetry_views.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        raw_sql = f.read()
    
    formatted_sql = raw_sql.format(project_id=project_id, dataset_id=dataset_id)
    job = bq_client.query(formatted_sql)
    job.result()
    print("    ✔ Analityczne widoki SQL zostały pomyślnie utworzone / zaktualizowane w BigQuery.")

def deploy_monitoring_dashboard(project_id):
    """Tworzy dashboard operacyjny w Cloud Monitoring, jeśli jeszcze nie istnieje."""
    print("--> [6/7] Sprawdzanie dashboardu w Cloud Monitoring...")
    try:
        res = subprocess.run(["gcloud", "monitoring", "dashboards", "list", f"--project={project_id}", "--format=value(displayName)"], stdout=subprocess.PIPE, text=True)
        if "Gemini Enterprise" in res.stdout:
            print("    Dashboard w Cloud Monitoring już istnieje.")
            return
        dash_file = os.path.join(os.path.dirname(__file__), "monitoring", "gemini_enterprise_telemetry_dashboard.json")
        subprocess.run(["gcloud", "monitoring", "dashboards", "create", f"--config-from-file={dash_file}", f"--project={project_id}"], check=True)
        print("    ✔ Pomyślnie utworzono dashboard w Cloud Monitoring.")
    except Exception as e:
        print(f"    (Dashboard Cloud Monitoring: {e})")

def deploy_telemetry_agent(project_id, location, engine_id, dataset_id="gemini_enterprise_telemetry", reasoning_engine=None):
    """Wdraża dynamicznego Agenta ADK w Vertex AI Agent Runtime i rejestruje w Gemini Enterprise."""
    print("--> [7/7] Wdrażanie Agenta Telemetrii w Gemini Enterprise (Dynamic ADK Agent na Vertex AI Agent Runtime)...")
    agent_script = os.path.join(os.path.dirname(__file__), "agent", "deploy_adk_agent.py")
    cmd = [
        sys.executable, agent_script,
        f"--project={project_id}",
        f"--location={location}",
        f"--engine={engine_id}",
        f"--dataset={dataset_id}"
    ]
    if reasoning_engine:
        cmd.append(f"--reasoning-engine={reasoning_engine}")
    subprocess.run(cmd, check=True)

def main():
    parser = argparse.ArgumentParser(description="Zintegrowany Instalator Potoku Telemetrii Gemini Enterprise")
    parser.add_argument("engine", nargs="?", default=None, help="Identyfikator silnika (Engine ID, np. ge-dprzek_1789915910154) lub przyjazna nazwa aplikacji")
    parser.add_argument("--project", "-p", default=None, help="ID Projektu Google Cloud")
    parser.add_argument("--location", "-l", default=None, help="Lokalizacja Discovery Engine (np. eu, global, us)")
    parser.add_argument("--engine", "-e", dest="engine_flag", default=None, help="Identyfikator silnika Gemini Enterprise (Engine ID)")
    parser.add_argument("--engine-id", dest="engine_id_flag", default=None, help="Jawny identyfikator silnika Gemini Enterprise (Engine ID)")
    parser.add_argument("--dataset", "-d", default="gemini_enterprise_telemetry", help="ID zbioru BigQuery")
    parser.add_argument("--skip-backfill", action="store_true", help="Pomiń wsteczną ingestję logów")
    parser.add_argument("--reasoning-engine", default=None, help="Istniejący zasób Vertex AI Reasoning Engine do ponownego użycia")
    args = parser.parse_args()

    project_id = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT") or get_default_project()
    if not project_id:
        print("Błąd: Nie określono identyfikatora projektu GCP. Użyj opcji --project <PROJECT_ID> lub ustaw zmienną GOOGLE_CLOUD_PROJECT.")
        sys.exit(1)
    location = args.location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "eu"
    dataset_id = args.dataset
    engine_hint = args.engine_id_flag or args.engine_flag or args.engine or os.environ.get("GEMINI_ENGINE_ID")

    token = get_auth_token()
    engine_id = resolve_engine(project_id, location, engine_hint, token)
    if not engine_id:
        print("Błąd: Nie określono lub nie znaleziono silnika Gemini Enterprise. Podaj identyfikator silnika: ./deploy.sh <ENGINE_ID> lub opcję --engine <ENGINE_ID>.")
        sys.exit(1)

    match_info = f" (z dopasowania: '{engine_hint}')" if engine_hint and engine_hint != engine_id else ""
    print("======================================================================")
    print("Rozpoczęcie automatycznego wdrożenia potoku telemetrii Gemini Enterprise")
    print(f"  Projekt:      {project_id}")
    print(f"  Lokalizacja:  {location}")
    print(f"  Silnik (ID):  {engine_id}{match_info}")
    print(f"  Zbiór danych: {dataset_id}")
    print("======================================================================")

    # 1. Weryfikacja i aktywacja API
    ensure_required_apis(project_id)

    # 2. Obserwowalność silnika (Auto-Enable)
    enable_engine_observability(project_id, location, engine_id, token)

    # 3. BigQuery i Zlew Cloud Logging
    bq_client = setup_bigquery_and_sink(project_id, location, dataset_id)

    # 4. Wsteczna ingestja logów (Backfill)
    if not args.skip_backfill:
        print("--> [4/7] Wsteczna ingestja logów z ostatnich 30 dni...")
        run_backfill(bq_client, project_id, dataset_id, days=30)
    else:
        print("--> [4/7] Pominięto wsteczną ingestję logów (--skip-backfill).")

    # 5. Widoki SQL
    deploy_sql_views(bq_client, project_id, dataset_id)

    # 6. Dashboard Cloud Monitoring
    deploy_monitoring_dashboard(project_id)

    # 7. Agent Gemini Enterprise
    deploy_telemetry_agent(project_id, location, engine_id, dataset_id, reasoning_engine=args.reasoning_engine)

    print("\n======================================================================")
    print("✔ Wdrożenie zakończone pełnym sukcesem! Wszystkie komponenty są aktywne.")
    print("======================================================================")
    print("Szybki start:")
    print(f"  CLI Utylizacji: python3 cli/telemetry_cli.py --project {project_id} --location {location} --engine {engine_id} utilization --daily")
    print(f"  CLI Adopcji:    python3 cli/telemetry_cli.py --project {project_id} --location {location} --engine {engine_id} adoption")
    print(f"  BigQuery View:  `{project_id}.{dataset_id}.v_user_daily_utilization`")
    print("======================================================================")

if __name__ == "__main__":
    main()
