-- ==============================================================================
-- Gemini Enterprise Telemetry Analytical Views
-- Automatically unifies real-time Cloud Logging Sink tables and backfilled logs.
-- ==============================================================================

-- 1. Unified Daily User Activity View (Day-by-Day Granularity)
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_user_daily_utilization` AS
WITH raw_user_events AS (
  -- Streamed user activity from Cloud Logging Sink
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(
      NULLIF(jsonPayload.useriamprincipal, '<elided>'),
      NULLIF(jsonPayload.useriamprincipal, ''),
      jsonPayload.request.userevent.userpseudoid,
      'anonymous_user'
    ) AS user_id,
    COALESCE(jsonPayload.logmetadata.methodname, '') AS method_name,
    COALESCE(jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype, '') AS page_type,
    COALESCE(jsonPayload.request.userevent.eventtype, '') AS event_type,
    COALESCE(jsonPayload.request.userevent.engine, '') AS engine,
    CASE 
      WHEN jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype = 'deep-research' 
        OR TO_JSON_STRING(jsonPayload) LIKE '%deep-research%' THEN 1 
      ELSE 0 
    END AS is_deep_research,
    CASE 
      WHEN jsonPayload.logmetadata.methodname IN ('StreamAssist', 'Assist') THEN 1 
      ELSE 0 
    END AS is_assistant_query
  FROM `adk-dev-485808.gemini_enterprise_telemetry.discoveryengine_googleapis_com_gemini_enterprise_user_activity`

  UNION ALL

  -- Backfilled historical user activity
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(
      NULLIF(user_iam_principal, '<elided>'),
      NULLIF(user_iam_principal, ''),
      user_pseudo_id,
      'anonymous_user'
    ) AS user_id,
    method_name,
    page_type,
    event_type,
    engine,
    CASE 
      WHEN page_type = 'deep-research' OR raw_payload LIKE '%deep-research%' THEN 1 
      ELSE 0 
    END AS is_deep_research,
    CASE 
      WHEN method_name IN ('StreamAssist', 'Assist') THEN 1 
      ELSE 0 
    END AS is_assistant_query
  FROM `adk-dev-485808.gemini_enterprise_telemetry.gemini_enterprise_user_activity`
),
aggregated_user_events AS (
  SELECT
    activity_date,
    user_id,
    COUNT(DISTINCT timestamp) AS total_events,
    SUM(is_assistant_query) AS assistant_queries,
    SUM(is_deep_research) AS deep_research_count,
    MIN(timestamp) AS first_event,
    MAX(timestamp) AS last_event
  FROM raw_user_events
  GROUP BY 1, 2
),
raw_audit AS (
  -- Streamed & backfilled audit events
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(
      NULLIF(principal_email, ''),
      NULLIF(protopayload_auditlog.authenticationInfo.principalEmail, ''),
      'unknown'
    ) AS user_id,
    COALESCE(method_name, protopayload_auditlog.methodName, '') AS method_name,
    COALESCE(resource_name, protopayload_auditlog.resourceName, '') AS resource_name,
    CASE 
      WHEN COALESCE(method_name, protopayload_auditlog.methodName, '') LIKE '%CreateAgent%' THEN 1 
      ELSE 0 
    END AS is_agent_created
  FROM `adk-dev-485808.gemini_enterprise_telemetry.cloudaudit_googleapis_com_activity`
),
aggregated_audit AS (
  SELECT
    activity_date,
    user_id,
    COUNT(*) AS audit_events,
    SUM(is_agent_created) AS agents_created,
    MIN(timestamp) AS first_audit,
    MAX(timestamp) AS last_audit
  FROM raw_audit
  GROUP BY 1, 2
),
raw_tokens AS (
  -- Model inference tokens
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(NULLIF(user_id, 'user'), 'admin@dprzek.altostrat.com') AS user_id,
    input_tokens,
    output_tokens,
    cached_tokens
  FROM `adk-dev-485808.gemini_enterprise_telemetry.gen_ai_client_inference_operation_details`
),
aggregated_tokens AS (
  SELECT
    activity_date,
    user_id,
    SUM(COALESCE(input_tokens, 0)) AS input_tokens,
    SUM(COALESCE(output_tokens, 0)) AS output_tokens,
    SUM(COALESCE(cached_tokens, 0)) AS cached_tokens,
    SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS total_tokens,
    MIN(timestamp) AS first_token,
    MAX(timestamp) AS last_token
  FROM raw_tokens
  GROUP BY 1, 2
)
SELECT
  COALESCE(u.activity_date, a.activity_date, t.activity_date) AS activity_date,
  COALESCE(u.user_id, a.user_id, t.user_id) AS user_id,
  COALESCE(u.total_events, 0) + COALESCE(a.audit_events, 0) AS total_events,
  COALESCE(u.assistant_queries, 0) AS assistant_queries,
  COALESCE(u.deep_research_count, 0) AS deep_research_count,
  COALESCE(a.agents_created, 0) AS agents_created,
  COALESCE(t.input_tokens, 0) AS input_tokens,
  COALESCE(t.output_tokens, 0) AS output_tokens,
  COALESCE(t.cached_tokens, 0) AS cached_tokens,
  COALESCE(t.total_tokens, 0) AS total_tokens,
  LEAST(
    COALESCE(u.first_event, a.first_audit, t.first_token),
    COALESCE(a.first_audit, t.first_token, u.first_event),
    COALESCE(t.first_token, u.first_event, a.first_audit)
  ) AS first_seen,
  GREATEST(
    COALESCE(u.last_event, a.last_audit, t.last_token),
    COALESCE(a.last_audit, t.last_token, u.last_event),
    COALESCE(t.last_token, u.last_event, a.last_audit)
  ) AS last_seen
FROM aggregated_user_events u
FULL OUTER JOIN aggregated_audit a 
  ON u.user_id = a.user_id AND u.activity_date = a.activity_date
FULL OUTER JOIN aggregated_tokens t
  ON COALESCE(u.user_id, a.user_id) = t.user_id 
  AND COALESCE(u.activity_date, a.activity_date) = t.activity_date;

-- 2. Backward Compatible View (Alias to v_user_daily_utilization)
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_user_utilization` AS
SELECT * FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_daily_utilization`;

-- 3. Per-User Summary View (All-Time Aggregated per User)
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_user_summary` AS
SELECT
  user_id,
  COUNT(DISTINCT activity_date) AS active_days,
  SUM(total_events) AS total_events,
  SUM(assistant_queries) AS assistant_queries,
  SUM(deep_research_count) AS deep_research_count,
  SUM(agents_created) AS agents_created,
  SUM(input_tokens) AS input_tokens,
  SUM(output_tokens) AS output_tokens,
  SUM(total_tokens) AS total_tokens,
  MIN(first_seen) AS first_active,
  MAX(last_seen) AS last_active
FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_daily_utilization`
GROUP BY user_id
ORDER BY total_events DESC, assistant_queries DESC;

-- 4. Organization Daily Adoption View
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_daily_adoption` AS
SELECT
  activity_date,
  COUNT(DISTINCT user_id) AS daily_active_users,
  SUM(total_events) AS total_interactions,
  SUM(assistant_queries) AS total_assistant_queries,
  SUM(deep_research_count) AS total_deep_research_queries,
  SUM(agents_created) AS total_agents_created,
  SUM(total_tokens) AS total_tokens_burned
FROM `adk-dev-485808.gemini_enterprise_telemetry.v_user_daily_utilization`
GROUP BY activity_date
ORDER BY activity_date DESC;

-- 5. Feature Usage Breakdown View
CREATE OR REPLACE VIEW `adk-dev-485808.gemini_enterprise_telemetry.v_feature_usage` AS
SELECT
  feature_name,
  COUNT(*) AS total_calls,
  COUNT(DISTINCT user_id) AS distinct_users,
  MIN(timestamp) AS earliest_invocation,
  MAX(timestamp) AS latest_invocation
FROM (
  SELECT
    timestamp,
    COALESCE(
      NULLIF(jsonPayload.useriamprincipal, '<elided>'),
      NULLIF(jsonPayload.useriamprincipal, ''),
      jsonPayload.request.userevent.userpseudoid,
      'anonymous_user'
    ) AS user_id,
    COALESCE(
      NULLIF(jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype, ''),
      jsonPayload.logmetadata.methodname,
      'General Assistant'
    ) AS feature_name
  FROM `adk-dev-485808.gemini_enterprise_telemetry.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
  
  UNION ALL
  
  SELECT
    timestamp,
    COALESCE(
      NULLIF(user_iam_principal, '<elided>'),
      NULLIF(user_iam_principal, ''),
      user_pseudo_id,
      'anonymous_user'
    ) AS user_id,
    COALESCE(NULLIF(page_type, ''), method_name, 'General Assistant') AS feature_name
  FROM `adk-dev-485808.gemini_enterprise_telemetry.gemini_enterprise_user_activity`
)
GROUP BY feature_name
ORDER BY total_calls DESC;
