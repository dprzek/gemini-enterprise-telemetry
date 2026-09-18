# Gemini Enterprise Telemetry & Adoption Monitoring

A production-ready solution to monitor, analyze, and report telemetry on Google Cloud **Gemini Enterprise** usage across an organization.

Equipped with automated BigQuery log ingestion, analytical SQL views, Cloud Monitoring real-time quota tracking, an Admin CLI, and a conversational AI agent deployed directly in **Gemini Enterprise Agent Designer**.

---

## Key Features

- **Per-User Utilization Tracking (Day-by-Day)**: Measure user activity, assistant queries, deep research invocations, agent creations, and token consumption with full daily breakdowns (`--daily`) or over customizable time spans.
- **Organization-Wide Adoption Analytics**: Monitor Daily Active Users (DAU), Weekly Active Users (WAU), total prompt volume, and tool adoption trends.
- **Quota & Overage Monitoring**: Real-time pooled quota limits and burn rate tracking (Assistant queries, Agent Builder, Deep Research, Image & Video generation, WTU AI Developer Tools credits, Storage).
- **Conversational Telemetry Agent**: An AI agent deployed directly in Gemini Enterprise (`rossmann-agent-designer` / Agent Builder) that answers admin questions about telemetry and day-by-day user adoption in natural language.
- **Cloud Monitoring Dashboard**: Visual charts for quota limits vs. usage, latencies, and storage metrics.
- **Customer Deployment Manual**: Complete end-to-end customer deployment runbook documented in [MANUAL.md](MANUAL.md).
- **One-Command Automated Deployment**: Shell script (`deploy_pipeline.sh`) and Terraform module for instant deployment on any customer project.
- **Antigravity Skill**: Reusable skill packaged under `skills/gemini-enterprise-telemetry/`.

---

## Architecture

```
                                      Gemini Enterprise
                                (rossmann-agent-designer in eu)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Cloud Logging & Audit Trails                    Cloud Monitoring (Real-time)
         - gemini_enterprise_user_activity               - discoveryengine.googleapis.com/quota/*
         - gen_ai.client.inference.operation.details     - text_answer_gen_tier_* (requests)
         - cloudaudit.googleapis.com/activity            - agents_tier_* (agents created)
         - cloudaudit.googleapis.com/data_access         - deep_research_query_total_tier_*
                      │                                  - image_gen_tier_*, video_gen_*
                      ▼ (Log Sink)                       - total_document_size_regional
           BigQuery Telemetry Dataset                                 │
           (gemini_enterprise_telemetry in EU)                        │
           - Partitioned & Clustered Tables                           │
           - Analytical Views:                                        │
             * v_daily_adoption (DAU/WAU/MAU)                         │
             * v_user_utilization (per user, per time span)           │
             * v_feature_usage (breakdown of capabilities)            │
             * v_token_telemetry (input, output, cache tokens)        │
             * v_agent_creation_audit (agent creations by user)       │
                      │                                               │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                        Adoption & Telemetry Service / CLI
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Gemini Enterprise Agent                           Antigravity Skill & CLI
         (Deployed in rossmann-agent-designer)             - Automated runbooks
         - Conversational telemetry answers                - Admin CLI (utilization per user)
         - Grounded in BigQuery telemetry digests          - Customer onboarding package
```

---

## Telemetry Dimensions Tracked

| Metric Category | Dimension | Source | Reset / Enforcement |
| :--- | :--- | :--- | :--- |
| **Assistant Queries** | User prompts & assistant completions | BigQuery + Cloud Monitoring | Daily at midnight PT (Pooled by edition) |
| **Agent Building** | No-code agents created / modified | Cloud Audit Logs (`CreateAgent`) + Quota | Daily at midnight PT (Pooled by edition) |
| **Deep Research** | Deep Research runs triggered | BigQuery + Cloud Monitoring | Daily at midnight PT (Pooled by edition) |
| **Image Generation** | Images generated | BigQuery + Cloud Monitoring | Daily at midnight PT (Pooled by edition) |
| **Video Generation** | Videos generated | BigQuery + Cloud Monitoring | Daily at midnight PT (Pooled by edition) |
| **AI Developer Tools**| Antigravity / IDE WTU credit burn | Cloud Monitoring (`ai_dev_tool_wtu_*`) | Rolling 7-day pooled cycle |
| **Storage & Indexing**| GiB indexed across data stores | Cloud Monitoring (`total_document_size`) | Project-wide pool |
| **Per-User Utilization**| Queries, tokens, active days, timestamps | BigQuery (`v_user_utilization`) | Custom date filter |
| **Adoption Metrics** | DAU, WAU, interactions | BigQuery (`v_daily_adoption`) | Daily / Weekly / Monthly |
| **Token Consumption**| Input, output, cached tokens | BigQuery (`v_token_telemetry`) | Real-time & aggregated |

---

## Quick Start: One-Command Deployment

To deploy the entire pipeline on any Google Cloud project:

```bash
# Clone the repository
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# Execute end-to-end deployment
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

### Example:
```bash
./scripts/deploy_pipeline.sh adk-dev-485808 eu rossmann-agent-designer_1784194686764 gemini_enterprise_telemetry
```

---

## Admin CLI Usage

The repository includes a Python CLI in `cli/` for administrators to query utilization:

### 1. Utilization Per User Over a Precise Time Span
```bash
python3 cli/telemetry_cli.py utilization --user admin@dprzek.altostrat.com --from-date 2026-09-01 --to-date 2026-09-18
```
Output:
```
=== User Utilization Report (1 users) ===
User ID                        | Active Days | Queries  | Deep Rsrch | Agents  | Tokens    
----------------------------------------------------------------------------------------
admin@dprzek.altostrat.com     | 7           | 70       | 0          | 50      | 0         
```

### 2. Top Active Users Overview
```bash
python3 cli/telemetry_cli.py utilization
```

### 3. Daily Adoption Trends (DAU, Events, Queries)
```bash
python3 cli/telemetry_cli.py adoption --days 14
```
Output:
```
=== Daily Adoption Trends (Past 14 Days) ===
Date         | DAU   | Events  | Queries  | Deep Rsrch | Agents  | Tokens    
---------------------------------------------------------------------------
2026-09-14   | 2     | 4       | 2        | 2          | 0       | 0         
2026-09-11   | 2     | 6       | 2        | 0          | 1       | 0         
2026-09-09   | 1     | 0       | 0        | 0          | 0       | 0         
```

### 4. Quota Limits & Reset Policies
```bash
python3 cli/telemetry_cli.py quotas
```

### 5. Generate Markdown Adoption Report
```bash
python3 cli/telemetry_cli.py report --output adoption_report.md
```

---

## BigQuery SQL Analytical Views

The dataset `gemini_enterprise_telemetry` exposes 5 analytical views:

- `v_user_utilization`: Per-user queries, active days, deep research, agents created, tokens.
- `v_daily_adoption`: Daily active users, total interactions, total tokens burned.
- `v_feature_usage`: Breakdown of calls across features.
- `v_agent_creation_audit`: Users creating and updating agents.
- `v_token_telemetry`: Detailed token metrics and finish reasons per inference call.

Example BigQuery query:
```sql
SELECT 
  user_id, 
  SUM(assistant_queries) AS total_queries, 
  SUM(agents_created) AS agents_created,
  SUM(total_input_tokens + total_output_tokens) AS tokens_consumed
FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_utilization`
WHERE activity_date BETWEEN '2026-09-01' AND '2026-09-18'
GROUP BY user_id
ORDER BY total_queries DESC;
```

---

## Gemini Enterprise Agent Deployment

The agent is deployed directly to the Gemini Enterprise engine via Discovery Engine API:

- **Agent Name**: `Gemini Enterprise Telemetry & Adoption Monitor`
- **Location**: `eu`
- **Engine ID**: `rossmann-agent-designer_1784194686764`
- **Capabilities**: Conversationally answers queries on quotas, active users, per-user utilization, and adoption trends.

To redeploy or update:
```bash
GOOGLE_CLOUD_PROJECT=adk-dev-485808 \
GOOGLE_CLOUD_LOCATION=eu \
GEMINI_ENGINE_ID=rossmann-agent-designer_1784194686764 \
python3 agent/deploy_agent.py
```

---

## Directory Structure

```text
gemini-enterprise-telemetry/
├── README.md                   # Project overview & documentation
├── LICENSE                     # Apache 2.0 license
├── .gitignore                  # Git ignore rules
├── scripts/
│   ├── deploy_pipeline.sh      # Master end-to-end deployment script
│   ├── setup_bigquery_sink.sh  # BigQuery dataset & Cloud Logging sink setup
│   ├── backfill_logs_to_bigquery.py # Backfill historical logs to BigQuery
│   └── push_to_github.sh       # Helper to push to dprzek@ repository
├── bigquery/
│   └── telemetry_views.sql     # 5 analytical views for adoption & utilization
├── monitoring/
│   └── gemini_enterprise_telemetry_dashboard.json # Cloud Monitoring dashboard
├── cli/
│   ├── telemetry_service.py    # Python service querying BigQuery & Monitoring
│   └── telemetry_cli.py        # CLI for admin querying
├── agent/
│   ├── telemetry_agent_definition.json # Agent JSON specification
│   └── deploy_agent.py         # Agent deployment script
├── terraform/                  # Terraform IaC module
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── skills/
    └── gemini-enterprise-telemetry/
        └── SKILL.md            # Antigravity skill for reproducing setup
```

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
