-- 1. Zunifikowany widok dziennej aktywności użytkowników (rozbicie dzień po dniu)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_user_daily_utilization` AS
WITH primary_admin AS (
  SELECT JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail") AS email
  FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
  WHERE JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail") IS NOT NULL 
    AND NOT JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail") LIKE "%gserviceaccount.com"
  ORDER BY timestamp ASC
  LIMIT 1
),
agent_creators AS (
  SELECT
    agent_id,
    author_user_id,
    MIN(created_at) AS created_at
  FROM (
    SELECT
      REGEXP_EXTRACT(COALESCE(
        JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.response.name"),
        JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.responseJson.name"),
        TO_JSON_STRING(protopayload_auditlog)
      ), r"/agents/([0-9a-zA-Z_\-]+)") AS agent_id,
      COALESCE(
        NULLIF(principal_email, ""),
        NULLIF(JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail"), ""),
        "unknown"
      ) AS author_user_id,
      timestamp AS created_at
    FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
    WHERE (
      method_name LIKE "%CreateAgent%"
      OR JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.methodName") LIKE "%CreateAgent%"
    )
    
    UNION ALL
    
    SELECT
      COALESCE(
        NULLIF(agent_id, ""),
        REGEXP_EXTRACT(raw_payload, r"/agents/([0-9a-zA-Z_\-]+)")
      ) AS agent_id,
      COALESCE(NULLIF(NULLIF(TRIM(user_iam_principal), "<elided>"), ""), "unknown") AS author_user_id,
      timestamp AS created_at
    FROM `{project_id}.{dataset_id}.gemini_enterprise_user_activity`
    WHERE method_name = "CreateAgent"
  )
  WHERE agent_id IS NOT NULL 
    AND agent_id != "" 
    AND agent_id != "deep_research"
    AND author_user_id NOT IN ("unknown", "<elided>")
    AND NOT author_user_id LIKE "%@gcp-sa-%.iam.gserviceaccount.com"
  GROUP BY 1, 2
),
raw_user_events AS (
  SELECT * FROM (
    -- Strumień aktywności użytkowników ze zlewu Cloud Logging (czas rzeczywisty)
    SELECT
      DATE(timestamp) AS activity_date,
      timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.useriamprincipal")), "<elided>"), ""),
        NULLIF(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.userpseudoid"), ""),
        (SELECT email FROM primary_admin),
        "system"
      ) AS user_id,
      COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") AS method_name,
      COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"), "") AS page_type,
      COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.eventtype"), "") AS event_type,
      COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.engine"), "") AS engine,
      COALESCE(
        NULLIF(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.agentsspec.agentspecs[0].agentid"), ""),
        REGEXP_EXTRACT(COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), ""), r"/agents/([^/]+)"),
        REGEXP_EXTRACT(COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agent"), ""), r"/agents/([^/]+)"),
        ""
      ) AS called_agent_id,
      REGEXP_EXTRACT(COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.answer.name"), ""), r"/sessions/([^/]+)") AS session_id,
      CASE 
        WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist")
         AND (
           COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), "") LIKE "%/agents/deep_research"
           OR TO_JSON_STRING(jsonPayload) LIKE "%deep_research%"
         )
         AND (SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) IS NULL OR SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) = 0)
         AND JSON_QUERY(TO_JSON_STRING(jsonPayload), "$.response") IS NOT NULL THEN 1 
        ELSE 0 
      END AS is_deep_research,
      CASE
        WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist")
         AND (
           COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"), "") = "image-generation"
           OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
           OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r'"(obrazek|obraz|image|zdjęcie)\s+')
           OR LOWER(TO_JSON_STRING(jsonPayload)) LIKE "%image-generation%"
         )
         AND (SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) IS NULL OR SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) = 0) THEN 1
        ELSE 0
      END AS is_image_generation,
      CASE 
        WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist") 
         AND NOT (
           COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), "") LIKE "%/agents/deep_research"
           OR TO_JSON_STRING(jsonPayload) LIKE "%deep_research%"
         )
         AND NOT (
           COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"), "") = "image-generation"
           OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
           OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r'"(obrazek|obraz|image|zdjęcie)\s+')
           OR LOWER(TO_JSON_STRING(jsonPayload)) LIKE "%image-generation%"
         )
         AND (SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) IS NULL OR SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) = 0) THEN 1 
        ELSE 0 
      END AS is_assistant_query,
      CASE
        WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") = "CreateAgent"
         AND NOT (
           COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.name"), "") LIKE "%/agents/deep_research"
           OR COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.agent.name"), "") LIKE "%/agents/deep_research"
           OR TO_JSON_STRING(jsonPayload) LIKE "%deep_research%"
         ) THEN 1
        ELSE 0
      END AS is_custom_agent_created,
      CASE
        WHEN SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) IS NOT NULL 
         AND SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.status.code") AS INT64) != 0 THEN 1
        ELSE 0
      END AS is_error_event,
      insertId,
      0 AS priority
    FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`

    UNION ALL

    -- Wstecznie zaingestowane logi (backfill)
    SELECT
      DATE(timestamp) AS activity_date,
      timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(user_iam_principal), "<elided>"), ""),
        NULLIF(user_pseudo_id, ""),
        (SELECT email FROM primary_admin),
        "system"
      ) AS user_id,
      method_name,
      page_type,
      event_type,
      engine,
      COALESCE(
        NULLIF(agent_id, ""),
        REGEXP_EXTRACT(raw_payload, r"/agents/([0-9a-zA-Z_\-]+)"),
        ""
      ) AS called_agent_id,
      REGEXP_EXTRACT(COALESCE(raw_payload, ""), r"sessions/([0-9]+)") AS session_id,
      CASE 
        WHEN method_name IN ("StreamAssist", "Assist") 
         AND (agent_id = "deep_research" OR raw_payload LIKE "%agents/deep_research%") THEN 1 
        ELSE 0 
      END AS is_deep_research,
      CASE
        WHEN method_name IN ("StreamAssist", "Assist")
         AND (
           page_type = "image-generation" 
           OR REGEXP_CONTAINS(LOWER(raw_payload), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
           OR REGEXP_CONTAINS(LOWER(raw_payload), r'"(obrazek|obraz|image|zdjęcie)\s+')
           OR LOWER(raw_payload) LIKE "%image-generation%"
         ) THEN 1
        ELSE 0
      END AS is_image_generation,
      CASE 
        WHEN method_name IN ("StreamAssist", "Assist") 
         AND NOT (agent_id = "deep_research" OR raw_payload LIKE "%agents/deep_research%")
         AND NOT (
           page_type = "image-generation" 
           OR REGEXP_CONTAINS(LOWER(raw_payload), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
           OR REGEXP_CONTAINS(LOWER(raw_payload), r'"(obrazek|obraz|image|zdjęcie)\s+')
           OR LOWER(raw_payload) LIKE "%image-generation%"
         ) THEN 1 
        ELSE 0 
      END AS is_assistant_query,
      CASE
        WHEN method_name = "CreateAgent"
         AND NOT (
           agent_id = "deep_research"
           OR raw_payload LIKE "%agents/deep_research%"
         ) THEN 1
        ELSE 0
      END AS is_custom_agent_created,
      0 AS is_error_event,
      insert_id AS insertId,
      1 AS priority
    FROM `{project_id}.{dataset_id}.gemini_enterprise_user_activity`
  )
  QUALIFY ROW_NUMBER() OVER(
    PARTITION BY COALESCE(NULLIF(insertId, ""), CONCAT(CAST(timestamp AS STRING), "_", method_name))
    ORDER BY priority ASC, timestamp ASC
  ) = 1
),
aggregated_user_events AS (
  SELECT
    activity_date,
    user_id,
    COUNT(*) AS total_events,
    SUM(is_assistant_query) AS assistant_queries,
    COALESCE(COUNT(DISTINCT CASE WHEN is_deep_research = 1 THEN session_id END), 0) AS deep_research_count,
    SUM(is_image_generation) AS images_generated,
    SUM(is_custom_agent_created) AS agents_created,
    COUNTIF(method_name = "UpdateAgent") AS agent_updates,
    COUNTIF(method_name = "WriteUserEvent") AS ui_page_views,
    SUM(is_error_event) AS failed_requests,
    MIN(timestamp) AS first_event,
    MAX(timestamp) AS last_event
  FROM raw_user_events
  GROUP BY 1, 2
),
agent_usage_events AS (
  SELECT
    c.activity_date,
    a.author_user_id AS user_id,
    COUNTIF(c.user_id = a.author_user_id) AS author_agent_invocations,
    COUNT(DISTINCT CASE WHEN c.user_id = a.author_user_id AND c.session_id IS NOT NULL THEN c.session_id END) AS author_agent_sessions,
    COUNT(*) AS org_agent_invocations,
    COUNT(DISTINCT c.session_id) AS org_agent_sessions,
    COUNT(DISTINCT c.user_id) AS org_agent_unique_callers
  FROM raw_user_events c
  JOIN agent_creators a ON c.called_agent_id = a.agent_id
  WHERE c.method_name IN ("StreamAssist", "Assist")
    AND c.called_agent_id != ""
    AND c.called_agent_id != "deep_research"
  GROUP BY 1, 2
),
raw_audit AS (
  -- Streamed & backfilled audit events
  SELECT
    DATE(timestamp) AS activity_date,
    timestamp,
    COALESCE(
      NULLIF(principal_email, ""),
      NULLIF(JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail"), ""),
      "unknown"
    ) AS user_id,
    COALESCE(method_name, JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.methodName"), "") AS method_name,
    COALESCE(resource_name, JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.resourceName"), "") AS resource_name,
    CASE 
      WHEN COALESCE(method_name, JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.methodName"), "") LIKE "%CreateAgent%"
       AND NOT COALESCE(resource_name, JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.resourceName"), "") LIKE "%/agents/deep_research"
       AND COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.status.code") AS INT64), 0) = 0 THEN 1 
      ELSE 0 
    END AS is_custom_agent_created
  FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
  WHERE NOT COALESCE(
    NULLIF(principal_email, ""),
    NULLIF(JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.authenticationInfo.principalEmail"), ""),
    ""
  ) LIKE "%@gcp-sa-%.iam.gserviceaccount.com"
  QUALIFY ROW_NUMBER() OVER(
    PARTITION BY COALESCE(NULLIF(insert_id, ""), NULLIF(insertId, ""), CONCAT(CAST(timestamp AS STRING), "_", COALESCE(method_name, JSON_VALUE(TO_JSON_STRING(protopayload_auditlog), "$.methodName"), "")))
    ORDER BY timestamp
  ) = 1
),
aggregated_audit AS (
  SELECT
    activity_date,
    user_id,
    COUNT(*) AS audit_events,
    SUM(is_custom_agent_created) AS agents_created,
    MIN(timestamp) AS first_audit,
    MAX(timestamp) AS last_audit
  FROM raw_audit
  GROUP BY 1, 2
),
raw_tokens AS (
  -- Strumień tokenów ze zlewu Cloud Logging w czasie rzeczywistym
  SELECT * FROM (
    SELECT
      DATE(inf.timestamp) AS activity_date,
      inf.timestamp,
      COALESCE(
        NULLIF(NULLIF(TRIM(JSON_VALUE(TO_JSON_STRING(act.jsonPayload), "$.useriamprincipal")), "<elided>"), ""),
        NULLIF(JSON_VALUE(TO_JSON_STRING(act.jsonPayload), "$.request.userevent.userpseudoid"), ""),
        CASE WHEN act.timestamp IS NOT NULL THEN (SELECT email FROM primary_admin) ELSE "unassigned" END
      ) AS user_id,
      CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(inf.jsonPayload), "$.gen_ai_usage_input_tokens") AS FLOAT64), 0) AS INT64) AS input_tokens,
      CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(inf.jsonPayload), "$.gen_ai_usage_output_tokens") AS FLOAT64), 0) AS INT64) AS output_tokens,
      CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(inf.jsonPayload), "$.gen_ai_usage_reasoning_output_tokens") AS FLOAT64), 0) AS INT64) AS cached_tokens,
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
        NULLIF(NULLIF(TRIM(user_id), "user"), ""),
        (SELECT email FROM primary_admin),
        "system"
      ) AS user_id,
      CAST(input_tokens AS INT64) AS input_tokens,
      CAST(output_tokens AS INT64) AS output_tokens,
      CAST(cached_tokens AS INT64) AS cached_tokens,
      insert_id AS insertId,
      0 AS priority
    FROM `{project_id}.{dataset_id}.gen_ai_client_inference_operation_details`
  )
  QUALIFY ROW_NUMBER() OVER(
    PARTITION BY COALESCE(NULLIF(insertId, ""), CAST(timestamp AS STRING))
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
  COALESCE(u.activity_date, a.activity_date, t.activity_date, ag.activity_date) AS activity_date,
  COALESCE(u.user_id, a.user_id, t.user_id, ag.user_id) AS user_id,
  COALESCE(u.total_events, a.audit_events, 0) AS total_events,
  COALESCE(u.assistant_queries, 0) AS assistant_queries,
  COALESCE(u.deep_research_count, 0) AS deep_research_count,
  COALESCE(u.images_generated, 0) AS images_generated,
  GREATEST(COALESCE(u.agents_created, 0), COALESCE(a.agents_created, 0)) AS agents_created,
  COALESCE(u.agent_updates, 0) AS agent_updates,
  COALESCE(u.ui_page_views, 0) AS ui_page_views,
  COALESCE(u.failed_requests, 0) AS failed_requests,
  COALESCE(ag.author_agent_invocations, 0) AS author_agent_invocations,
  COALESCE(ag.author_agent_sessions, 0) AS author_agent_sessions,
  COALESCE(ag.org_agent_invocations, 0) AS org_agent_invocations,
  COALESCE(ag.org_agent_sessions, 0) AS org_agent_sessions,
  COALESCE(ag.org_agent_unique_callers, 0) AS org_agent_unique_callers,
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
  AND COALESCE(u.activity_date, a.activity_date) = t.activity_date
FULL OUTER JOIN agent_usage_events ag
  ON COALESCE(u.user_id, a.user_id, t.user_id) = ag.user_id
  AND COALESCE(u.activity_date, a.activity_date, t.activity_date) = ag.activity_date
WHERE COALESCE(u.user_id, a.user_id, t.user_id, ag.user_id) NOT IN ("unknown", "system", "unassigned");

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
  SUM(images_generated) AS images_generated,
  SUM(agents_created) AS agents_created,
  SUM(agent_updates) AS agent_updates,
  SUM(ui_page_views) AS ui_page_views,
  SUM(failed_requests) AS failed_requests,
  SUM(author_agent_invocations) AS author_agent_invocations,
  SUM(author_agent_sessions) AS author_agent_sessions,
  SUM(org_agent_invocations) AS org_agent_invocations,
  SUM(org_agent_sessions) AS org_agent_sessions,
  MAX(org_agent_unique_callers) AS org_agent_unique_callers,
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
  SUM(images_generated) AS total_images_generated,
  SUM(agents_created) AS total_agents_created,
  SUM(agent_updates) AS total_agent_updates,
  SUM(ui_page_views) AS total_ui_page_views,
  SUM(failed_requests) AS total_failed_requests,
  SUM(org_agent_invocations) AS total_custom_agent_invocations,
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
      NULLIF(NULLIF(TRIM(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.useriamprincipal")), "<elided>"), ""),
      NULLIF(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.userpseudoid"), ""),
      "system"
    ) AS user_id,
    CASE
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist")
       AND (
         COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), "") LIKE "%/agents/deep_research"
         OR TO_JSON_STRING(jsonPayload) LIKE "%deep_research%"
       ) THEN "Deep Research"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist")
       AND (
         COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"), "") = "image-generation"
         OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
         OR REGEXP_CONTAINS(LOWER(TO_JSON_STRING(jsonPayload)), r'"(obrazek|obraz|image|zdjęcie)\s+')
         OR LOWER(TO_JSON_STRING(jsonPayload)) LIKE "%image-generation%"
       ) THEN "Image Generation (Modele graficzne)"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist")
       AND (
         COALESCE(
           NULLIF(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.agentsspec.agentspecs[0].agentid"), ""),
           REGEXP_EXTRACT(COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), ""), r"/agents/([^/]+)")
         ) IS NOT NULL
         AND COALESCE(
           NULLIF(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.agentsspec.agentspecs[0].agentid"), ""),
           REGEXP_EXTRACT(COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent"), ""), r"/agents/([^/]+)")
         ) != "deep_research"
       ) THEN "Custom Agent Conversation"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") IN ("StreamAssist", "Assist") THEN "General Assistant"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") = "CreateAgent" THEN "Custom Agent Creation"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "") = "UpdateAgent" THEN "Custom Agent Edit"
      WHEN COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"), "") != "" 
        THEN CONCAT("UI: ", JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.agentspaceinfo.agentspacepagetype"))
      ELSE COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname"), "Other")
    END AS feature_name
  FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
  
  UNION ALL
  
  SELECT
    timestamp,
    COALESCE(
      NULLIF(NULLIF(TRIM(user_iam_principal), "<elided>"), ""),
      NULLIF(user_pseudo_id, ""),
      "system"
    ) AS user_id,
    CASE
      WHEN method_name IN ("StreamAssist", "Assist") 
       AND (agent_id = "deep_research" OR raw_payload LIKE "%agents/deep_research%") THEN "Deep Research"
      WHEN method_name IN ("StreamAssist", "Assist") 
       AND (
         page_type = "image-generation" 
         OR REGEXP_CONTAINS(LOWER(raw_payload), r"(wygeneruj|stwórz|utwórz|zrób|generuj|generate|create|draw|narysuj|namaluj|paint)\s+(obraz|obrazek|grafik|zdjęci|image|picture|photo|illustration)")
         OR REGEXP_CONTAINS(LOWER(raw_payload), r'"(obrazek|obraz|image|zdjęcie)\s+')
         OR LOWER(raw_payload) LIKE "%image-generation%"
       ) THEN "Image Generation (Modele graficzne)"
      WHEN method_name IN ("StreamAssist", "Assist") 
       AND agent_id IS NOT NULL AND agent_id NOT IN ("", "deep_research") THEN "Custom Agent Conversation"
      WHEN method_name IN ("StreamAssist", "Assist") THEN "General Assistant"
      WHEN method_name = "CreateAgent" THEN "Custom Agent Creation"
      WHEN method_name = "UpdateAgent" THEN "Custom Agent Edit"
      WHEN COALESCE(page_type, "") != "" THEN CONCAT("UI: ", page_type)
      ELSE COALESCE(method_name, "Other")
    END AS feature_name
  FROM `{project_id}.{dataset_id}.gemini_enterprise_user_activity`
)
WHERE user_id != "system"
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
    NULLIF(NULLIF(TRIM(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.useriamprincipal")), "<elided>"), ""),
    JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.request.userevent.userpseudoid"),
    "anonymous_user"
  ) AS user_id,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.methodname") AS method_name,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.logmetadata.servicename") AS service_name,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.answer.state") AS answer_state,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.displayname") AS agent_display_name,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.response.agentinfo.agent") AS agent_resource,
  severity,
  insertId
FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gemini_enterprise_user_activity`
WHERE trace IS NOT NULL
ORDER BY timestamp DESC;

-- 7. Widok szczegółowej telemetrii zużycia tokenów LLM (OpenTelemetry Spans & GenAI Operations)
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.v_token_telemetry` AS
SELECT
  timestamp,
  DATE(timestamp) AS activity_date,
  insertId AS insert_id,
  trace AS trace_id,
  spanId AS span_id,
  CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_usage_input_tokens") AS FLOAT64), 0) AS INT64) AS input_tokens,
  CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_usage_output_tokens") AS FLOAT64), 0) AS INT64) AS output_tokens,
  CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_usage_reasoning_output_tokens") AS FLOAT64), 0) AS INT64) AS cached_tokens,
  (CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_usage_input_tokens") AS FLOAT64), 0) AS INT64) + CAST(COALESCE(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_usage_output_tokens") AS FLOAT64), 0) AS INT64)) AS total_tokens,
  COALESCE(JSON_VALUE(TO_JSON_STRING(jsonPayload), "$.gen_ai_agent_name"), "") AS agent_name,
  severity
FROM `{project_id}.{dataset_id}.discoveryengine_googleapis_com_gen_ai_client_inference_operation_details`

UNION ALL

SELECT
  timestamp,
  DATE(timestamp) AS activity_date,
  insert_id,
  NULL AS trace_id,
  NULL AS span_id,
  CAST(COALESCE(input_tokens, 0) AS INT64) AS input_tokens,
  CAST(COALESCE(output_tokens, 0) AS INT64) AS output_tokens,
  CAST(COALESCE(cached_tokens, 0) AS INT64) AS cached_tokens,
  (CAST(COALESCE(input_tokens, 0) AS INT64) + CAST(COALESCE(output_tokens, 0) AS INT64)) AS total_tokens,
  COALESCE(agent_name, "") AS agent_name,
  "DEFAULT" AS severity
FROM `{project_id}.{dataset_id}.gen_ai_client_inference_operation_details`;
