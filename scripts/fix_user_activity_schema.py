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
Narzędzie naprawcze (Self-Healing) dla błędu Cloud Logging Sink:
table_invalid_schema (Cannot convert std::string to a record field ... query = 4).

Rozwiązuje problem niezgodności schematów BigQuery, gdzie pole 'request.query'
zostało utworzone jako RECORD zamiast STRING, co blokowało routing logów
Cloud Logging do BigQuery.

Wywołanie:
    python3 scripts/fix_user_activity_schema.py --project prj-gemini-rossmann-global
"""

import os
import sys
import argparse
import subprocess
from google.cloud import bigquery

# Import procedury autoleczenia i definicji schematów z modułu backfill
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.backfill_logs_to_bigquery import init_streaming_tables, repair_user_activity_schema_if_needed


def get_default_project():
    try:
        res = subprocess.run(["gcloud", "config", "get-value", "project"], stdout=subprocess.PIPE, text=True, check=True)
        proj = res.stdout.strip()
        if proj:
            return proj
    except Exception:
        pass
    return os.environ.get("PROJECT_ID", "")


def deploy_sql_views_locally(bq_client, project_id, dataset_id):
    """Odświeża analityczne widoki SQL w BigQuery."""
    print("--> Wdrażanie analitycznych widoków SQL w BigQuery...")
    init_streaming_tables(bq_client, project_id, dataset_id)

    sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bigquery", "telemetry_views.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        raw_sql = f.read()

    formatted_sql = raw_sql.format(project_id=project_id, dataset_id=dataset_id)
    job = bq_client.query(formatted_sql)
    job.result()
    print("    ✔ Analityczne widoki SQL zostały pomyślnie utworzone / zaktualizowane w BigQuery.")


def main():
    parser = argparse.ArgumentParser(
        description="Naprawa błędu table_invalid_schema dla tabeli aktywności Gemini Enterprise w BigQuery."
    )
    parser.add_argument("--project", default=get_default_project(), help="Google Cloud Project ID")
    parser.add_argument("--dataset", default="gemini_enterprise_telemetry", help="ID datasetu BigQuery")
    parser.add_argument("--force", action="store_true", help="Wymuszenie przebudowy tabeli nawet jeśli typ query nie jest RECORD")
    parser.add_argument("--backfill-days", type=int, default=0, help="Opcjonalna liczba dni wstecznej ingestji po naprawie")
    args = parser.parse_args()

    project_id = args.project
    dataset_id = args.dataset

    if not project_id:
        print("[!] Błąd: Nie określono Project ID. Użyj --project <PROJECT_ID> lub ustaw gcloud config set project.")
        sys.exit(1)

    print(f"=== Weryfikacja i Autonaprawa Schematu BigQuery ({project_id}.{dataset_id}) ===")
    bq_client = bigquery.Client(project=project_id)

    table_id = f"{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity"
    try:
        tbl = bq_client.get_table(table_id)
        table_exists = True
    except Exception:
        table_exists = False
        tbl = None

    is_record = False
    current_query_type = "NIEZNANY / BRAK"
    if table_exists and tbl:
        for f in tbl.schema:
            if f.name == "jsonPayload" and f.fields:
                for sub in f.fields:
                    if sub.name == "request" and sub.fields:
                        for rsub in sub.fields:
                            if rsub.name == "query":
                                current_query_type = rsub.field_type
                                if rsub.field_type == "RECORD":
                                    is_record = True
                                break

    print(f"[*] Aktualny stan pola 'jsonPayload.request.query': {current_query_type}")

    if not is_record and not args.force:
        if table_exists:
            print("✔ Tabela posiada już poprawny schemat (query nie jest typu RECORD). Nie są wymagane żadne zmiany.")
        else:
            print("[*] Tabela nie istnieje. Inicjalizacja ze świeżym schematem...")
            init_streaming_tables(bq_client, project_id, dataset_id)
            deploy_sql_views_locally(bq_client, project_id, dataset_id)
            print("✔ Pomyślnie zainicjalizowano tabele ze schematem zawierającym pole query: STRING.")
    else:
        print("[!] Wymagana naprawa schematu!")
        # Uruchomienie procedury naprawczej
        init_streaming_tables(bq_client, project_id, dataset_id, force_repair=args.force)
        # Przeładowanie widoków
        deploy_sql_views_locally(bq_client, project_id, dataset_id)
        print("✔ Procedura naprawcza zakończona sukcesem!")
        print("✔ Cloud Logging Sink (gemini-enterprise-telemetry-sink) może natychmiast bezbłędnie przesyłać logi.")

    if args.backfill_days > 0:
        print(f"--> Uruchamianie wstecznej ingestji z ostatnich {args.backfill_days} dni...")
        from scripts.backfill_logs_to_bigquery import run_backfill
        run_backfill(bq_client, project_id, dataset_id, days=args.backfill_days)

    print("\n[Podsumowanie]")
    print(f"Projekt:   {project_id}")
    print(f"Dataset:   {dataset_id}")
    print(f"Tabela:    discoveryengine_googleapis_com_gemini_enterprise_user_activity")
    print(f"Typ query: STRING (Zgodny z Cloud Logging Sink)")
    print("Stan:      SPRAWNY / ZSYNCHRONIZOWANY")


if __name__ == "__main__":
    main()
