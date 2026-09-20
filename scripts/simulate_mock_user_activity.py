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

import json
import sys
import time
import urllib.request
import urllib.error
import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request

PROJECT_ID = "test-ge-demos"
LOCATION = "eu"
ENGINE_ID = "gemini-test-123_1789903253533"
MOCK_USER_SA = "mock-analyst-user@test-ge-demos.iam.gserviceaccount.com"
BASE_URL = f"https://eu-discoveryengine.googleapis.com/v1alpha/projects/931239021849/locations/{LOCATION}/collections/default_collection/engines/{ENGINE_ID}/assistants/default_assistant"


def get_mock_user_token():
    source_credentials, _ = google.auth.default()
    target_credentials = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=MOCK_USER_SA,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    target_credentials.refresh(Request())
    return target_credentials.token


def call_stream_assist(token, query_text, agent_id=None):
    url = f"{BASE_URL}:streamAssist"
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
            "X-Goog-User-Project": PROJECT_ID
        }
    )
    full_resp = []
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            full_resp.append(line.decode("utf-8"))
    return "".join(full_resp)


def call_create_agent(token, display_name, description, instruction):
    url = f"{BASE_URL}/agents"
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
            "X-Goog-User-Project": PROJECT_ID
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    skip_already_done = "--resume" in sys.argv
    print(f"=== Generowanie tokenu dla użytkownika: {MOCK_USER_SA} ===")
    token = get_mock_user_token()
    print("Token wygenerowany pomyślnie!")

    if not skip_already_done:
        # 1. Obrazek (Image Generation)
        print("\n[1/4] Krok 1: Generowanie obrazka (Image Generation via StreamAssist)...")
        img_resp = call_stream_assist(token, "Wygeneruj obrazek futurystycznego miasta w stylu cyberpunk")
        print(f"Obrazek wygenerowany! (Długość odpowiedzi strumienia: {len(img_resp)} znaków)")
        time.sleep(2)

        # 2. Deep Research
        print("\n[2/4] Krok 2: Uruchomienie 1 zadania Deep Research...")
        dr_resp = call_stream_assist(
            token,
            "Analiza rynku technologii kwantowych w Europie w 2026 roku",
            agent_id="deep_research"
        )
        print(f"Deep research zainicjalizowany! (Długość odpowiedzi strumienia: {len(dr_resp)} znaków)")
        time.sleep(2)

        # 3. Dwa bardzo proste agenty (Agent 1)
        print("\n[3/4] Krok 3: Tworzenie 2 prostych agentów...")
        a1 = call_create_agent(
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
    r1 = call_stream_assist(token, q1)
    print(f"Zapytanie 1 wysłane: '{q1}' (odpowiedź: {len(r1)} znaków)")
    time.sleep(2)

    q2 = "Podsumuj główne zalety architektury mikroserwisów"
    r2 = call_stream_assist(token, q2)
    print(f"Zapytanie 2 wysłane: '{q2}' (odpowiedź: {len(r2)} znaków)")
    time.sleep(2)

    q3 = "Wyjaśnij różnicę między modelem Gemini Flash a Gemini Pro"
    r3 = call_stream_assist(token, q3)
    print(f"Zapytanie 3 wysłane: '{q3}' (odpowiedź: {len(r3)} znaków)")

    print("\n=== Sukces! Wszystkie działania użytkownika fikcyjnego zostały pomyślnie zrealizowane! ===")


if __name__ == "__main__":
    main()
