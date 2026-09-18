#!/usr/bin/env python3
"""
Backfill historical Gemini Enterprise logs from Cloud Logging into BigQuery.
Ensures instant telemetry availability for past activity.
"""
import sys
import json
import subprocess
from datetime import datetime
from google.cloud import bigquery

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else "adk-dev-485808"
DATASET_ID = sys.argv[2] if len(sys.argv) > 2 else "gemini_enterprise_telemetry"
DAYS = int(sys.argv[3]) if len(sys.argv) > 3 else 30

client = bigquery.Client(project=PROJECT_ID)

print(f"=== Backfilling Gemini Enterprise logs for {PROJECT_ID} (Past {DAYS} days) ===")

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
        print(f"Error fetching logs: {res.stderr}")
        return []
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return []

# 1. Backfill Cloud Audit Activity (Agent creation, modification)
print("--> Fetching Cloud Audit logs for Discovery Engine / Gemini Enterprise...")
audit_logs = fetch_logs('logName=~"cloudaudit.googleapis.com" AND protoPayload.serviceName="discoveryengine.googleapis.com"')
print(f"    Found {len(audit_logs)} audit log entries.")

if audit_logs:
    table_id = f"{PROJECT_ID}.{DATASET_ID}.cloudaudit_googleapis_com_activity"
    schema = [
        bigquery.SchemaField("insert_id", "STRING"),
        bigquery.SchemaField("timestamp", "TIMESTAMP"),
        bigquery.SchemaField("principal_email", "STRING"),
        bigquery.SchemaField("method_name", "STRING"),
        bigquery.SchemaField("resource_name", "STRING"),
        bigquery.SchemaField("raw_payload", "STRING"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="timestamp")
    client.create_table(table, exists_ok=True)
    
    rows = []
    for entry in audit_logs:
        proto = entry.get("protoPayload", {})
        auth = proto.get("authenticationInfo", {})
        rows.append({
            "insert_id": entry.get("insertId", ""),
            "timestamp": entry.get("timestamp"),
            "principal_email": auth.get("principalEmail", "unknown"),
            "method_name": proto.get("methodName", ""),
            "resource_name": proto.get("resourceName", ""),
            "raw_payload": json.dumps(proto)
        })
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        print(f"    Errors inserting audit rows: {errors}")
    else:
        print(f"    Inserted {len(rows)} audit records into {table_id}.")

# 2. Backfill Gemini Enterprise User Activity
print("--> Fetching Gemini Enterprise User Activity logs...")
user_logs = fetch_logs('logName="projects/' + PROJECT_ID + '/logs/discoveryengine.googleapis.com%2Fgemini_enterprise_user_activity"')
print(f"    Found {len(user_logs)} user activity log entries.")

if user_logs:
    table_id = f"{PROJECT_ID}.{DATASET_ID}.gemini_enterprise_user_activity"
    schema = [
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
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="timestamp")
    client.create_table(table, exists_ok=True)
    
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
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        print(f"    Errors inserting user activity rows: {errors}")
    else:
        print(f"    Inserted {len(rows)} user activity records into {table_id}.")

# 3. Backfill Inference Operation Details (Token Metrics)
print("--> Fetching GenAI Inference Operation Details...")
inference_logs = fetch_logs('logName="projects/' + PROJECT_ID + '/logs/discoveryengine.googleapis.com%2Fgen_ai.client.inference.operation.details"')
print(f"    Found {len(inference_logs)} inference log entries.")

if inference_logs:
    table_id = f"{PROJECT_ID}.{DATASET_ID}.gen_ai_client_inference_operation_details"
    schema = [
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
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="timestamp")
    client.create_table(table, exists_ok=True)
    
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
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        print(f"    Errors inserting inference rows: {errors}")
    else:
        print(f"    Inserted {len(rows)} inference records into {table_id}.")

print("=== Backfill completed successfully! ===")
