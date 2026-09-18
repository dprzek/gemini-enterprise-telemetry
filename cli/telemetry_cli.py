#!/usr/bin/env python3
"""
Command Line Interface for Gemini Enterprise Admins.
Enables querying adoption metrics and per-user utilization over precise time spans
with full day-by-day breakdown.
"""

import os
import sys
import argparse
import json
from telemetry_service import TelemetryService

def main():
    parser = argparse.ArgumentParser(description="Gemini Enterprise Telemetry & Adoption CLI")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", "adk-dev-485808"), help="GCP Project ID")
    parser.add_argument("--dataset", default="gemini_enterprise_telemetry", help="BigQuery Dataset ID")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. User Utilization Command
    p_user = subparsers.add_parser("utilization", help="Query per-user utilization over a precise time span")
    p_user.add_argument("--user", help="Filter by specific user email / identifier")
    p_user.add_argument("--from-date", dest="from_date", help="Start date (YYYY-MM-DD)")
    p_user.add_argument("--to-date", dest="to_date", help="End date (YYYY-MM-DD)")
    p_user.add_argument("--daily", action="store_true", help="Display day-by-day activity breakdown for users")
    p_user.add_argument("--format", choices=["table", "json"], default="table")

    # 2. Daily Adoption Command
    p_adopt = subparsers.add_parser("adoption", help="View organization-wide daily adoption trends")
    p_adopt.add_argument("--days", type=int, default=14, help="Number of past days to inspect")
    p_adopt.add_argument("--format", choices=["table", "json"], default="table")

    # 3. Features Breakdown Command
    p_feat = subparsers.add_parser("features", help="View breakdown across Gemini Enterprise features")
    p_feat.add_argument("--format", choices=["table", "json"], default="table")

    # 4. Quotas Command
    p_quota = subparsers.add_parser("quotas", help="View quota limits, usage status, and reset policies")
    p_quota.add_argument("--format", choices=["table", "json"], default="table")

    # 5. Digest / Report Export
    p_rep = subparsers.add_parser("report", help="Generate full markdown adoption report with day-by-day table")
    p_rep.add_argument("--output", help="Optional output file path")
    p_rep.add_argument("--days", type=int, default=14)

    args = parser.parse_args()
    service = TelemetryService(project_id=args.project, dataset_id=args.dataset)

    if args.command == "utilization":
        if args.daily:
            results = service.get_user_daily_breakdown(start_date=args.from_date, end_date=args.to_date, user_id=args.user)
            if args.format == "json":
                print(json.dumps(results, indent=2))
            else:
                if not results:
                    print("No daily activity records found for the specified criteria.")
                    return
                print(f"\n=== Day-by-Day User Utilization Report ({len(results)} daily entries) ===")
                print(f"{'Date':<12} | {'User ID':<28} | {'Events':<7} | {'Queries':<8} | {'Deep Rsrch':<10} | {'Agents':<7} | {'Tokens':<10}")
                print("-" * 94)
                for r in results:
                    print(f"{r['activity_date']:<12} | {r['user_id']:<28} | {r['total_events']:<7} | {r['assistant_queries']:<8} | {r['deep_research_count']:<10} | {r['agents_created']:<7} | {r['total_tokens']:<10,}")
        else:
            results = service.get_user_summary(start_date=args.from_date, end_date=args.to_date, user_id=args.user)
            if args.format == "json":
                print(json.dumps(results, indent=2))
            else:
                if not results:
                    print("No utilization records found for the specified criteria.")
                    return
                print(f"\n=== User Utilization Summary ({len(results)} users) ===")
                print(f"{'User ID':<28} | {'Active Days':<11} | {'Events':<7} | {'Queries':<8} | {'Deep Rsrch':<10} | {'Agents':<7} | {'Tokens':<10}")
                print("-" * 94)
                for r in results:
                    print(f"{r['user_id']:<28} | {r['active_days']:<11} | {r['total_events']:<7} | {r['assistant_queries']:<8} | {r['deep_research_count']:<10} | {r['agents_created']:<7} | {r['total_tokens']:<10,}")
                print("\nTip: Add '--daily' to view day-by-day activity for each user.")

    elif args.command == "adoption":
        results = service.get_daily_adoption(days=args.days)
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\n=== Daily Adoption Trends (Past {args.days} Days) ===")
            print(f"{'Date':<12} | {'DAU':<5} | {'Events':<7} | {'Queries':<8} | {'Deep Rsrch':<10} | {'Agents':<7} | {'Tokens':<10}")
            print("-" * 75)
            for r in results:
                print(f"{r['activity_date']:<12} | {r['daily_active_users']:<5} | {r['total_interactions']:<7} | {r['total_assistant_queries']:<8} | {r['total_deep_research_queries']:<10} | {r['total_agents_created']:<7} | {r['total_tokens_burned']:<10,}")

    elif args.command == "features":
        results = service.get_feature_breakdown()
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\n=== Feature Usage Breakdown ===")
            print(f"{'Feature Name':<35} | {'Total Calls':<12} | {'Distinct Users':<15}")
            print("-" * 68)
            for r in results:
                print(f"{r['feature_name']:<35} | {r['total_calls']:<12} | {r['distinct_users']:<15}")

    elif args.command == "quotas":
        quotas = service.get_realtime_quotas()
        if args.format == "json":
            print(json.dumps(quotas, indent=2))
        else:
            print(f"\n=== Gemini Enterprise Quotas & Overages Status ===")
            for k, v in quotas.items():
                if isinstance(v, dict) and "metric" in v:
                    print(f"• {k:<25}: {v['value']} ({v['status']})")
                elif isinstance(v, dict):
                    print(f"\n{k}:")
                    for sub_k, sub_v in v.items():
                        print(f"  - {sub_k:<45}: {sub_v}")

    elif args.command == "report":
        digest = service.generate_digest_markdown(days=args.days)
        if args.output:
            with open(args.output, "w") as f:
                f.write(digest)
            print(f"Report saved to {args.output}")
        else:
            print(digest)

if __name__ == "__main__":
    main()
