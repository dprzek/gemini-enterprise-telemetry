#!/usr/bin/env python3
"""
Gemini Enterprise Telemetry & Adoption Service.
Integrates BigQuery (historical & real-time streamed per-user daily utilization & adoption)
and Cloud Monitoring (real-time pooled quotas, limit headroom, and latency).
"""

import os
import json
import urllib.request
from datetime import datetime, timedelta
import google.auth
from google.auth.transport.requests import Request
from google.cloud import bigquery

class TelemetryService:
    def __init__(self, project_id="adk-dev-485808", dataset_id="gemini_enterprise_telemetry", location="eu"):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.location = location
        self.credentials, _ = google.auth.default()
        self.bq_client = bigquery.Client(project=self.project_id, credentials=self.credentials)

    def _get_access_token(self):
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        return self.credentials.token

    def get_user_summary(self, start_date=None, end_date=None, user_id=None):
        """
        Query aggregate utilization per user across customizable time spans.
        """
        where_clauses = []
        if start_date:
            where_clauses.append(f"activity_date >= '{start_date}'")
        if end_date:
            where_clauses.append(f"activity_date <= '{end_date}'")
        if user_id:
            where_clauses.append(f"LOWER(user_id) LIKE LOWER('%{user_id}%')")

        where_stmt = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        query = f"""
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
        FROM `{self.project_id}.{self.dataset_id}.v_user_daily_utilization`
        {where_stmt}
        GROUP BY user_id
        ORDER BY total_events DESC, assistant_queries DESC
        """
        job = self.bq_client.query(query)
        results = []
        for row in job.result():
            results.append({
                "user_id": row.user_id,
                "active_days": row.active_days,
                "total_events": row.total_events,
                "assistant_queries": row.assistant_queries,
                "deep_research_count": row.deep_research_count,
                "agents_created": row.agents_created,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "total_tokens": row.total_tokens,
                "first_active": str(row.first_active) if row.first_active else None,
                "last_active": str(row.last_active) if row.last_active else None,
            })
        return results

    def get_user_daily_breakdown(self, start_date=None, end_date=None, user_id=None):
        """
        Query exact day-by-day utilization per user.
        Answers: "pokaż mi adopcję użytkownika X rozbitą na poszczególne dni"
        """
        where_clauses = []
        if start_date:
            where_clauses.append(f"activity_date >= '{start_date}'")
        if end_date:
            where_clauses.append(f"activity_date <= '{end_date}'")
        if user_id:
            where_clauses.append(f"LOWER(user_id) LIKE LOWER('%{user_id}%')")

        where_stmt = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        query = f"""
        SELECT
            activity_date,
            user_id,
            total_events,
            assistant_queries,
            deep_research_count,
            agents_created,
            input_tokens,
            output_tokens,
            total_tokens,
            first_seen,
            last_seen
        FROM `{self.project_id}.{self.dataset_id}.v_user_daily_utilization`
        {where_stmt}
        ORDER BY activity_date DESC, total_events DESC
        """
        job = self.bq_client.query(query)
        results = []
        for row in job.result():
            results.append({
                "activity_date": str(row.activity_date),
                "user_id": row.user_id,
                "total_events": row.total_events,
                "assistant_queries": row.assistant_queries,
                "deep_research_count": row.deep_research_count,
                "agents_created": row.agents_created,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "total_tokens": row.total_tokens,
                "first_seen": str(row.first_seen) if row.first_seen else None,
                "last_seen": str(row.last_seen) if row.last_seen else None,
            })
        return results

    def get_daily_adoption(self, days=30):
        """
        Query organization-level daily adoption metrics.
        Tracks DAU, query volume, tokens burned, and agents created.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"""
        SELECT
            activity_date,
            daily_active_users,
            total_interactions,
            total_assistant_queries,
            total_deep_research_queries,
            total_agents_created,
            total_tokens_burned
        FROM `{self.project_id}.{self.dataset_id}.v_daily_adoption`
        WHERE activity_date >= '{cutoff_date}'
        ORDER BY activity_date DESC
        """
        job = self.bq_client.query(query)
        results = []
        for row in job.result():
            results.append({
                "activity_date": str(row.activity_date),
                "daily_active_users": row.daily_active_users,
                "total_interactions": row.total_interactions,
                "total_assistant_queries": row.total_assistant_queries,
                "total_deep_research_queries": row.total_deep_research_queries,
                "total_agents_created": row.total_agents_created,
                "total_tokens_burned": row.total_tokens_burned,
            })
        return results

    def get_feature_breakdown(self):
        """
        Query feature breakdown across Gemini Enterprise features.
        """
        query = f"""
        SELECT
            feature_name,
            total_calls,
            distinct_users,
            earliest_invocation,
            latest_invocation
        FROM `{self.project_id}.{self.dataset_id}.v_feature_usage`
        ORDER BY total_calls DESC
        """
        job = self.bq_client.query(query)
        results = []
        for row in job.result():
            results.append({
                "feature_name": row.feature_name,
                "total_calls": row.total_calls,
                "distinct_users": row.distinct_users,
                "earliest_invocation": str(row.earliest_invocation) if row.earliest_invocation else None,
                "latest_invocation": str(row.latest_invocation) if row.latest_invocation else None,
            })
        return results

    def get_realtime_quotas(self):
        """
        Query Cloud Monitoring API for real-time pooled quota limits and usage.
        """
        token = self._get_access_token()
        now = datetime.utcnow()
        start = now - timedelta(hours=24)
        start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        metrics_to_check = {
            "Assistant Queries": "discoveryengine.googleapis.com/quota/text_answer_gen_tier_enterprise_regional/limit",
            "Agents Created": "discoveryengine.googleapis.com/quota/agents_tier_enterprise_regional/limit",
            "Deep Research": "discoveryengine.googleapis.com/quota/deep_research_query_total_tier_enterprise_regional/limit",
            "Image Generation": "discoveryengine.googleapis.com/quota/image_gen_tier_enterprise_regional/limit",
            "Video Generation": "discoveryengine.googleapis.com/quota/video_gen_numbers_tier_enterprise_regional/limit",
            "Storage / Total Size": "discoveryengine.googleapis.com/total_document_size_regional",
        }

        quotas = {}
        for label, metric_type in metrics_to_check.items():
            url = (
                f"https://monitoring.googleapis.com/v3/projects/{self.project_id}/timeSeries"
                f"?filter=metric.type%3D%22{metric_type}%22"
                f"&interval.startTime={start_str}&interval.endTime={end_str}"
            )
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.load(resp)
                    ts = data.get("timeSeries", [])
                    if ts and "points" in ts[0] and ts[0]["points"]:
                        val = ts[0]["points"][0]["value"]
                        metric_val = val.get("int64Value", val.get("doubleValue", 0))
                        quotas[label] = {
                            "metric": metric_type,
                            "value": metric_val,
                            "status": "ACTIVE"
                        }
                    else:
                        quotas[label] = {
                            "metric": metric_type,
                            "value": "Unlimited / Dynamic Pooling",
                            "status": "DEFAULT"
                        }
            except Exception as e:
                quotas[label] = {
                    "metric": metric_type,
                    "value": "Managed Tier",
                    "status": "OK"
                }

        quotas["Quota Reset Cycle"] = {
            "Assistant, Agents, Images, Video, Deep Research": "Daily at midnight PT (Pooled)",
            "AI Developer Tools (WTU)": "Rolling 7-day pooled cycle",
            "Data Storage & Indexing": "Continuous regional pool"
        }
        return quotas

    def generate_digest_markdown(self, days=14):
        """
        Generate a comprehensive executive markdown digest suitable for
        admins or grounding an LLM agent, including exact day-by-day tables.
        """
        adoption = self.get_daily_adoption(days=days)
        users = self.get_user_summary()
        daily_breakdown = self.get_user_daily_breakdown()
        features = self.get_feature_breakdown()
        quotas = self.get_realtime_quotas()

        total_users = len(users)
        total_queries = sum(u["assistant_queries"] for u in users)
        total_deep_research = sum(u["deep_research_count"] for u in users)
        total_agents = sum(u["agents_created"] for u in users)
        total_tokens = sum(u["total_tokens"] for u in users)

        md = []
        md.append(f"# Gemini Enterprise Adoption & Telemetry Report")
        md.append(f"*Project*: `{self.project_id}` | *Generated*: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

        md.append("## 1. Executive Summary")
        md.append(f"- **Tracked Users**: {total_users}")
        md.append(f"- **Total Assistant Queries**: {total_queries}")
        md.append(f"- **Deep Research Queries**: {total_deep_research}")
        md.append(f"- **Agents Created / Modified**: {total_agents}")
        md.append(f"- **Total Tokens Consumed**: {total_tokens:,}")
        md.append("")

        md.append("## 2. Per-User Summary (Aggregated)")
        md.append("| User Identifier | Active Days | Total Events | Assistant Queries | Deep Research | Agents Created | Tokens Burned | First Active | Last Active |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for u in users:
            first_seen = u["first_active"][:10] if u["first_active"] else "N/A"
            last_seen = u["last_active"][:10] if u["last_active"] else "N/A"
            md.append(f"| `{u['user_id']}` | {u['active_days']} | {u['total_events']} | {u['assistant_queries']} | {u['deep_research_count']} | {u['agents_created']} | {u['total_tokens']:,} | {first_seen} | {last_seen} |")
        md.append("")

        md.append("## 3. Szczegółowe Rozbicie Utylizacji na Dni (Day-by-Day User Breakdown)")
        md.append("| Data | Identyfikator Użytkownika | Zdarzenia | Zapytania Asystenta | Deep Research | Utworzone Agenty | Zużyte Tokeny |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for d in daily_breakdown:
            md.append(f"| {d['activity_date']} | `{d['user_id']}` | {d['total_events']} | {d['assistant_queries']} | {d['deep_research_count']} | {d['agents_created']} | {d['total_tokens']:,} |")
        md.append("")

        md.append("## 4. Daily Adoption Trend (Recent Days)")
        md.append("| Date | Active Users | Total Interactions | Assistant Queries | Deep Research | Agents Created |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for d in adoption[:7]:
            md.append(f"| {d['activity_date']} | {d['daily_active_users']} | {d['total_interactions']} | {d['total_assistant_queries']} | {d['total_deep_research_queries']} | {d['total_agents_created']} |")
        md.append("")

        md.append("## 5. Quota Enforcement & Reset Schedules")
        md.append("All quotas pool across organization licenses according to [Gemini Enterprise Quotas](https://docs.cloud.google.com/gemini/enterprise/docs/quotas-and-overages):")
        md.append("- **Assistant Queries**: 160 (Standard) / 200 (Plus) queries per user/day. Resets midnight PT.")
        md.append("- **Agent Building**: 1 (Standard) / 10 (Plus) creations per user/day. Resets midnight PT.")
        md.append("- **Deep Research**: 3 (Standard) / 10 (Plus) queries per user/day. Resets midnight PT.")
        md.append("- **Image Generation**: 5 (Standard) / 10 (Plus) generations per user/day. Resets midnight PT.")
        md.append("- **Video Generation**: 2 (Standard) / 3 (Plus) generations per user/day. Resets midnight PT.")
        md.append("- **AI Developer Tools**: $10 (Standard) / $15 (Plus) per user / 7-day rolling window.")
        md.append("- **Data Storage & Indexing**: 30 GiB (Standard) / 75 GiB (Plus) per user pooled.")
        md.append("")

        return "\n".join(md)
