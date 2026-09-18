---
name: gemini-enterprise-telemetry
description: >-
  Deploy, configure, and query Gemini Enterprise telemetry, user adoption, and OpenTelemetry observability.
  Tracks per-user utilization with day-by-day breakdowns, OpenTelemetry traces and spans in Cloud Trace,
  operational metrics (sessions, conversational depth, tool adoption rate, time-to-first-token TTFT),
  pooled quota limits and burn rates (assistant queries, agent building, deep research, images/video, WTU credits),
  BigQuery analytical views, Cloud Monitoring dashboards, and agent deployment in Gemini Enterprise.
---

# Gemini Enterprise Telemetry & Observability Monitoring Skill

This skill provides procedures, automation scripts, SQL views, and agent configurations to monitor and report telemetry on Google Cloud **Gemini Enterprise** usage, adoption, and performance across an organization.

## Architecture & Data Flow

1. **Cloud Logging & Audit Logs Sink**: Automatically captures user activity, prompt interactions, model inference tokens, OpenTelemetry trace spans, and administrative actions (`CreateAgent`, `UpdateAgent`).
2. **BigQuery Telemetry Dataset (`gemini_enterprise_telemetry`)**: Stores partitioned logs with 6 analytical SQL views:
   - `v_user_daily_utilization`: Per-user queries, active days, deep research, agents created, and tokens in day-by-day granularity.
   - `v_observability_traces`: OpenTelemetry distributed trace and span linkage (trace IDs, span IDs, methods, execution states).
   - `v_user_summary`: All-time per-user aggregate metrics.
   - `v_daily_adoption`: Organization-wide DAU, WAU, query volume trends.
   - `v_feature_usage`: Breakdown across Gemini Enterprise features.
   - `v_token_telemetry`: Input, output, and cache token metrics.
3. **Cloud Monitoring & OpenTelemetry Integration**:
   - Observability settings: `observabilityConfig` (enables OpenTelemetry spans & sensitive logging).
   - Real-time operational metrics: `agent_session_count`, `agent_turn_count` (conversational depth), `agent_session_with_tool_count` (tool adoption rate), and `engine/time_to_first_token_latency` (TTFT).
   - Real-time pooled quota limits and usage against edition thresholds (`discoveryengine.googleapis.com/quota/*`).
4. **Gemini Enterprise Agent**: Deployed directly in Gemini Enterprise Agent Designer (`rossmann-agent-designer` in `eu`).
   - Initiates conversations with an **opening statement of metrics offered** (User utilization, Adoption & Engagement, Observability & Traces, Quotas).
   - Answers queries on day-by-day adoption, user rankings, latencies, and quota burn rates.
5. **Admin CLI**: Instant querying of day-by-day utilization (`--daily`), adoption trends, and OpenTelemetry metrics (`python3 cli/telemetry_cli.py observability --traces`).

---

## Prerequisites & Required IAM Roles

To deploy the telemetry pipeline in any customer Google Cloud project, ensure the following roles are granted:

| Role | Purpose |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Manage and deploy agents in Discovery Engine / Gemini Enterprise |
| `roles/logging.configWriter` | Create Cloud Logging sink routing logs to BigQuery |
| `roles/bigquery.admin` | Create BigQuery dataset, tables, and views |
| `roles/monitoring.viewer` / `roles/monitoring.editor` | Query quota metrics and deploy Cloud Monitoring dashboard |
| `roles/cloudtrace.user` | View and inspect distributed traces in Cloud Trace |
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

---

## Key CLI Commands

### 1. Observability & OpenTelemetry Metrics:
```bash
python3 cli/telemetry_cli.py observability --traces
```

### 2. Day-by-Day User Utilization:
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@mycompany.com
```

### 3. Organization Adoption Trends (DAU):
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

### 4. Real-time Quotas & Headroom:
```bash
python3 cli/telemetry_cli.py quotas
```
