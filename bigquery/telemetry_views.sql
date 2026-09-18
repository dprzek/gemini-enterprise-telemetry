-- ==============================================================================
-- Gemini Enterprise Telemetry Analytical Views
-- ==============================================================================

-- 1. Per-User Utilization View
-- Answers: "give an answer of utilization per users in precised time span"
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_user_utilization` AS
WITH user_activity AS (
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(
      NULLIF(user_iam_principal, '<elided>'),
      NULLIF(user_iam_principal, ''),
      user_pseudo_id,
      'anonymous_user'
    ) AS user_identifier,
    method_name,
    page_type,
    event_type,
    engine,
    CASE 
      WHEN page_type = 'deep-research' OR raw_payload LIKE '%deep-research%' THEN 1 
      ELSE 0 
    END AS is_deep_research,
    CASE 
      WHEN method_name = 'StreamAssist' OR method_name = 'Assist' THEN 1 
      ELSE 0 
    END AS is_assistant_query
  FROM `adk-dev-485808.gemini_enterprise_telemetry.gemini_enterprise_user_activity`
),
agent_audit AS (
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    principal_email AS user_identifier,
    method_name,
    resource_name,
    CASE 
      WHEN method_name LIKE '%CreateAgent%' THEN 1 
      ELSE 0 
    END AS is_agent_created
  FROM `adk-dev-485808.gemini_enterprise_telemetry.cloudaudit_googleapis_com_activity`
),
tokens AS (
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(NULLIF(user_id, 'user'), 'admin') AS user_identifier,
    input_tokens,
    output_tokens,
    cached_tokens,
    finish_reason
  FROM `adk-dev-485808.gemini_enterprise_telemetry.gen_ai_client_inference_operation_details`
)
SELECT
  COALESCE(u.activity_date, a.activity_date, t.activity_date) AS activity_date,
  COALESCE(u.user_identifier, a.user_identifier, t.user_identifier) AS user_id,
  COUNT(DISTINCT u.timestamp) AS total_events,
  SUM(COALESCE(u.is_assistant_query, 0)) AS assistant_queries,
  SUM(COALESCE(u.is_deep_research, 0)) AS deep_research_count,
  SUM(COALESCE(a.is_agent_created, 0)) AS agents_created,
  SUM(COALESCE(t.input_tokens, 0)) AS total_input_tokens,
  SUM(COALESCE(t.output_tokens, 0)) AS total_output_tokens,
  SUM(COALESCE(t.cached_tokens, 0)) AS total_cached_tokens,
  MIN(COALESCE(u.timestamp, a.timestamp, t.timestamp)) AS first_seen,
  MAX(COALESCE(u.timestamp, a.timestamp, t.timestamp)) AS last_seen
FROM user_activity u
FULL OUTER JOIN agent_audit a 
  ON u.user_identifier = a.user_identifier AND u.activity_date = a.activity_date
FULL OUTER JOIN tokens t
  ON COALESCE(u.user_identifier, a.user_identifier) = t.user_identifier 
  AND COALESCE(u.activity_date, a.activity_date) = t.activity_date
GROUP BY 1, 2;

-- 2. Daily Adoption & Organization Metrics (DAU, WAU, Total Activity)
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_daily_adoption` AS
SELECT
  activity_date,
  COUNT(DISTINCT user_id) AS daily_active_users,
  SUM(total_events) AS total_interactions,
  SUM(assistant_queries) AS total_assistant_queries,
  SUM(deep_research_count) AS total_deep_research_queries,
  SUM(agents_created) AS total_agents_created,
  SUM(total_input_tokens + total_output_tokens) AS total_tokens_burned
FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_utilization`
GROUP BY activity_date
ORDER BY activity_date DESC;

-- 3. Feature Breakdown
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_feature_usage` AS
SELECT
  COALESCE(NULLIF(page_type, ''), method_name, 'General Assistant') AS feature_name,
  COUNT(*) AS total_calls,
  COUNT(DISTINCT user_pseudo_id) AS distinct_users,
  MIN(timestamp) AS earliest_invocation,
  MAX(timestamp) AS latest_invocation
FROM `adk-dev-485808.gemini_enterprise_telemetry.gemini_enterprise_user_activity`
GROUP BY 1
ORDER BY total_calls DESC;

-- 4. Agent Creation Audit Trail
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_agent_creation_audit` AS
SELECT
  timestamp,
  principal_email,
  method_name,
  resource_name,
  REGEXP_EXTRACT(resource_name, r'/agents/([^/]+)') AS extracted_agent_id
FROM `adk-dev-485808.gemini_enterprise_telemetry.cloudaudit_googleapis_com_activity`
WHERE method_name LIKE '%Agent%'
ORDER BY timestamp DESC;

-- 5. Token Burn & Model Telemetry
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_token_telemetry` AS
SELECT
  timestamp,
  user_id,
  agent_name,
  engine_id,
  input_tokens,
  output_tokens,
  cached_tokens,
  (input_tokens + output_tokens) AS total_tokens,
  finish_reason
FROM `adk-dev-485808.gemini_enterprise_telemetry.gen_ai_client_inference_operation_details`
ORDER BY timestamp DESC;
