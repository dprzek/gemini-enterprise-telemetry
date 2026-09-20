#!/usr/bin/env python3
"""
Wsteczna ingestja historycznych logów Cloud Logging Gemini Enterprise do BigQuery.
Tworzy i uzupełnia partycjonowane tabele telemetryczne dla zdarzeń audytowych,
aktywności użytkowników oraz operacji wnioskowania modeli GenAI z ostatnich N dni.
Gwarantuje inicjalizację wszystkich tabel i schematów, aby widoki analityczne SQL
mogły zostać natychmiast utworzone nawet w przypadku braku historycznych zdarzeń.
"""

import sys
import os
import json
import subprocess
from google.cloud import bigquery

def create_partitioned_table(client, table_id, schema):
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="timestamp"
    )
    return client.create_table(table, exists_ok=True)

def fetch_logs(project_id, filter_str, days=30, limit=1000):
    cmd = [
        "gcloud", "logging", "read", filter_str,
        f"--project={project_id}",
        f"--freshness={days}d",
        f"--limit={limit}",
        "--format=json"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        return []
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return []

def parse_activity_entry(e):
    return {
        "insert_id": e.get("insertId", ""),
        "timestamp": e.get("timestamp"),
        "user_iam_principal": e.get("jsonPayload", {}).get("userIamPrincipal", e.get("jsonPayload", {}).get("useriamprincipal", "")),
        "user_pseudo_id": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("userPseudoId", e.get("jsonPayload", {}).get("request", {}).get("userevent", {}).get("userpseudoid", "")),
        "method_name": e.get("jsonPayload", {}).get("logMetadata", {}).get("methodName", e.get("jsonPayload", {}).get("logmetadata", {}).get("methodname", "")),
        "engine": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("engine", e.get("jsonPayload", {}).get("request", {}).get("userevent", {}).get("engine", e.get("jsonPayload", {}).get("logMetadata", {}).get("name", ""))),
        "page_type": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("agentspaceInfo", {}).get("agentspacePageType", e.get("jsonPayload", {}).get("request", {}).get("userevent", {}).get("agentspaceinfo", {}).get("agentspacepagetype", "")),
        "event_type": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("eventType", e.get("jsonPayload", {}).get("request", {}).get("userevent", {}).get("eventtype", "")),
        "agent_id": (e.get("jsonPayload", {}).get("request", {}).get("agentsSpec", {}).get("agentSpecs", [{}])[0].get("agentId", "") if e.get("jsonPayload", {}).get("request", {}).get("agentsSpec") else ""),
        "raw_payload": json.dumps(e.get("jsonPayload", {}))
    }

def parse_inference_entry(e):
    jp = e.get("jsonPayload", {})
    return {
        "insert_id": e.get("insertId", ""),
        "timestamp": e.get("timestamp"),
        "user_id": jp.get("user.id", jp.get("user_id", "")),
        "conversation_id": jp.get("gen_ai.conversation.id", jp.get("conversation_id", "")),
        "agent_name": jp.get("gen_ai.agent.name", e.get("resource", {}).get("labels", {}).get("agent_id", "")),
        "engine_id": e.get("resource", {}).get("labels", {}).get("engine_id", ""),
        "assistant_id": e.get("resource", {}).get("labels", {}).get("assistant_id", ""),
        "input_tokens": int(jp.get("gen_ai.usage.input_tokens", jp.get("gen_ai_usage_input_tokens", 0)) or 0),
        "output_tokens": int(jp.get("gen_ai.usage.output_tokens", jp.get("gen_ai_usage_output_tokens", 0)) or 0),
        "cached_tokens": int(jp.get("gen_ai.usage.cache_read.input_tokens", jp.get("gen_ai_usage_cached_tokens", 0)) or 0),
        "finish_reason": (jp.get("gen_ai.response.finish_reasons", [""])[0] if jp.get("gen_ai.response.finish_reasons") else ""),
        "raw_payload": json.dumps(jp)
    }

def init_streaming_tables(client, project_id, dataset_id):
    """Inicjalizuje puste tabele strumieniowe zlewu logów, jeśli jeszcze nie istnieją."""
    # 1. Tabela aktywności użytkownika
    user_act_schema = [
        bigquery.SchemaField("logName", "STRING"),
        bigquery.SchemaField("timestamp", "TIMESTAMP"),
        bigquery.SchemaField("receiveTimestamp", "TIMESTAMP"),
        bigquery.SchemaField("severity", "STRING"),
        bigquery.SchemaField("insertId", "STRING"),
        bigquery.SchemaField("trace", "STRING"),
        bigquery.SchemaField("spanId", "STRING"),
        bigquery.SchemaField("useriamprincipal", "STRING"),
        bigquery.SchemaField("jsonPayload", "RECORD", fields=[
            bigquery.SchemaField("useriamprincipal", "STRING"),
            bigquery.SchemaField("logmetadata", "RECORD", fields=[
                bigquery.SchemaField("timestamp", "STRING"),
                bigquery.SchemaField("methodname", "STRING"),
                bigquery.SchemaField("servicename", "STRING"),
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("servicelabel", "STRING"),
            ]),
            bigquery.SchemaField("response", "RECORD", fields=[
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("displayname", "STRING"),
                bigquery.SchemaField("description", "STRING"),
                bigquery.SchemaField("answer", "RECORD", fields=[
                    bigquery.SchemaField("name", "STRING"),
                    bigquery.SchemaField("state", "STRING"),
                ]),
                bigquery.SchemaField("agentinfo", "RECORD", fields=[
                    bigquery.SchemaField("spiffeid", "STRING"),
                    bigquery.SchemaField("displayname", "STRING"),
                    bigquery.SchemaField("agentkind", "STRING"),
                    bigquery.SchemaField("agent", "STRING"),
                ]),
            ]),
            bigquery.SchemaField("request", "RECORD", fields=[
                bigquery.SchemaField("parent", "STRING"),
                bigquery.SchemaField("userevent", "RECORD", fields=[
                    bigquery.SchemaField("engine", "STRING"),
                    bigquery.SchemaField("eventtime", "STRING"),
                    bigquery.SchemaField("userpseudoid", "STRING"),
                    bigquery.SchemaField("eventtype", "STRING"),
                    bigquery.SchemaField("agentspaceinfo", "RECORD", fields=[
                        bigquery.SchemaField("agentspacepagetype", "STRING"),
                    ]),
                ]),
            ]),
        ]),
    ]
    create_partitioned_table(client, f"{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity", user_act_schema)

    # 2. Tabela operacji wnioskowania GenAI
    inference_schema = [
        bigquery.SchemaField("logName", "STRING"),
        bigquery.SchemaField("timestamp", "TIMESTAMP"),
        bigquery.SchemaField("receiveTimestamp", "TIMESTAMP"),
        bigquery.SchemaField("severity", "STRING"),
        bigquery.SchemaField("insertId", "STRING"),
        bigquery.SchemaField("trace", "STRING"),
        bigquery.SchemaField("spanId", "STRING"),
        bigquery.SchemaField("jsonPayload", "RECORD", fields=[
            bigquery.SchemaField("gen_ai_usage_input_tokens", "FLOAT"),
            bigquery.SchemaField("gen_ai_usage_output_tokens", "FLOAT"),
            bigquery.SchemaField("gen_ai_usage_reasoning_output_tokens", "FLOAT"),
            bigquery.SchemaField("gen_ai_agent_name", "STRING"),
            bigquery.SchemaField("gen_ai_conversation_id", "STRING"),
            bigquery.SchemaField("gcp_vertex_agent_invocation_id", "STRING"),
            bigquery.SchemaField("gcp_vertex_agent_event_id", "STRING"),
            bigquery.SchemaField("gen_ai_response_finish_reasons", "STRING", mode="REPEATED"),
        ]),
    ]
    create_partitioned_table(client, f"{project_id}.{dataset_id}.discoveryengine_googleapis_com_gen_ai_client_inference_operation_details", inference_schema)

def run_backfill(client, project_id, dataset_id, days=30):
    """Główna procedura wstecznej ingestji logów."""
    print(f"=== Wsteczna ingestja logów Gemini Enterprise dla {project_id} (Ostatnie {days} dni) ===")
    init_streaming_tables(client, project_id, dataset_id)

    # Konfiguracja zadań ingestji
    tasks = [
        {
            "name": "Cloud Audit Activity",
            "filter": f'logName=~"cloudaudit.googleapis.com" AND protoPayload.serviceName="discoveryengine.googleapis.com"',
            "table": f"{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity",
            "schema": [
                bigquery.SchemaField("insert_id", "STRING"),
                bigquery.SchemaField("timestamp", "TIMESTAMP"),
                bigquery.SchemaField("principal_email", "STRING"),
                bigquery.SchemaField("method_name", "STRING"),
                bigquery.SchemaField("resource_name", "STRING"),
                bigquery.SchemaField("raw_payload", "STRING"),
                bigquery.SchemaField("protopayload_auditlog", "RECORD", fields=[
                    bigquery.SchemaField("methodName", "STRING"),
                    bigquery.SchemaField("resourceName", "STRING"),
                    bigquery.SchemaField("authenticationInfo", "RECORD", fields=[
                        bigquery.SchemaField("principalEmail", "STRING"),
                    ]),
                ]),
            ],
            "transform": lambda e: {
                "insert_id": e.get("insertId", ""),
                "timestamp": e.get("timestamp"),
                "principal_email": e.get("protoPayload", {}).get("authenticationInfo", {}).get("principalEmail", "unknown"),
                "method_name": e.get("protoPayload", {}).get("methodName", ""),
                "resource_name": e.get("protoPayload", {}).get("resourceName", ""),
                "raw_payload": json.dumps(e.get("protoPayload", {})),
                "protopayload_auditlog": {
                    "methodName": e.get("protoPayload", {}).get("methodName", ""),
                    "resourceName": e.get("protoPayload", {}).get("resourceName", ""),
                    "authenticationInfo": {
                        "principalEmail": e.get("protoPayload", {}).get("authenticationInfo", {}).get("principalEmail", "unknown")
                    }
                }
            }
        },
        {
            "name": "Aktywność Użytkowników",
            "filter": f'logName="projects/{project_id}/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity"',
            "table": f"{project_id}.{dataset_id}.gemini_enterprise_user_activity",
            "schema": [
                bigquery.SchemaField("insert_id", "STRING"),
                bigquery.SchemaField("timestamp", "TIMESTAMP"),
                bigquery.SchemaField("user_iam_principal", "STRING"),
                bigquery.SchemaField("user_pseudo_id", "STRING"),
                bigquery.SchemaField("method_name", "STRING"),
                bigquery.SchemaField("engine", "STRING"),
                bigquery.SchemaField("page_type", "STRING"),
                bigquery.SchemaField("event_type", "STRING"),
                bigquery.SchemaField("agent_id", "STRING"),
                bigquery.SchemaField("raw_payload", "STRING"),
            ],
            "transform": lambda e: {
                "insert_id": e.get("insertId", ""),
                "timestamp": e.get("timestamp"),
                "user_iam_principal": e.get("jsonPayload", {}).get("userIamPrincipal", ""),
                "user_pseudo_id": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("userPseudoId", ""),
                "method_name": e.get("jsonPayload", {}).get("logMetadata", {}).get("methodName", ""),
                "engine": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("engine", e.get("jsonPayload", {}).get("logMetadata", {}).get("name", "")),
                "page_type": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("agentspaceInfo", {}).get("agentspacePageType", ""),
                "event_type": e.get("jsonPayload", {}).get("request", {}).get("userEvent", {}).get("eventType", ""),
                "agent_id": (e.get("jsonPayload", {}).get("request", {}).get("agentsSpec", {}).get("agentSpecs", [{}])[0].get("agentId", "")),
                "raw_payload": json.dumps(e.get("jsonPayload", {}))
            }
        },
        {
            "name": "Wnioskowanie Modeli GenAI (Tokeny)",
            "filter": f'logName="projects/{project_id}/logs/discoveryengine.googleapis.com%2Fgen_ai.client.inference.operation.details"',
            "table": f"{project_id}.{dataset_id}.gen_ai_client_inference_operation_details",
            "schema": [
                bigquery.SchemaField("insert_id", "STRING"),
                bigquery.SchemaField("timestamp", "TIMESTAMP"),
                bigquery.SchemaField("user_id", "STRING"),
                bigquery.SchemaField("conversation_id", "STRING"),
                bigquery.SchemaField("agent_name", "STRING"),
                bigquery.SchemaField("engine_id", "STRING"),
                bigquery.SchemaField("assistant_id", "STRING"),
                bigquery.SchemaField("input_tokens", "INT64"),
                bigquery.SchemaField("output_tokens", "INT64"),
                bigquery.SchemaField("cached_tokens", "INT64"),
                bigquery.SchemaField("finish_reason", "STRING"),
                bigquery.SchemaField("raw_payload", "STRING"),
            ],
            "transform": lambda e: {
                "insert_id": e.get("insertId", ""),
                "timestamp": e.get("timestamp"),
                "user_id": e.get("jsonPayload", {}).get("user.id", ""),
                "conversation_id": e.get("jsonPayload", {}).get("gen_ai.conversation.id", ""),
                "agent_name": e.get("jsonPayload", {}).get("gen_ai.agent.name", e.get("resource", {}).get("labels", {}).get("agent_id", "")),
                "engine_id": e.get("resource", {}).get("labels", {}).get("engine_id", ""),
                "assistant_id": e.get("resource", {}).get("labels", {}).get("assistant_id", ""),
                "input_tokens": int(e.get("jsonPayload", {}).get("gen_ai.usage.input_tokens", 0) or 0),
                "output_tokens": int(e.get("jsonPayload", {}).get("gen_ai.usage.output_tokens", 0) or 0),
                "cached_tokens": int(e.get("jsonPayload", {}).get("gen_ai.usage.cache_read.input_tokens", 0) or 0),
                "finish_reason": (e.get("jsonPayload", {}).get("gen_ai.response.finish_reasons", [""])[0] if e.get("jsonPayload", {}).get("gen_ai.response.finish_reasons") else ""),
                "raw_payload": json.dumps(e.get("jsonPayload", {}))
            }
        }
    ]

    for t in tasks:
        print(f"--> Przetwarzanie: {t['name']}...")
        create_partitioned_table(client, t["table"], t["schema"])
        entries = fetch_logs(project_id, t["filter"], days=days)
        print(f"    Pobrano {len(entries)} wpisów.")
        if entries:
            rows = [t["transform"](e) for e in entries]
            errors = client.insert_rows_json(t["table"], rows)
            if errors:
                print(f"    ⚠️ Błędy zapisu do {t['table']}: {errors}")
            else:
                print(f"    ✔ Zapisano {len(rows)} rekordów do {t['table']}.")

    print("✔ Wsteczna ingestja logów zakończona sukcesem!")

if __name__ == "__main__":
    p_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not p_id:
        try:
            import subprocess
            p_id = subprocess.check_output(["gcloud", "config", "get-value", "project"], text=True).strip()
        except Exception:
            pass
    if not p_id:
        print("Błąd: Nie podano identyfikatora projektu GCP. Użyj: python3 backfill_logs_to_bigquery.py <PROJECT_ID>")
        sys.exit(1)
    d_id = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DATASET_ID", "gemini_enterprise_telemetry")
    d_days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    bq_client = bigquery.Client(project=p_id)
    run_backfill(bq_client, p_id, d_id, d_days)
