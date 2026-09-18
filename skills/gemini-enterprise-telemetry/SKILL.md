---
name: gemini-enterprise-telemetry
description: >-
  Deploy, configure, and query Gemini Enterprise telemetry and user adoption monitoring.
  Tracks per-user utilization over precise time spans, quota limits and burn rates (assistant
  queries, agent building, deep research, image/video generation, WTU dev credits, data indexing),
  BigQuery analytical views, Cloud Monitoring dashboards, and agent deployment to Gemini Enterprise.
---

# Gemini Enterprise Telemetry & Adoption Monitoring Skill

This skill provides procedures, automation scripts, SQL views, and agent configurations to monitor and report telemetry on Google Cloud **Gemini Enterprise** usage across an organization.

## Architecture & Data Flow

1. **Cloud Logging & Audit Logs Sink**: Automatically captures user activity, prompt interactions, model inference tokens, and administrative actions (`CreateAgent`, `UpdateAgent`).
2. **BigQuery Telemetry Dataset (`gemini_enterprise_telemetry`)**: Stores partitioned logs with 5 analytical SQL views:
   - `v_user_utilization`: Per-user queries, active days, deep research, agents created, tokens.
   - `v_daily_adoption`: Organization-wide DAU, WAU, query volume trends.
   - `v_feature_usage`: Breakdown across Gemini Enterprise features.
   - `v_agent_creation_audit`: Users creating and modifying agents.
   - `v_token_telemetry`: Input, output, and cache token metrics.
3. **Cloud Monitoring Integration**: Tracks real-time pooled quota limits and usage against edition thresholds (`discoveryengine.googleapis.com/quota/*`).
4. **Gemini Enterprise Agent**: Deployed directly in the Gemini Enterprise Agent Designer to conversationally answer administrator queries.
5. **Admin CLI**: Instant querying of utilization per user over customizable time spans.

---

## Prerequisites & Required IAM Roles

To deploy the telemetry pipeline in any customer Google Cloud project, ensure the following roles are granted:

| Role | Purpose |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Manage and deploy agents in Discovery Engine / Gemini Enterprise |
| `roles/logging.configWriter` | Create Cloud Logging sink routing logs to BigQuery |
| `roles/bigquery.admin` | Create BigQuery dataset, tables, and views |
| `roles/monitoring.viewer` / `roles/monitoring.editor` | Query quota metrics and deploy Cloud Monitoring dashboard |
| `roles/resourcemanager.projectIamAdmin` | Grant BigQuery Data Editor to the sink service account |

---

## One-Command Automated Deployment

Run the automated deployment script pointing to the customer's project and engine:

```bash
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

Example for EU engine `rossmann-agent-designer`:
```bash
./scripts/deploy_pipeline.sh adk-dev-485808 eu rossmann-agent-designer_1784194686764 gemini_enterprise_telemetry
```

### What this script automates:
1. Provisions BigQuery dataset `gemini_enterprise_telemetry` with partitioning.
2. Creates Cloud Logging sink `gemini-enterprise-telemetry-sink` filtering Discovery Engine and Audit logs.
3. Grants `roles/bigquery.dataEditor` to the sink writer identity.
4. Backfills historical logs from the past 30 days into BigQuery.
5. Deploys the 5 SQL analytical views.
6. Provisions the Cloud Monitoring dashboard.
7. Deploys the Telemetry & Adoption Agent to Gemini Enterprise.

---

## Step-by-Step Manual Runbook

### Step 1: BigQuery Logging Sink
```bash
./scripts/setup_bigquery_sink.sh <PROJECT_ID> <LOCATION> <DATASET_ID> <SINK_NAME>
```

### Step 2: Backfill Historical Logs
```bash
python3 scripts/backfill_logs_to_bigquery.py <PROJECT_ID> <DATASET_ID> 30
```

### Step 3: Create Analytical Views
```bash
sed "s/adk-dev-485808/<PROJECT_ID>/g; s/gemini_enterprise_telemetry/<DATASET_ID>/g" \
  bigquery/telemetry_views.sql | bq query --project_id=<PROJECT_ID> --use_legacy_sql=false
```

### Step 4: Deploy Cloud Monitoring Dashboard
```bash
gcloud monitoring dashboards create \
  --config-from-file=monitoring/gemini_enterprise_telemetry_dashboard.json \
  --project=<PROJECT_ID>
```

### Step 5: Deploy the Telemetry Agent
```bash
GOOGLE_CLOUD_PROJECT=<PROJECT_ID> \
GOOGLE_CLOUD_LOCATION=<LOCATION> \
GEMINI_ENGINE_ID=<ENGINE_ID> \
python3 agent/deploy_agent.py
```

---

## Querying Telemetry via CLI

The included CLI provides instant answers for administrators:

### 1. Per-User Utilization in Precise Time Span
```bash
python3 cli/telemetry_cli.py utilization --user admin@example.com --from-date 2026-09-01 --to-date 2026-09-18
```

### 2. Top Active Users Overview
```bash
python3 cli/telemetry_cli.py utilization
```

### 3. Daily Adoption Trends (DAU, Events, Queries)
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

### 4. Quota Limits & Reset Status
```bash
python3 cli/telemetry_cli.py quotas
```

### 5. Export Markdown Digest
```bash
python3 cli/telemetry_cli.py report --output /path/to/report.md
```

---

## Quota Limits & Reset Reference

Refer to [Google Cloud Gemini Enterprise Quotas](https://docs.cloud.google.com/gemini/enterprise/docs/quotas-and-overages):

| Feature | Standard Edition | Plus Edition | Reset Schedule |
| :--- | :--- | :--- | :--- |
| **Assistant Queries** | 160 / user / day | 200 / user / day | Daily at midnight PT (Pooled) |
| **Agent Building** | 1 / user / day | 10 / user / day | Daily at midnight PT (Pooled) |
| **Deep Research** | 3 / user / day | 10 / user / day | Daily at midnight PT (Pooled) |
| **Image Generation** | 5 / user / day | 10 / user / day | Daily at midnight PT (Pooled) |
| **Video Generation** | 2 / user / day | 3 / user / day | Daily at midnight PT (Pooled) |
| **AI Developer Tools**| $10 / user / window | $15 / user / window | Rolling 7-day pooled window |
| **Storage & Indexing**| 30 GiB / user | 75 GiB / user | Regional pool |
