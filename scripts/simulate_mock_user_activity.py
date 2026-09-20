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
Script to simulate activity for fictitious user:
mock-analyst-user@test-ge-demos.iam.gserviceaccount.com

Actions:
1. 1 Image generation query (Imagen via StreamAssist)
2. 1 Deep Research query (StreamAssist with deep_research agent)
3. 2 Custom Agents created (CreateAgent)
4. 3 Regular Assistant queries (StreamAssist)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request
from google.cloud import resourcemanager_v3


def get_project_number(project_id, credentials):
    try:
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project = client.get_project(name=f"projects/{project_id}")
        return project.name.split("/")[-1]
    except Exception:
        return project_id


def get_mock_user_token(mock_user_sa):
    source_credentials, _ = google.auth.default()
    target_credentials = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=mock_user_sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    target_credentials.refresh(Request())
    return target_credentials.token


def call_stream_assist(base_url, project_id, token, query_text, agent_id=None):
    url = f"{base_url}:streamAssist"
    payload = {
        "query": {
            "parts": [{"text": query_text}]
        }
    }
    if agent_id:
        payload["agentsSpec"] = {
            "agentSpecs": [{"agentId": agent_id}]
        }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id
        }
    )
    full_resp = []
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            full_resp.append(line.decode("utf-8"))
    return "".join(full_resp)


def call_create_agent(base_url, project_id, token, display_name, description, instruction):
    url = f"{base_url}/agents"
    payload = {
        "displayName": display_name,
        "description": description,
        "state": "PRIVATE",
        "lowCodeAgentDefinition": {
            "nodes": [
                {
                    "llmAgentNode": {
                        "model": "gemini-2.5-flash",
                        "instruction": instruction,
                        "selectedTools": {
                            "tool": [{"name": "googleSearch"}]
                        }
                    },
                    "id": "root_agent",
                    "displayName": display_name
                }
            ],
            "rootAgentId": "root_agent",
            "deployedNodes": [
                {
                    "llmAgentNode": {
                        "model": "gemini-2.5-flash",
                        "instruction": instruction,
                        "selectedTools": {
                            "tool": [{"name": "googleSearch"}]
                        }
                    },
                    "id": "root_agent",
                    "displayName": display_name
                }
            ],
            "deployedRootAgentId": "root_agent",
            "draftDisplayName": display_name,
            "draftDescription": description
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    parser = argparse.ArgumentParser(description="Simulate mock user telemetry activity in Gemini Enterprise")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-ge-demos"), help="GCP Project ID")
    parser.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "eu"), help="Location (eu, us, global)")
    parser.add_argument("--engine", default="damian-test_1789915277912", help="Discovery Engine / Gemini Enterprise Engine ID")
    parser.add_argument("--user-sa", default="mock-analyst-user@dprzek-vertex.iam.gserviceaccount.com", help="Mock user service account email")
    parser.add_argument("--resume", action="store_true", help="Resume/skip already done parts")
    args = parser.parse_args()

    credentials, _ = google.auth.default()
    project_number = get_project_number(args.project, credentials)
    api_host = f"{args.location}-discoveryengine.googleapis.com" if args.location != "global" else "discoveryengine.googleapis.com"
    base_url = f"https://{api_host}/v1alpha/projects/{project_number}/locations/{args.location}/collections/default_collection/engines/{args.engine}/assistants/default_assistant"

    print(f"=== Generowanie tokenu dla użytkownika: {args.user_sa} ===")
    print(f"    Projekt: {args.project} ({project_number}), Silnik: {args.engine}")
    token = get_mock_user_token(args.user_sa)
    print("Token wygenerowany pomyślnie!")

    if not args.resume:
        # 1. Obrazek (Image Generation)
        print("\n[1/4] Krok 1: Generowanie obrazka (Image Generation via StreamAssist)...")
        img_resp = call_stream_assist(base_url, args.project, token, "Wygeneruj obrazek futurystycznego miasta w stylu cyberpunk")
        print(f"Obrazek wygenerowany! (Długość odpowiedzi strumienia: {len(img_resp)} znaków)")
        time.sleep(2)

        # 2. Deep Research
        print("\n[2/4] Krok 2: Uruchomienie 1 zadania Deep Research...")
        dr_resp = call_stream_assist(
            base_url,
            args.project,
            token,
            "Analiza rynku technologii kwantowych w Europie w 2026 roku",
            agent_id="deep_research"
        )
        print(f"Deep research zainicjalizowany! (Długość odpowiedzi strumienia: {len(dr_resp)} znaków)")
        time.sleep(2)

        # 3. Dwa bardzo proste agenty (Agent 1)
        print("\n[3/4] Krok 3: Tworzenie 2 prostych agentów...")
        a1 = call_create_agent(
            base_url,
            args.project,
            token, 
            "Mock Quick FAQ Agent", 
            "Simple FAQ agent for telemetry testing",
            "Answer customer FAQs concisely and accurately."
        )
        print(f"Agent 1 utworzony: {a1.get('name')} ({a1.get('displayName')})")
        time.sleep(2)

    # Agent 2
    print("\nTworzenie Agenta 2...")
    a2 = call_create_agent(
        base_url,
        args.project,
        token, 
        "Mock Data Summarizer Agent", 
        "Simple summarizer agent for telemetry testing",
        "Summarize data tables and key business metrics."
    )
    print(f"Agent 2 utworzony: {a2.get('name')} ({a2.get('displayName')})")
    time.sleep(2)

    # 4. Trzy zapytania do asystenta
    print("\n[4/4] Krok 4: Dokonanie 3 standardowych zapytań do asystenta...")
    q1 = "Jaki jest dzisiejszy kurs wymiany EUR do PLN?"
    r1 = call_stream_assist(base_url, args.project, token, q1)
    print(f"Zapytanie 1 wysłane: '{q1}' (odpowiedź: {len(r1)} znaków)")
    time.sleep(2)

    q2 = "Podsumuj główne zalety architektury mikroserwisów"
    r2 = call_stream_assist(base_url, args.project, token, q2)
    print(f"Zapytanie 2 wysłane: '{q2}' (odpowiedź: {len(r2)} znaków)")
    time.sleep(2)

    q3 = "Wyjaśnij różnicę między modelem Gemini Flash a Gemini Pro"
    r3 = call_stream_assist(base_url, args.project, token, q3)
    print(f"Zapytanie 3 wysłane: '{q3}' (odpowiedź: {len(r3)} znaków)")

    print("\n=== Sukces! Wszystkie działania użytkownika fikcyjnego zostały pomyślnie zrealizowane! ===")


if __name__ == "__main__":
    main()
