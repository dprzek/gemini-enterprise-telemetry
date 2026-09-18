# Gemini Enterprise Telemetry & Adoption Monitoring — Customer Deployment Manual

This manual provides instructions for deploying, configuring, and maintaining the **Gemini Enterprise Telemetry, Adoption & Quota Monitoring Suite** in any customer Google Cloud environment.

---

## Architecture Overview

```
                                      Gemini Enterprise
                             (Enterprise Engine / Agent Builder)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         Cloud Logging & Audit Trails                    Cloud Monitoring (Real-Time)
         - discoveryengine_googleapis_com_*              - discoveryengine.googleapis.com/quota/*
         - cloudaudit_googleapis_com_activity            - text_answer_gen_tier_* (requests)
         - gen_ai.client.inference.operation.details     - agents_tier_* (agents created)
                      │                                  - deep_research_query_total_tier_*
                      ▼ (Log Sink)                       - image_gen_tier_*, video_gen_*
           BigQuery Telemetry Dataset                                 │
           (gemini_enterprise_telemetry)                              │
           - Partitioned & Clustered Tables                           │
           - Analytical Views:                                        │
             * v_user_daily_utilization (day-by-day user breakdown)   │
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
         (Deployed in Agent Designer)                      - Day-by-day user queries
         - Conversational telemetry answers                - Real-time quota alerts
         - Full day-by-day per-user metrics                - Visual Cloud Monitoring dashboard
```

---

## 1. Prerequisites & Required IAM Roles

Before deploying, ensure that the person or service account running the deployment has the following IAM roles on the target Google Cloud project:

| Role | Purpose |
| :--- | :--- |
| `roles/discoveryengine.agentspaceAdmin` | Manage and deploy agents in Discovery Engine / Gemini Enterprise |
| `roles/logging.configWriter` | Create Cloud Logging sinks routing logs to BigQuery |
| `roles/bigquery.admin` | Create datasets, partitioned tables, and analytical views |
| `roles/monitoring.editor` | Deploy Cloud Monitoring dashboards and inspect quotas |
| `roles/resourcemanager.projectIamAdmin` | Grant BigQuery Data Editor to the Cloud Logging sink service account |

### Target Environment Information Needed:
- **`PROJECT_ID`**: The customer's Google Cloud project ID (e.g. `customer-prod-123456`).
- **`LOCATION`**: The region of the Gemini Enterprise engine (`eu` or `us` or `global`).
- **`ENGINE_ID`**: The Discovery Engine / Gemini Enterprise engine ID (e.g. `my-enterprise-engine_123456789`).

---

## 2. Fast-Track Deployment (One Single Command)

To deploy the entire solution automatically in a single step:

```bash
# 1. Clone repository
git clone https://github.com/dprzek/gemini-enterprise-telemetry.git
cd gemini-enterprise-telemetry

# 2. Run automated pipeline deployment
./scripts/deploy_pipeline.sh <PROJECT_ID> <LOCATION> <ENGINE_ID> [DATASET_ID]
```

### Example:
```bash
./scripts/deploy_pipeline.sh my-company-gcp eu my-gemini-engine_1784194686764 gemini_enterprise_telemetry
```

### What this script automates:
1. Provisions the BigQuery dataset (`gemini_enterprise_telemetry`) with 90-day retention and partitioning.
2. Creates the Cloud Logging sink (`gemini-enterprise-telemetry-sink`) filtering Discovery Engine and Audit activity.
3. Automatically grants `roles/bigquery.dataEditor` to the sink's unique service account.
4. Backfills historical logs from the past 30 days into BigQuery.
5. Deploys the 5 SQL analytical views (including Day-by-Day user utilization).
6. Provisions the Cloud Monitoring dashboard.
7. Deploys the Telemetry & Adoption AI Agent directly into the customer's Gemini Enterprise Agent Designer.

---

## 3. Step-by-Step Manual Deployment (Enterprise Governance Track)

If the customer prefers to deploy step-by-step through change management:

### Step 3.1: Provision BigQuery Dataset and Logging Sink
```bash
./scripts/setup_bigquery_sink.sh <PROJECT_ID> <REGION> <DATASET_ID> <SINK_NAME>
```
*Example*:
```bash
./scripts/setup_bigquery_sink.sh my-company-gcp EU gemini_enterprise_telemetry gemini-enterprise-telemetry-sink
```

### Step 3.2: Backfill Historical Logs (Past 30 Days)
If the customer has already been using Gemini Enterprise before deploying this pipeline, backfill historical logs:
```bash
python3 scripts/backfill_logs_to_bigquery.py <PROJECT_ID> <DATASET_ID> 30
```

### Step 3.3: Deploy Analytical BigQuery Views
The views automatically unify real-time logs streamed from the Cloud Logging sink and historical backfilled logs:
```bash
sed "s/adk-dev-485808/<PROJECT_ID>/g; s/gemini_enterprise_telemetry/<DATASET_ID>/g" \
  bigquery/telemetry_views.sql | bq query --project_id=<PROJECT_ID> --use_legacy_sql=false
```

### Step 3.4: Deploy Cloud Monitoring Dashboard
```bash
gcloud monitoring dashboards create \
  --config-from-file=monitoring/gemini_enterprise_telemetry_dashboard.json \
  --project=<PROJECT_ID>
```

### Step 3.5: Deploy Gemini Enterprise Agent
```bash
export GOOGLE_CLOUD_PROJECT="<PROJECT_ID>"
export GOOGLE_CLOUD_LOCATION="<LOCATION>"
export GEMINI_ENGINE_ID="<ENGINE_ID>"

python3 agent/deploy_agent.py
```

---

## 4. Terraform / Infrastructure as Code (IaC) Track

For organizations managing Google Cloud infrastructure with Terraform:

```bash
cd terraform
terraform init
terraform plan -var="project_id=<PROJECT_ID>" -var="region=EU"
terraform apply -var="project_id=<PROJECT_ID>" -var="region=EU"
```

Then deploy the analytical views and agent using Steps 3.3 and 3.5.

---

## 5. Administrator Guide: Telemetry Querying & Operations

### A. Querying Day-by-Day User Utilization via CLI

The administrator CLI provides instant day-by-day and summary utilization reports:

#### 1. Day-by-Day Breakdown for a Specific User:
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@mycompany.com
```
*Output:*
```
=== Day-by-Day User Utilization Report (8 daily entries) ===
Date         | User ID                      | Events  | Queries  | Deep Rsrch | Agents  | Tokens    
----------------------------------------------------------------------------------------------
2026-09-18   | admin@mycompany.com          | 7       | 1        | 0          | 1       | 0         
2026-09-14   | admin@mycompany.com          | 1       | 0        | 0          | 0       | 0         
2026-09-11   | admin@mycompany.com          | 4       | 0        | 0          | 1       | 0         
2026-08-27   | admin@mycompany.com          | 3       | 2        | 0          | 0       | 12,434    
2026-08-26   | admin@mycompany.com          | 18      | 5        | 0          | 0       | 0         
2026-08-25   | admin@mycompany.com          | 31      | 9        | 0          | 2       | 0         
```

#### 2. User Utilization Over a Precise Time Span:
```bash
python3 cli/telemetry_cli.py utilization --daily --user admin@mycompany.com --from-date 2026-08-25 --to-date 2026-09-18
```

#### 3. Organization Daily Adoption Trends:
```bash
python3 cli/telemetry_cli.py adoption --days 30
```

#### 4. Real-Time Quota Headroom:
```bash
python3 cli/telemetry_cli.py quotas
```

#### 5. Generate Executive Markdown Report:
```bash
python3 cli/telemetry_cli.py report --output /path/to/adoption_report.md
```

---

### B. Querying Directly in BigQuery

Administrators can run custom SQL queries in BigQuery console or via BI tools (Looker Studio, PowerBI, Tableau):

#### Day-by-Day Utilization per User:
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
WHERE activity_date BETWEEN '2026-09-01' AND '2026-09-18'
ORDER BY activity_date DESC, total_events DESC;
```

#### Power Users Ranking:
```sql
SELECT 
  user_id,
  active_days,
  total_events,
  assistant_queries,
  deep_research_count,
  agents_created,
  total_tokens,
  first_active,
  last_active
FROM `<PROJECT_ID>.gemini_enterprise_telemetry.v_user_summary`
ORDER BY total_events DESC;
```

---

### C. Conversational Queries with the Gemini Enterprise Agent

The AI Agent is available directly inside the Gemini Enterprise console:
`https://console.cloud.google.com/gemini-enterprise/locations/<LOCATION>/engines/<ENGINE_ID>/overview?project=<PROJECT_ID>`

Admins can ask conversational questions in English or Polish:
- *"Powiedz mi jak wygląda adopcja użytkownika admin@mycompany.com po konkretnych dniach"*
  - The agent responds with a complete day-by-day table of events, queries, deep research, agents, and tokens!
- *"Którzy użytkownicy utworzyli najwięcej agentów w tym miesiącu?"*
- *"Czy zbliżamy się do limitu zapytań asystenta lub Deep Research?"*
- *"Jaki jest trend DAU (Daily Active Users) w naszej organizacji?"*

---

## 6. Official Quota Limits & Reset Reference

As documented in [Google Cloud Gemini Enterprise Quotas](https://docs.cloud.google.com/gemini/enterprise/docs/quotas-and-overages):

| Feature | Standard Edition | Plus Edition | Reset Schedule | Enforcement Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Assistant Queries** | 160 / user / day | 200 / user / day | Midnight PT | Organization Pool |
| **Agent Building** | 1 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Deep Research** | 3 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Image Generation** | 5 / user / day | 10 / user / day | Midnight PT | Organization Pool |
| **Video Generation** | 2 / user / day | 3 / user / day | Midnight PT | Organization Pool |
| **AI Developer Tools (WTU)**| $10 / user / cycle | $15 / user / cycle | Rolling 7-day window | Organization Pool |
| **Storage & Indexing** | 30 GiB / user | 75 GiB / user | Continuous regional pool | Project / Region |

---

## 7. Continuous Ingestion & Agent Refresh

- **Continuous Ingestion**: Every new user action, assistant query, Deep Research execution, or agent modification in Gemini Enterprise is streamed immediately by Cloud Logging to BigQuery.
- **Agent Knowledge Refresh**: To update the agent's baseline knowledge snapshot with newly ingested days, simply run:
  ```bash
  python3 agent/deploy_agent.py
  ```
  *(This can be scheduled as a daily Cloud Run job or Cloud Function).*
