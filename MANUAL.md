# Gemini Enterprise Telemetry, Adoption & Observability Manual

This manual provides complete instructions for deploying, configuring, and operating the **Gemini Enterprise Telemetry, Adoption, Quota & OpenTelemetry Observability Suite** in any customer Google Cloud environment.

---

## 1. Architecture & Telemetry Pipeline

```
                                      Gemini Enterprise
                             (Enterprise Engine / Agent Builder)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Cloud Logging & Audit Trails                    Cloud Monitoring (Real-Time)
         - discoveryengine_googleapis_com_*              - discoveryengine.googleapis.com/quota/*
         - cloudaudit_googleapis_com_activity            - agent_session_count & agent_turn_count
         - gen_ai.client.inference.operation.details     - agent_session_with_tool_count
                      │                                  - engine/time_to_first_token_latency (TTFT)
                      ▼ (Log Sink)                       - agent_total_latencies & tool_latencies
           BigQuery Telemetry Dataset                                 │
           (gemini_enterprise_telemetry)                              │
           - Partitioned & Clustered Tables                           │
           - 6 Analytical Views:                                      │
             * v_user_daily_utilization (day-by-day user breakdown)   │
             * v_observability_traces (OpenTelemetry traces & spans)  │
             * v_user_summary (all-time per user stats)               │
             * v_daily_adoption (DAU/WAU/MAU trends)                  │
             * v_feature_usage (breakdown of capabilities)            │
             * v_token_telemetry (input, output, cache tokens)        │
                      │                                               │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                        Adoption & Telemetry Service / CLI
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Gemini Enterprise Agent                           Admin CLI & Monitoring
         (Deployed in Agent Designer)                      - Day-by-day user queries (--daily)
         - Starts with statement of metrics offered        - OpenTelemetry metrics & traces
         - Full day-by-day per-user metrics                - Real-time quota alerts
         - Observability & TTFT latency reporting          - Visual Cloud Monitoring dashboard
```

---

## 2. Gemini Enterprise Observability Architecture

This solution natively integrates with the three core Google Cloud Gemini Enterprise observability capabilities:

### 2.1 Manage Observability Settings
Gemini Enterprise enables granular telemetry instrumentation at both the **Engine (Assistant app)** level and the **Individual Agent** level:

1. **Instrumentation of OpenTelemetry Traces & Logs (`observabilityEnabled`)**:
   - Enables capturing distributed trace spans, span logs, execution paths, and agent-scoped operational metrics.
2. **Sensitive Prompt & Response Logging (`sensitiveLoggingEnabled`)**:
   - Captures full user prompt inputs and model response text in Cloud Logging (requires `observabilityEnabled` to be active).

#### Enabling via Google Cloud Console:
- Navigate to **Gemini Enterprise > Configurations > Observability** tab (or **Agents > [Agent Name] > Configuration** tab).
- Toggle **Enable instrumentation of OpenTelemetry traces and logs**.
- (Optional) Toggle **Enable logging of prompt inputs and response outputs**.

#### Enabling via REST API:
```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: <PROJECT_ID>" \
  "https://<LOCATION>-discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/<LOCATION>/collections/default_collection/engines/<ENGINE_ID>?updateMask=observabilityConfig" \
  -d '{
    "observabilityConfig": {
      "observabilityEnabled": true,
      "sensitiveLoggingEnabled": true
    }
  }'
```

---

### 2.2 Access Traces & Spans (OpenTelemetry & Cloud Trace)
When instrumentation is enabled, Gemini Enterprise emits end-to-end distributed traces into **Google Cloud Trace** (retained for 30 days):

- **Trace Context**: Transmitted via standard `x-cloud-trace-context` headers and logged in `v_observability_traces`.
- **Trace Hierarchy & Spans**:
  * **Root Turn Span**: `AssistantService.StreamAssist` (or `AssistantService.Assist`) representing the entire user conversational turn.
  * **Tool Execution Spans**: `execute_tool <tool_name>` (e.g., `googleSearch`, Python code interpreter, custom enterprise tools).
  * **Connector Spans**: `invoke_connector <connector_name>` (e.g., Salesforce, Jira, Google Drive connectors).
  * **Sub-agent Spans**: `invoke_agent <agent_name>` (sub-agent delegation in multi-agent workflows).
  * **Model Inference Spans**: `model_generate_content` (capturing token usage, finish reasons, and model latencies).

---

### 2.3 Access Operational Metrics (Cloud Monitoring)
Metrics are automatically published under the `discoveryengine.googleapis.com/` namespace in Google Cloud Monitoring (retained for 6 weeks):

#### A. Engagement & Conversational Adoption Metrics:
- **`agent_session_count`**: Total conversational sessions initiated with agents.
- **`agent_session_with_tool_count`**: Sessions that actively invoked tools.
  * **Tool Adoption Rate (%)** $= \frac{\text{agent\_session\_with\_tool\_count}}{\text{agent\_session\_count}} \times 100$
- **`agent_turn_count`**: Total back-and-forth conversational turns.
  * **Conversational Depth** $= \frac{\text{agent\_turn\_count}}{\text{agent\_session\_count}}$ (measures engagement depth vs. single-turn bounce rate).

#### B. Perceived User Experience & Responsiveness:
- **`engine/time_to_first_token_latency` (TTFT)**: Latency distribution from user query submission to the generation of the first streamed response token.
- **`agent_total_latencies`**: End-to-end turn processing duration distribution.
- **`tool_total_latencies`**: Individual tool execution overhead.

---

## 3. Prerequisites & Required IAM Roles

Ensure the deployment account has the following IAM roles on the target Google Cloud project:

| Role | Purpose |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Manage and deploy agents in Gemini Enterprise / Agent Designer |
| `roles/logging.configWriter` | Create Cloud Logging sinks routing telemetry to BigQuery |
| `roles/bigquery.admin` | Create datasets, partitioned tables, and analytical views |
| `roles/monitoring.editor` | Provision Cloud Monitoring dashboards and inspect operational metrics |
| `roles/cloudtrace.user` | View and inspect distributed traces in Cloud Trace |
| `roles/resourcemanager.projectIamAdmin` | Grant BigQuery Data Editor to the Cloud Logging sink service account |

---

## 4. Automated One-Command Fast-Track Deployment

To deploy the entire solution automatically:

```bash
# 1. Clone repository
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Run automated pipeline deployment
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

### Example:
```bash
./scripts/deploy_pipeline.sh adk-dev-485808 eu rossmann-agent-designer_1784194686764 gemini_enterprise_telemetry
```

---

## 5. Step-by-Step Manual Deployment (Enterprise Change Management)

### Step 5.1: Enable Observability on Engine
```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: <PROJECT_ID>" \
  "https://<LOCATION>-discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/<LOCATION>/collections/default_collection/engines/<ENGINE_ID>?updateMask=observabilityConfig" \
  -d '{"observabilityConfig": {"observabilityEnabled": true, "sensitiveLoggingEnabled": true}}'
```

### Step 5.2: Provision BigQuery Dataset and Logging Sink
```bash
./scripts/setup_bigquery_sink.sh <PROJECT_ID> <REGION> <DATASET_ID> <SINK_NAME>
```

### Step 5.3: Backfill Historical Logs
```bash
python3 scripts/backfill_logs_to_bigquery.py <PROJECT_ID> <DATASET_ID> 30
```

### Step 5.4: Deploy Analytical BigQuery Views
```bash
sed "s/adk-dev-485808/<PROJECT_ID>/g; s/gemini_enterprise_telemetry/<DATASET_ID>/g" \
  bigquery/telemetry_views.sql | bq query --project_id=<PROJECT_ID> --use_legacy_sql=false
```

### Step 5.5: Deploy Cloud Monitoring Dashboard
```bash
gcloud monitoring dashboards create \
  --config-from-file=monitoring/gemini_enterprise_telemetry_dashboard.json \
  --project=<PROJECT_ID>
```

### Step 5.6: Deploy Telemetry & Observability AI Agent
```bash
export GOOGLE_CLOUD_PROJECT="<PROJECT_ID>"
export GOOGLE_CLOUD_LOCATION="<LOCATION>"
export GEMINI_ENGINE_ID="<ENGINE_ID>"

python3 agent/deploy_agent.py
```

---

## 6. Administrator Guide: Telemetry & Observability Operations

### A. Conversational Telemetry Agent with Metrics Statement

When an administrator begins chatting with the agent in Gemini Enterprise, the agent starts by delivering an **Opening Statement of Metrics Offered**:

> **"Cześć! Jestem Twoim Agentem ds. Telemetrii i Obserwowalności Gemini Enterprise.**
> Monitoruję wdrożenie, adopcję, wydajność platformy oraz limity kwotowe w całej Twojej organizacji.
> 
> **Oto 4 główne filary metryk, które dla Ciebie udostępniam:**
> 1. 📊 **Utylizacja Użytkowników w Ujęciu Dziennym**: Dokładna aktywność per-user rozbita na konkretne dni.
> 2. 🚀 **Metryki Adopcji i Zaangażowania**: DAU/WAU/MAU, głębokość konwersacji (Conversational Depth), wskaźnik adopcji narzędzi (Tool Adoption Rate).
> 3. ⏱️ **Obserwowalność, Trasy OpenTelemetry i Wydajność**: Ślady Cloud Trace, czasy odpowiedzi TTFT (Time to First Token) i opóźnienia narzędzi.
> 4. 🛡️ **Limity Kwot i Quotas**: Zapytania asystenta, tworzenie agentów, Deep Research, generowanie mediów, kredyty WTU."

---

### B. Admin CLI Usage

#### 1. Inspect Observability & OpenTelemetry Metrics:
```bash
python3 cli/telemetry_cli.py observability --traces
```
*Output:*
```text
=== Gemini Enterprise Observability & OpenTelemetry Metrics ===
• Engine ID:                   rossmann-agent-designer_1784194686764
• Location:                    eu
• Observability Enabled:       True
• Sensitive Logging Enabled:   True
• App Type:                    APP_TYPE_INTRANET
--------------------------------------------------------------------
• Total Agent Sessions:        4600
• Total Conversational Turns:  8360
• Conversational Depth:        1.82 turns/session
• Sessions with Tools:         0
• Tool Adoption Rate:          0.0%
• Total Engine Requests:       9067
• Avg Time to 1st Token (TTFT):47747.19 ms
• Avg Request Total Latency:   208540.94 ms

=== Recent OpenTelemetry Distributed Traces (2 entries) ===
Timestamp (UTC)      | Trace ID                           | Method         | User                       | State   
--------------------------------------------------------------------------------------------------------------
2026-09-18 11:43:09  | 5379e14ddba2e5c1860cefde7554f4c3   | StreamAssist   | admin@dprzek.altostrat.com | SUCCESS 
2026-09-18 11:31:08  | bd5b4d06073dd350c3cbe37912532b4c   | StreamAssist   | admin@dprzek.altostrat.com | SUCCEEDED
```

#### 2. Query Day-by-Day User Utilization:
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@dprzek.altostrat.com
```

#### 3. View Organization Adoption Trends (DAU):
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

#### 4. Check Real-Time Quotas & Overages:
```bash
python3 cli/telemetry_cli.py quotas
```

---

### C. BigQuery Analytical SQL Queries

#### 1. Query Recent OpenTelemetry Distributed Traces:
```sql
SELECT
  timestamp,
  trace_id,
  span_id,
  user_id,
  method_name,
  answer_state,
  agent_display_name
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_observability_traces`
ORDER BY timestamp DESC
LIMIT 20;
```

#### 2. Query Day-by-Day User Activity Breakdown:
```sql
SELECT
  activity_date,
  user_id,
  total_events,
  assistant_queries,
  deep_research_count,
  agents_created,
  total_tokens
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_user_daily_utilization`
WHERE activity_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
ORDER BY activity_date DESC, total_events DESC;
```

---

## 7. Official Gemini Enterprise Quota Reference

| Feature | Standard Edition | Plus Edition | Reset Schedule | Enforcement Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Assistant Queries** | 160 / user / day | 200 / user / day | Midnight PT | Organization Pool |
| **Agent Building** | 1 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Deep Research** | 3 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Image Generation** | 5 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Video Generation** | 2 / user / day | 3 / user / day | Midnight PT | Organization Pool |
| **AI Developer Tools (WTU)**| $10 / user / cycle | $15 / user / cycle | Rolling 7-day window | Organization Pool |
| **Storage & Indexing** | 30 GiB / user | 75 GiB / user | Continuous regional pool | Project / Region |
