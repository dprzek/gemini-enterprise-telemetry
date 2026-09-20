#!/usr/bin/env python3
"""
Moduł zarządzania licencjami Gemini Enterprise (Discovery Engine License API).
Umożliwia listowanie puli licencji, sprawdzanie przypisanych użytkowników
oraz automatyczne przypisywanie licencji (pre-provisioning) bez czekania na pierwsze logowanie.
"""

import sys
import os
import json
import argparse
import urllib.request
import google.auth
from google.auth.transport.requests import Request

def get_auth_token():
    creds, _ = google.auth.default()
    creds.refresh(Request())
    return creds.token

def get_api_host(location):
    return f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"

def list_license_configs(project_id, location, token):
    api_host = get_api_host(location)
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/licenseConfigs"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("licenseConfigs", [])
    except Exception as e:
        print(f"[!] Błąd pobierania konfiguracji licencji: {e}")
        return []

def list_user_licenses(project_id, location, token):
    api_host = get_api_host(location)
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/userStores/default_user_store/userLicenses"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("userLicenses", [])
    except Exception as e:
        print(f"[!] Błąd pobierania licencji użytkowników: {e}")
        return []

def batch_assign_licenses(project_id, location, user_emails, license_config_name, token):
    api_host = get_api_host(location)
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/userStores/default_user_store:batchUpdateUserLicenses"
    
    user_licenses_payload = [
        {
            "userPrincipal": email.strip(),
            "licenseConfig": license_config_name
        }
        for email in user_emails if email.strip()
    ]
    
    body = {
        "inlineSource": {
            "userLicenses": user_licenses_payload
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Goog-User-Project": project_id,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Błąd przypisywania licencji: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Zarządzanie licencjami użytkowników Gemini Enterprise.")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-ge-demos"), help="ID projektu GCP")
    parser.add_argument("--location", default="eu", help="Lokalizacja (np. eu, us, global)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: configs
    subparsers.add_parser("configs", help="Wyświetla dostępne pule licencji")

    # Subcommand: users
    subparsers.add_parser("users", help="Wyświetla użytkowników z przypisanymi licencjami")

    # Subcommand: assign
    assign_p = subparsers.add_parser("assign", help="Przypisuje licencję podanym użytkownikom")
    assign_p.add_argument("--emails", required=True, help="Adresy e-mail rozdzielone przecinkami")
    assign_p.add_argument("--license-config", help="Pełna nazwa zasobu licenseConfig (jeśli brak, użyje pierwszej aktywnej)")

    args = parser.parse_args()
    token = get_auth_token()

    if args.command == "configs":
        configs = list_license_configs(args.project, args.location, token)
        print(f"\n=== Konfiguracje Licencji w Projekcie '{args.project}' ({args.location}) ===")
        for c in configs:
            print(f"- Nazwa: {c.get('name')}")
            print(f"  Pula: {c.get('licenseCount')} licencji | Stan: {c.get('state')} | Tier: {c.get('subscriptionTier')}")
            print(f"  Ważność: {c.get('startDate')} do {c.get('endDate')}")

    elif args.command == "users":
        users = list_user_licenses(args.project, args.location, token)
        print(f"\n=== Użytkownicy z Przypisanymi Licencjami ({len(users)} użytkowników) ===")
        print(f"{'Identyfikator / E-mail':<32} | {'Stan':<10} | {'Ostatnie Logowanie':<26}")
        print("-" * 72)
        for u in users:
            last_login = u.get("lastLoginTime", "Jeszcze nie zalogowano")
            print(f"{u.get('userPrincipal'):<32} | {u.get('licenseAssignmentState'):<10} | {last_login:<26}")

    elif args.command == "assign":
        emails = [e.strip() for e in args.emails.split(",") if e.strip()]
        cfg = args.license_config
        if not cfg:
            configs = list_license_configs(args.project, args.location, token)
            if not configs:
                print("[!] Brak dostępnych konfiguracji licencji!")
                sys.exit(1)
            cfg = configs[0].get("name")
        print(f"[*] Przypisywanie licencji '{cfg}' dla {len(emails)} użytkowników...")
        res = batch_assign_licenses(args.project, args.location, emails, cfg, token)
        if res and res.get("done"):
            print("✔ Pomyślnie przypisano licencje!")
            for ul in res.get("response", {}).get("userLicenses", []):
                print(f"  - {ul.get('userPrincipal')}: {ul.get('licenseAssignmentState')}")
        else:
            print(f"[!] Wynik operacji: {res}")

if __name__ == "__main__":
    main()
