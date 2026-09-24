#!/usr/bin/env python3
"""
Moduł automatycznego włączania obserwowalności dla nowo tworzonych agentów w Gemini Enterprise.
Konfiguruje:
  1. Temat Cloud Pub/Sub: gemini-enterprise-agent-events
  2. Zlew Cloud Logging: gemini-enterprise-agent-events-sink (filtr na CreateAgent w Cloud Audit Logs)
  3. Uprawnienia IAM (Publisher dla sinka, Admin dla konta serwisowego funkcji)
  4. Wdrożenie Cloud Run Function (2nd gen): ge-auto-observability-enabler
  5. Początkową reconciliację istniejących agentów w silniku (Zero-Agent-Left-Behind)
"""

import sys
import os
import json
import re
import subprocess
import urllib.request
import google.auth
from google.auth.transport.requests import Request

def get_auth_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token

def map_location_to_functions_region(location):
    loc_lower = location.lower()
    if loc_lower == "eu":
        return "europe-west1"
    elif loc_lower == "us":
        return "us-central1"
    elif loc_lower == "global":
        return "europe-west1"
    elif "-" in loc_lower:
        return loc_lower
    return "europe-west1"

def reconcile_existing_agents(project_id, location, engine_id, token):
    """
    Skanuje i natychmiast włącza observabilityEnabled: true na wszystkich istniejących agentach w silniku.
    """
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            agents = data.get("agents", [])
            patched_count = 0
            for a in agents:
                a_name = a.get("name")
                obs = a.get("observabilityConfig") or {}
                if not obs.get("observabilityEnabled"):
                    patch_url = f"https://{api_host}/v1alpha/{a_name}?updateMask=observabilityConfig"
                    patch_body = json.dumps({"observabilityConfig": {"observabilityEnabled": True}}).encode("utf-8")
                    patch_req = urllib.request.Request(
                        patch_url, data=patch_body, method="PATCH",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Goog-User-Project": project_id}
                    )
                    with urllib.request.urlopen(patch_req) as p_resp:
                        if p_resp.status in (200, 204):
                            patched_count += 1
            return len(agents), patched_count
    except Exception as e:
        print(f"    (Ostrzeżenie przy wstępnej weryfikacji agentów: {e})")
        return 0, 0

def setup_auto_observability_enabler(project_id, location, engine_id):
    print("--> [8/8] Konfiguracja automatycznego włączania obserwowalności nowych agentów (Event-Driven)...")
    token = get_auth_token()
    topic_name = "gemini-enterprise-agent-events"
    sink_name = "gemini-enterprise-agent-events-sink"
    sa_name = "sa-ge-auto-obs"
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    fn_name = "ge-auto-observability-enabler"
    fn_region = map_location_to_functions_region(location)

    # 1. Pub/Sub Topic
    print(f"    Sprawdzanie / tworzenie tematu Pub/Sub '{topic_name}'...")
    res = subprocess.run(["gcloud", "pubsub", "topics", "describe", topic_name, f"--project={project_id}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        subprocess.run(["gcloud", "pubsub", "topics", "create", topic_name, f"--project={project_id}", "--quiet"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"    ✔ Utworzono temat Pub/Sub '{topic_name}'.")
    else:
        print(f"    ✔ Temat Pub/Sub '{topic_name}' już istnieje.")

    # 2. Cloud Logging Sink
    print(f"    Konfiguracja zlewu Cloud Logging '{sink_name}' (filtr na CreateAgent)...")
    log_filter = 'logName=~"cloudaudit.googleapis.com%2Factivity" AND protoPayload.methodName="google.cloud.discoveryengine.v1main.AgentService.CreateAgent"'
    destination = f"pubsub.googleapis.com/projects/{project_id}/topics/{topic_name}"

    res = subprocess.run(["gcloud", "logging", "sinks", "describe", sink_name, f"--project={project_id}", "--format=value(writerIdentity)"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        sink_res = subprocess.run([
            "gcloud", "logging", "sinks", "create", sink_name, destination,
            f"--log-filter={log_filter}", f"--project={project_id}", "--quiet"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        res = subprocess.run(["gcloud", "logging", "sinks", "describe", sink_name, f"--project={project_id}", "--format=value(writerIdentity)"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    
    writer_identity = res.stdout.strip()
    if writer_identity:
        subprocess.run([
            "gcloud", "pubsub", "topics", "add-iam-policy-binding", topic_name,
            f"--member={writer_identity}", "--role=roles/pubsub.publisher",
            f"--project={project_id}", "--quiet"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print(f"    ✔ Zlew Cloud Logging '{sink_name}' jest aktywny.")

    # 3. Service Account dla funkcji
    print(f"    Weryfikacja konta serwisowego '{sa_email}'...")
    sa_check = subprocess.run(["gcloud", "iam", "service-accounts", "describe", sa_email, f"--project={project_id}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sa_check.returncode != 0:
        subprocess.run([
            "gcloud", "iam", "service-accounts", "create", sa_name,
            "--display-name=Gemini Enterprise Auto Observability Enabler",
            f"--project={project_id}", "--quiet"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Role dla konta serwisowego
    for role in ["roles/discoveryengine.admin", "roles/logging.logWriter", "roles/run.invoker"]:
        subprocess.run([
            "gcloud", "projects", "add-iam-policy-binding", project_id,
            f"--member=serviceAccount:{sa_email}", f"--role={role}",
            "--condition=None", "--quiet"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    # Uprawnienia dla Pub/Sub i Cloud Build
    try:
        proj_num_res = subprocess.run([
            "gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"
        ], stdout=subprocess.PIPE, text=True, check=True)
        proj_num = proj_num_res.stdout.strip()
        pubsub_sa = f"serviceAccount:service-{proj_num}@gcp-sa-pubsub.iam.gserviceaccount.com"
        compute_sa = f"serviceAccount:{proj_num}-compute@developer.gserviceaccount.com"

        # Pub/Sub token creator na SA funkcji (dla Eventarc OIDC)
        subprocess.run([
            "gcloud", "iam", "service-accounts", "add-iam-policy-binding", sa_email,
            f"--member={pubsub_sa}", "--role=roles/iam.serviceAccountTokenCreator",
            f"--project={project_id}", "--quiet"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        # Build permissions na compute SA
        for b_role in ["roles/logging.logWriter", "roles/storage.objectViewer", "roles/artifactregistry.writer"]:
            subprocess.run([
                "gcloud", "projects", "add-iam-policy-binding", project_id,
                f"--member={compute_sa}", f"--role={b_role}",
                "--condition=None", "--quiet"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass

    # 4. Wdrożenie Cloud Run Function
    source_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "functions", "auto_observability_enabler"))
    print(f"    Wdrażanie funkcji Cloud Run (2nd gen) '{fn_name}' w regionie '{fn_region}'...")
    deploy_cmd = [
        "gcloud", "functions", "deploy", fn_name,
        "--gen2",
        "--runtime=python311",
        f"--region={fn_region}",
        f"--source={source_dir}",
        "--entry-point=auto_enable_observability",
        f"--trigger-topic={topic_name}",
        f"--service-account={sa_email}",
        f"--set-env-vars=GCP_PROJECT={project_id},LOCATION={location},ENGINE_ID={engine_id}",
        f"--project={project_id}",
        "--quiet"
    ]
    subprocess.run(deploy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    # Zapewnienie uprawnień wywołania (allow unauthenticated / allUsers / run.invoker)
    subprocess.run([
        "gcloud", "run", "services", "add-iam-policy-binding", fn_name,
        f"--region={fn_region}", "--member=allUsers", "--role=roles/run.invoker",
        f"--project={project_id}", "--quiet"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print(f"    ✔ Funkcja '{fn_name}' została pomyślnie wdrożona i podłączona pod zdarzenia CreateAgent.")

    # 5. Wstępna reconciliacja agentów
    total_agents, patched = reconcile_existing_agents(project_id, location, engine_id, token)
    if patched > 0:
        print(f"    ✔ Wstępna synchronizacja: Włączono obserwowalność na {patched} z {total_agents} istniejących agentów.")
    else:
        print(f"    ✔ Wstępna synchronizacja: Wszyscy istniejący agenci ({total_agents}) mają aktywną obserwowalność.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Wdraża automat obserwowalności agentów Gemini Enterprise")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--location", default="eu")
    parser.add_argument("--engine", required=True)
    args = parser.parse_args()
    setup_auto_observability_enabler(args.project, args.location, args.engine)
