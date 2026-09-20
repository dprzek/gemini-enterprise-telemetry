#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Deploy Dynamic ADK Agent to Vertex AI Agent Runtime (Reasoning Engine)
and register it in Gemini Enterprise.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

import vertexai
from vertexai import agent_engines
from vertexai.agent_engines import _utils

# Add current directory to path so we can import the agent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent.adk_telemetry_agent as telemetry_agent_module
from agent.adk_telemetry_agent import root_agent

# Ensure cloudpickle embeds the module bytecode directly into the pickle blob
# so the remote Reasoning Engine container doesn't fail with No module named 'agent'
cloudpickle = _utils._import_cloudpickle_or_raise()
cloudpickle.register_pickle_by_value(telemetry_agent_module)


def get_access_token(credentials):
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials.token


def get_project_number(project_id, credentials):
    try:
        res = subprocess.run(
            ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        pnum = res.stdout.strip()
        if pnum:
            return pnum
    except Exception:
        pass
    try:
        url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {get_access_token(credentials)}",
                "X-Goog-User-Project": project_id
            }
        )
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            return data.get("projectNumber")
    except Exception as e:
        print(f"[WARN] Nie udało się automatycznie pobrać projectNumber: {e}")
        return None


def resolve_engine_id(project_id, location, engine_hint, credentials):
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    token = get_access_token(credentials)
    
    # 1. Sprawdź bezpośrednio
    if engine_hint:
        direct_url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_hint}"
        req = urllib.request.Request(direct_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    return engine_hint
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return engine_hint

    # 2. Wylistuj silniki
    list_url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines"
    req = urllib.request.Request(list_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            engines = data.get("engines", [])
            if not engine_hint and engines:
                if len(engines) == 1:
                    return engines[0].get("name", "").split("/")[-1]
                print(f"[!] W projekcie '{project_id}' wykryto wiele silników ({len(engines)}). Wskaż docelowy silnik za pomocą opcji --engine <ENGINE_ID>.")
                for eng in engines:
                    print(f"    - Engine ID: {eng.get('name', '').split('/')[-1]} (Nazwa: {eng.get('displayName', '')})")
                sys.exit(1)
            for eng in engines:
                eid = eng.get("name", "").split("/")[-1]
                dname = eng.get("displayName", "")
                if engine_hint and (eid.lower() == engine_hint.lower() or dname.lower() == engine_hint.lower() or eid.lower().startswith(f"{engine_hint.lower()}_")):
                    return eid
    except Exception as e:
        print(f"[WARN] Błąd listowania silników: {e}")
        
    return engine_hint


def ensure_staging_bucket(project_id, location, credentials):
    bucket_name = f"{project_id}-vertex-staging-{location}"
    client = storage.Client(project=project_id, credentials=credentials)
    try:
        bucket = client.get_bucket(bucket_name)
        print(f"[OK] Używam istniejącego bucketu stagingowego: gs://{bucket_name}")
        return f"gs://{bucket_name}"
    except Exception:
        print(f"[*] Tworzenie bucketu stagingowego gs://{bucket_name} w regionie {location}...")
        try:
            client.create_bucket(bucket_name, location=location)
            print(f"[OK] Utworzono bucket: gs://{bucket_name}")
            return f"gs://{bucket_name}"
        except Exception as e:
            print(f"[WARN] Nie udało się utworzyć bucketu: {e}")
            return f"gs://{bucket_name}"


def delete_existing_agents(project_id, project_number, location, engine_id, credentials, target_display_name):
    """Usuwa stare wersje agenta o danej nazwie lub stary statyczny agent."""
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    token = get_access_token(credentials)
    list_url = f"https://{api_host}/v1alpha/projects/{project_number or project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents"
    req = urllib.request.Request(list_url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            agents = data.get("agents", [])
            for ag in agents:
                dname = ag.get("displayName", "")
                ag_name = ag.get("name", "")
                if dname == target_display_name or "Telemetry" in dname:
                    print(f"[*] Usuwanie poprzedniej wersji agenta: {dname} ({ag_name})...")
                    del_req = urllib.request.Request(
                        f"https://{api_host}/v1alpha/{ag_name}",
                        headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id},
                        method="DELETE"
                    )
                    try:
                        urllib.request.urlopen(del_req)
                        print(f"[OK] Usunięto stary agent: {ag_name}")
                    except Exception as de:
                        print(f"[WARN] Błąd usuwania starego agenta: {de}")
    except Exception as e:
        print(f"[WARN] Nie udało się pobrać listy istniejących agentów: {e}")


def register_adk_agent_in_gemini(project_id, project_number, location, engine_id, reasoning_engine_resource_name, credentials):
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    token = get_access_token(credentials)
    url = f"https://{api_host}/v1alpha/projects/{project_number or project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents"
    
    payload = {
        "displayName": "Gemini Enterprise Telemetry & Adoption Agent",
        "description": "Dynamiczny agent ADK telemetrii, utylizacji i adopcji Gemini Enterprise w czasie rzeczywistym.",
        "state": "ENABLED",
        "sharingConfig": {
            "scope": "ALL_USERS"
        },
        "adk_agent_definition": {
            "tool_settings": {
                "tool_description": "Narzędzie do pobierania w czasie rzeczywistym telemetrii, adopcji użytkowników, zużycia tokenów, czasów odpowiedzi oraz limitów kwotowych w Gemini Enterprise."
            },
            "provisioned_reasoning_engine": {
                "reasoning_engine": reasoning_engine_resource_name
            }
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.load(resp)
            print(f"[OK] Agent pomyślnie zarejestrowany w Gemini Enterprise!")
            print(f"     Nazwa: {res.get('displayName')}")
            print(f"     Resource: {res.get('name')}")
            print(f"     Stan: {res.get('state')}")
            print(f"     Sharing: {res.get('sharingConfig', {}).get('scope', 'ALL_USERS')}")
            return res
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[ERROR] Błąd rejestracji agenta w Gemini Enterprise: HTTP {e.code}")
        print(f"        Szczegóły: {err_body}")
        raise


def ensure_reasoning_engine_permissions(project_id, project_number, dataset_id, credentials):
    """Automatycznie weryfikuje i nadaje uprawnienia IAM dla kont usługi Vertex Reasoning Engine."""
    sa_emails = [
        f"service-{project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com",
        f"service-{project_number}@gcp-sa-aiplatform.iam.gserviceaccount.com",
    ]
    roles = [
        "roles/bigquery.jobUser",
        "roles/monitoring.viewer",
        "roles/cloudtrace.user"
    ]

    for sa_email in sa_emails:
        print(f"[*] Weryfikacja i konfiguracja uprawnień IAM dla konta usługi Reasoning Engine: {sa_email}")
        # 1. Role na poziomie projektu (BigQuery Job User, Monitoring Viewer, Cloud Trace User)
        for role in roles:
            try:
                cmd = [
                    "gcloud", "projects", "add-iam-policy-binding", project_id,
                    f"--member=serviceAccount:{sa_email}",
                    f"--role={role}",
                    "--condition=None"
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"    ✔ Przypisano rolę {role} dla {sa_email}")
            except Exception as e:
                print(f"    [INFO] Status roli {role} dla {sa_email}: weryfikacja zakończona ({e})")

        # 2. Dostęp READER na zbiorze danych BigQuery
        try:
            from google.cloud import bigquery
            from google.cloud.bigquery import AccessEntry
            bq_client = bigquery.Client(project=project_id, credentials=credentials)
            dataset = bq_client.get_dataset(dataset_id)
            current_entries = list(dataset.access_entries)
            already_has_access = any(
                entry.entity_id == sa_email and entry.role in ("READER", "WRITER", "OWNER")
                for entry in current_entries
            )
            if not already_has_access:
                current_entries.append(AccessEntry(role="READER", entity_type="userByEmail", entity_id=sa_email))
                dataset.access_entries = current_entries
                bq_client.update_dataset(dataset, ["access_entries"])
                print(f"    ✔ Nadano uprawnienie READER na zbiorze BigQuery '{dataset_id}' dla {sa_email}")
            else:
                print(f"    ✔ Konto {sa_email} posiada już uprawnienia READER do zbioru BigQuery '{dataset_id}'")
        except Exception as bqe:
            print(f"    [INFO] Weryfikacja uprawnień zbioru BigQuery dla {sa_email}: {bqe}")


def main():
    parser = argparse.ArgumentParser(description="Deploy Dynamic ADK Telemetry Agent to Vertex AI Agent Runtime & Gemini Enterprise")
    default_proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
    if not default_proj:
        try:
            _, default_proj = google.auth.default()
        except Exception:
            default_proj = ""
    default_engine = os.environ.get("GEMINI_ENGINE_ID", "")
    parser.add_argument("--project", "-p", default=default_proj, help="Google Cloud Project ID")
    parser.add_argument("--engine", default=default_engine, help="Discovery Engine / Gemini Enterprise Engine ID lub nazwa aplikacji")
    parser.add_argument("--engine-id", dest="engine_id_flag", default=None, help="Jawny identyfikator silnika Discovery Engine (Engine ID)")
    parser.add_argument("--location", default="eu", help="Gemini Enterprise Location (eu, global, us)")
    parser.add_argument("--vertex-location", default="europe-west1", help="Vertex AI Reasoning Engine Location (europe-west1, europe-west4)")
    parser.add_argument("--dataset", default="gemini_enterprise_telemetry", help="BigQuery Dataset ID")
    parser.add_argument("--reasoning-engine", default=None, help="Existing Vertex AI Reasoning Engine resource name to reuse")
    args = parser.parse_args()

    engine_input = args.engine_id_flag or args.engine
    if not engine_input and not default_engine:
        pass  # resolve_engine_id will list engines or error clearly

    credentials, _ = google.auth.default()
    project_number = get_project_number(args.project, credentials)
    engine_id = resolve_engine_id(args.project, args.location, engine_input, credentials)

    print(f"============================================================")
    print(f"  DEPLOY DYNAMIC ADK AGENT -> VERTEX AI AGENT RUNTIME       ")
    print(f"============================================================")
    print(f"  Projekt:         {args.project} ({project_number})")
    print(f"  Gemini Engine:   {engine_id} ({args.location})")
    print(f"  Vertex Region:   {args.vertex_location}")
    print(f"  BigQuery Dataset:{args.dataset}")
    print(f"============================================================")

    # 1. Bucket stagingowy
    staging_bucket = ensure_staging_bucket(args.project, args.vertex_location, credentials)

    # 2. Inicjalizacja Vertex AI
    print(f"[*] Inicjalizacja Vertex AI ({args.project}, {args.vertex_location})...")
    vertexai.init(
        project=args.project,
        location=args.vertex_location,
        staging_bucket=staging_bucket
    )

    # 3. Zapewnienie uprawnień IAM dla konta Reasoning Engine
    ensure_reasoning_engine_permissions(args.project, project_number, args.dataset, credentials)

    # 4. Wdrażanie Agenta do Vertex AI Reasoning Engine
    engine_resource_name = args.reasoning_engine
    if not engine_resource_name:
        print(f"[*] Wdrażanie Agenta ADK do Vertex AI Reasoning Engine...")
        print(f"    Agent: {root_agent.name} (Narzędzia: {len(root_agent.tools)})")
        
        os.environ["BIGQUERY_PROJECT"] = args.project
        os.environ["BIGQUERY_DATASET"] = args.dataset

        try:
            engine = agent_engines.create(
                agent_engine=root_agent,
                display_name="Gemini Enterprise Telemetry & Adoption Engine",
                description="Managed ADK Agent Runtime for Gemini Enterprise Telemetry & Adoption",
                env_vars={
                    "BIGQUERY_PROJECT": args.project,
                    "BIGQUERY_DATASET": args.dataset,
                },
                requirements=[
                    "google-cloud-aiplatform[agent_engines,adk]>=1.88.0",
                    "google-adk>=2.9.0",
                    "google-cloud-bigquery>=3.25.0",
                    "google-cloud-monitoring>=2.21.0",
                ]
            )
            engine_resource_name = engine.resource_name
            print(f"[OK] Vertex AI Reasoning Engine wdrożony!")
            print(f"     Resource: {engine_resource_name}")
        except Exception as e:
            print(f"[WARN] Wystąpił błąd lub timeout podczas oczekiwania na create(): {e}")
            print(f"[*] Weryfikacja czy Reasoning Engine został pomyślnie utworzony na Vertex AI...")
            from vertexai.preview import reasoning_engines as re_preview
            candidate_engines = list(re_preview.ReasoningEngine.list())
            matching = [
                ce for ce in candidate_engines 
                if ce.display_name == "Gemini Enterprise Telemetry & Adoption Engine"
            ]
            if matching:
                engine_resource_name = matching[0].resource_name
                print(f"    ✔ Wykryto aktywny Reasoning Engine na platformie Vertex AI: {engine_resource_name}")
            else:
                raise
    else:
        print(f"[*] Użycie wskazanego Reasoning Engine: {engine_resource_name}")

    # 4. Usunięcie starych instancji agenta w Gemini Enterprise
    print(f"[*] Czyszczenie poprzednich instancji agenta w Gemini Enterprise...")
    delete_existing_agents(args.project, project_number, args.location, engine_id, credentials, "Gemini Enterprise Telemetry & Adoption Agent")

    # 5. Rejestracja nowego Agenta ADK w Gemini Enterprise
    print(f"[*] Rejestracja Agenta w aplikacji Gemini Enterprise...")
    res = register_adk_agent_in_gemini(
        args.project,
        project_number,
        args.location,
        engine_id,
        engine_resource_name,
        credentials
    )

    print(f"\n============================================================")
    print(f"  WDROŻENIE ZAKOŃCZONE SUKCESEM!                             ")
    print(f"============================================================")
    print(f"  Agent:           {res.get('displayName')}")
    print(f"  Gemini Agent ID: {res.get('name')}")
    print(f"  Reasoning Engine:{engine_resource_name}")
    print(f"  Status:          {res.get('state')}")
    print(f"============================================================")


if __name__ == "__main__":
    main()
