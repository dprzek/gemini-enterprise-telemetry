-- ==============================================================================
-- Widoki Analityczne Telemetrii i Obserwowalności Gemini Enterprise
-- Automatycznie unifikuje tabele zlewu Cloud Logging w czasie rzeczywistym i logi historyczne.
-- Obejmuje ślady i spany OpenTelemetry, zdarzenia użytkowników, opóźnienia i tokeny.
-- ==============================================================================

-- 1. Zunifikowany widok dziennej aktywności użytkowników (rozbicie dzień po dniu)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_user_daily_utilization` AS
WITH primary_user AS (
  SELECT protopayload_auditlog.authenticationInfo.principalEmail AS email
  FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
  WHERE protopayload_auditlog.authenticationInfo.principalEmail IS NOT NULL 
    AND NOT protopayload_auditlog.authenticationInfo.principalEmail LIKE '%gserviceaccount.com'
  ORDER BY timestamp DESC
  LIMIT 1
),
raw_user_events AS (
  SELECT * FROM (
    -- Strumień aktywności użytkowników ze zlewu Cloud Logging (czas rzeczywisty)
    SELECT
      DATE(timestamp) AS activity_date,
      timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(jsonPayload.useriamprincipal), '<elided>'), ''),
        (SELECT email FROM primary_user),
        jsonPayload.request.userevent.userpseudoid,
        'admin@dprzek.altostrat.com'
      ) AS user_id,
      COALESCE(jsonPayload.logmetadata.methodname, '') AS method_name,
      COALESCE(jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype, '') AS page_type,
      COALESCE(jsonPayload.request.userevent.eventtype, '') AS event_type,
      COALESCE(jsonPayload.request.userevent.engine, '') AS engine,
      CASE 
        WHEN COALESCE(jsonPayload.request.userevent.agentspaceinfo.agentspacepagetype, '') = 'deep-research'
          OR jsonPayload.response.agentinfo.agent LIKE '%/agents/deep_research'
          OR EXISTS (
            SELECT 1 
            FROM UNNEST(COALESCE(jsonPayload.request.agentsspec.agentspecs, [])) s 
            WHERE s.agentid = 'deep_research'
          ) THEN 1 
        ELSE 0 
      END AS is_deep_research,
      CASE 
        WHEN jsonPayload.logmetadata.methodname IN ('StreamAssist', 'Assist') THEN 1 
        ELSE 0 
      END AS is_assistant_query,
      insertId
    FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`

    UNION ALL

    -- Backfilled historical user activity
    SELECT
      DATE(timestamp) AS activity_date,
      timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(user_iam_principal), '<elided>'), ''),
        (SELECT email FROM primary_user),
        NULLIF(user_pseudo_id, ''),
        'admin@dprzek.altostrat.com'
      ) AS user_id,
      method_name,
      page_type,
      event_type,
      engine,
      CASE 
        WHEN page_type = 'deep-research' 
          OR agent_id = 'deep_research' THEN 1 
        ELSE 0 
      END AS is_deep_research,
      CASE 
        WHEN method_name IN ('StreamAssist', 'Assist') THEN 1 
        ELSE 0 
      END AS is_assistant_query,
      insert_id AS insertId
    FROM `{project_id}.{dataset_id}.gemini_enterprise_user_activity`
  )
  QUALIFY ROW_NUMBER() OVER(
    PARTITION BY COALESCE(NULLIF(insertId, ''), CONCAT(CAST(timestamp AS STRING), '_', method_name))
    ORDER BY timestamp
  ) = 1
),
aggregated_user_events AS (
  SELECT
    activity_date,
    user_id,
    COUNT(*) AS total_events,
    SUM(is_assistant_query) AS assistant_queries,
    SUM(is_deep_research) AS deep_research_count,
    COUNTIF(method_name = 'CreateAgent') AS agents_created,
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
  FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
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
  SELECT * FROM (
    -- Strumień tokenów ze zlewu Cloud Logging w czasie rzeczywistym
    SELECT
      DATE(inf.timestamp) AS activity_date,
      inf.timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(act.jsonPayload.useriamprincipal), '<elided>'), ''),
        (SELECT email FROM primary_user),
        'admin@dprzek.altostrat.com'
      ) AS user_id,
      CAST(COALESCE(inf.jsonPayload.gen_ai_usage_input_tokens, 0) AS INT64) AS input_tokens,
      CAST(COALESCE(inf.jsonPayload.gen_ai_usage_output_tokens, 0) AS INT64) AS output_tokens,
      CAST(COALESCE(inf.jsonPayload.gen_ai_usage_reasoning_output_tokens, 0) AS INT64) AS cached_tokens,
      inf.insertId,
      1 AS priority
    FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gen_ai_client_inference_operation_details` inf
    LEFT JOIN `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity` act
      ON inf.trace = act.trace AND act.trace IS NOT NULL

    UNION ALL

    -- Historyczne tokeny z tabeli backfill
    SELECT
      DATE(timestamp) AS activity_date,
      timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(user_id), 'user'), ''),
        (SELECT email FROM primary_user),
        'admin@dprzek.altostrat.com'
      ) AS user_id,
      CAST(input_tokens AS INT64) AS input_tokens,
      CAST(output_tokens AS INT64) AS output_tokens,
      CAST(cached_tokens AS INT64) AS cached_tokens,
      insert_id AS insertId,
      0 AS priority
    FROM `{project_id}.{dataset_id}.gen_ai_client_inference_operation_details`
  )
  QUALIFY ROW_NUMBER() OVER(
    PARTITION BY COALESCE(NULLIF(insertId, ''), CAST(timestamp AS STRING))
    ORDER BY priority DESC, timestamp
  ) = 1
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
  COALESCE(u.total_events, a.audit_events, 0) AS total_events,
  COALESCE(u.assistant_queries, 0) AS assistant_queries,
  COALESCE(u.deep_research_count, 0) AS deep_research_count,
  GREATEST(COALESCE(u.agents_created, 0), COALESCE(a.agents_created, 0)) AS agents_created,
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

-- 2. Widok wstecznej kompatybilności (alias dla v_user_daily_utilization)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_user_utilization` AS
SELECT * FROM `{project_id}.{dataset_id}.v_user_daily_utilization`;

-- 3. Zbiorcze podsumowanie per użytkownik (statystyki łączone od początku rejestracji)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_user_summary` AS
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
FROM `{project_id}.{dataset_id}.v_user_daily_utilization`
GROUP BY user_id
ORDER BY total_events DESC, assistant_queries DESC;

-- 4. Widok dziennych trendów adopcji organizacji (DAU, interakcje, zapytania)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_daily_adoption` AS
SELECT
  activity_date,
  COUNT(DISTINCT user_id) AS daily_active_users,
  SUM(total_events) AS total_interactions,
  SUM(assistant_queries) AS total_assistant_queries,
  SUM(deep_research_count) AS total_deep_research_queries,
  SUM(agents_created) AS total_agents_created,
  SUM(total_tokens) AS total_tokens_burned
FROM `{project_id}.{dataset_id}.v_user_daily_utilization`
GROUP BY activity_date
ORDER BY activity_date DESC;

-- 5. Widok podziału wykorzystania poszczególnych modułów i funkcji
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_feature_usage` AS
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
  FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
  
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
  FROM `{project_id}.{dataset_id}.gemini_enterprise_user_activity`
)
GROUP BY feature_name
ORDER BY total_calls DESC;

-- 6. Widok rozproszonych śladów i spanów OpenTelemetry (Cloud Trace)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_observability_traces` AS
SELECT
  timestamp,
  DATE(timestamp) AS trace_date,
  trace AS trace_id,
  spanId AS span_id,
  COALESCE(
    NULLIF(jsonPayload.useriamprincipal, '<elided>'),
    NULLIF(jsonPayload.useriamprincipal, ''),
    jsonPayload.request.userevent.userpseudoid,
    'anonymous_user'
  ) AS user_id,
  jsonPayload.logmetadata.methodname AS method_name,
  jsonPayload.logmetadata.servicename AS service_name,
  jsonPayload.response.answer.state AS answer_state,
  jsonPayload.response.agentinfo.displayname AS agent_display_name,
  jsonPayload.response.agentinfo.agent AS agent_resource,
  severity,
  insertId
FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
WHERE trace IS NOT NULL
ORDER BY timestamp DESC;
