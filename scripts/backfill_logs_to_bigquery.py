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

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GOOGLE_CLOUD_PROJECT", "adk-dev-485808")
DATASET_ID = sys.argv[2] if len(sys.argv) > 2 else "gemini_enterprise_telemetry"
DAYS = int(sys.argv[3]) if len(sys.argv) > 3 else 30

client = bigquery.Client(project=PROJECT_ID)

print(f"=== Wsteczna ingestja logów Gemini Enterprise dla {PROJECT_ID} (Ostatnie {DAYS} dni) ===")

def fetch_logs(filter_str, limit=1000):
    cmd = [
        "gcloud", "logging", "read", filter_str,
        f"--project={PROJECT_ID}",
        f"--freshness={DAYS}d",
        f"--limit={limit}",
        "--format=json"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"Błąd podczas pobierania logów: {res.stderr}")
        return []
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return []

def ensure_table(table_id, schema):
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="timestamp")
    client.create_table(table, exists_ok=True)

# 0. Inicjalizacja tabeli czasu rzeczywistego ze zlewu Cloud Logging
print("--> Inicjalizacja partycjonowanych tabel telemetrycznych...")
discovery_sink_table_id = f"{PROJECT_ID}.{DATASET_ID}.discoveryengine_googleapis_com_gemini_enterprise_user_activity"
discovery_sink_schema = [
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
ensure_table(discovery_sink_table_id, discovery_sink_schema)

discovery_inference_sink_table_id = f"{PROJECT_ID}.{DATASET_ID}.discoveryengine_googleapis_com_gen_ai_client_inference_operation_details"
discovery_inference_sink_schema = [
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
ensure_table(discovery_inference_sink_table_id, discovery_inference_sink_schema)

# 1. Wsteczna ingestja Cloud Audit Activity (tworzenie i modyfikacja agentów)
print("--> Pobieranie logów Cloud Audit dla Discovery Engine / Gemini Enterprise...")
audit_logs = fetch_logs('logName=~"cloudaudit.googleapis.com" AND protoPayload.serviceName="discoveryengine.googleapis.com"')
print(f"    Znaleziono {len(audit_logs)} wpisów logów audytowych.")

audit_table_id = f"{PROJECT_ID}.{DATASET_ID}.cloudaudit_googleapis_com_activity"
audit_schema = [
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
]
ensure_table(audit_table_id, audit_schema)

if audit_logs:
    rows = []
    for entry in audit_logs:
        proto = entry.get("protoPayload", {})
        auth = proto.get("authenticationInfo", {})
        p_email = auth.get("principalEmail", "unknown")
        m_name = proto.get("methodName", "")
        r_name = proto.get("resourceName", "")
        rows.append({
            "insert_id": entry.get("insertId", ""),
            "timestamp": entry.get("timestamp"),
            "principal_email": p_email,
            "method_name": m_name,
            "resource_name": r_name,
            "raw_payload": json.dumps(proto),
            "protopayload_auditlog": {
                "methodName": m_name,
                "resourceName": r_name,
                "authenticationInfo": {
                    "principalEmail": p_email
                }
            }
        })
    errors = client.insert_rows_json(audit_table_id, rows)
    if errors:
        print(f"    Błędy podczas wstawiania wierszy audytu: {errors}")
    else:
        print(f"    Wstawiono {len(rows)} rekordów audytowych do {audit_table_id}.")

# 2. Wsteczna ingestja aktywności użytkowników Gemini Enterprise
print("--> Pobieranie logów aktywności użytkowników Gemini Enterprise...")
user_logs = fetch_logs('logName="projects/' + PROJECT_ID + '/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity"')
print(f"    Znaleziono {len(user_logs)} wpisów aktywności użytkowników.")

user_table_id = f"{PROJECT_ID}.{DATASET_ID}.gemini_enterprise_user_activity"
user_schema = [
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
]
ensure_table(user_table_id, user_schema)

if user_logs:
    rows = []
    for entry in user_logs:
        jp = entry.get("jsonPayload", {})
        meta = jp.get("logMetadata", {})
        req = jp.get("request", {})
        ue = req.get("userEvent", {})
        agent_specs = req.get("agentsSpec", {}).get("agentSpecs", [])
        agent_id = agent_specs[0].get("agentId") if agent_specs else ""
        
        rows.append({
            "insert_id": entry.get("insertId", ""),
            "timestamp": entry.get("timestamp"),
            "user_iam_principal": jp.get("userIamPrincipal", ""),
            "user_pseudo_id": ue.get("userPseudoId", ""),
            "method_name": meta.get("methodName", ""),
            "engine": ue.get("engine", meta.get("name", "")),
            "page_type": ue.get("agentspaceInfo", {}).get("agentspacePageType", ""),
            "event_type": ue.get("eventType", ""),
            "agent_id": agent_id,
            "raw_payload": json.dumps(jp)
        })
    errors = client.insert_rows_json(user_table_id, rows)
    if errors:
        print(f"    Błędy podczas wstawiania wierszy aktywności: {errors}")
    else:
        print(f"    Wstawiono {len(rows)} rekordów aktywności użytkowników do {user_table_id}.")

# 3. Wsteczna ingestja operacji wnioskowania GenAI (tokeny)
print("--> Pobieranie szczegółów operacji wnioskowania GenAI...")
inference_logs = fetch_logs('logName="projects/' + PROJECT_ID + '/logs/discoveryengine.googleapis.com%2Fgen_ai.client.inference.operation.details"')
print(f"    Znaleziono {len(inference_logs)} wpisów logów wnioskowania.")

inference_table_id = f"{PROJECT_ID}.{DATASET_ID}.gen_ai_client_inference_operation_details"
inference_schema = [
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
]
ensure_table(inference_table_id, inference_schema)

if inference_logs:
    rows = []
    for entry in inference_logs:
        jp = entry.get("jsonPayload", {})
        res = entry.get("resource", {}).get("labels", {})
        finish_reasons = jp.get("gen_ai.response.finish_reasons", [])
        finish_reason = finish_reasons[0] if finish_reasons else ""
        
        rows.append({
            "insert_id": entry.get("insertId", ""),
            "timestamp": entry.get("timestamp"),
            "user_id": jp.get("user.id", ""),
            "conversation_id": jp.get("gen_ai.conversation.id", ""),
            "agent_name": jp.get("gen_ai.agent.name", res.get("agent_id", "")),
            "engine_id": res.get("engine_id", ""),
            "assistant_id": res.get("assistant_id", ""),
            "input_tokens": int(jp.get("gen_ai.usage.input_tokens", 0) or 0),
            "output_tokens": int(jp.get("gen_ai.usage.output_tokens", 0) or 0),
            "cached_tokens": int(jp.get("gen_ai.usage.cache_read.input_tokens", 0) or 0),
            "finish_reason": finish_reason,
            "raw_payload": json.dumps(jp)
        })
    errors = client.insert_rows_json(inference_table_id, rows)
    if errors:
        print(f"    Błędy podczas wstawiania wierszy wnioskowania: {errors}")
    else:
        print(f"    Wstawiono {len(rows)} rekordów wnioskowania do {inference_table_id}.")

print("=== Inicjalizacja tabel oraz wsteczna ingestja zakończona pomyślnie! ===")
