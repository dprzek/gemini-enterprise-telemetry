#!/usr/bin/env python3
"""
Interfejs wiersza poleceń (CLI) dla administratorów Gemini Enterprise.
Umożliwia badanie metryk adopcji, utylizacji per-user w ujęciu dziennym,
metryk obserwowalności OpenTelemetry, rozproszonych śladów oraz limitów kwotowych.
"""

import os
import sys
import argparse
import json
from telemetry_service import TelemetryService

def main():
    parser = argparse.ArgumentParser(description="CLI do Telemetrii, Adopcji i Obserwowalności Gemini Enterprise")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"), help="Identyfikator projektu GCP (domyślnie z $GOOGLE_CLOUD_PROJECT)")
    parser.add_argument("--dataset", default=os.environ.get("DATASET_ID", "gemini_enterprise_telemetry"), help="Identyfikator zbioru danych BigQuery")
    parser.add_argument("--engine", default=os.environ.get("GEMINI_ENGINE_ID"), help="Identyfikator silnika Discovery Engine (np. my-app lub pełne ID)")
    parser.add_argument("--engine-id", dest="engine_id_flag", default=None, help="Jawny identyfikator silnika Discovery Engine (Engine ID)")
    parser.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "eu"), help="Lokalizacja Google Cloud (np. eu, us)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Komenda Utylizacji Użytkowników
    p_user = subparsers.add_parser("utilization", help="Zbadaj utylizację użytkowników w wybranym przedziale czasowym")
    p_user.add_argument("--user", help="Filtruj po adresie e-mail / identyfikatorze użytkownika")
    p_user.add_argument("--from-date", dest="from_date", help="Data początkowa (RRRR-MM-DD)")
    p_user.add_argument("--to-date", dest="to_date", help="Data końcowa (RRRR-MM-DD)")
    p_user.add_argument("--daily", action="store_true", help="Wyświetl szczegółowe rozbicie aktywności dzień po dniu")
    p_user.add_argument("--bottom", type=int, help="Pokaż N najmniej aktywnych użytkowników (Bottom N)")
    p_user.add_argument("--order", choices=["desc", "asc"], default="desc", help="Kierunek sortowania (domyślnie desc)")
    p_user.add_argument("--limit", type=int, help="Maksymalna liczba użytkowników")
    p_user.add_argument("--format", choices=["table", "json"], default="table", help="Format wyjściowy (table lub json)")

    # 2. Komenda Adopcji Organizacji
    p_adopt = subparsers.add_parser("adoption", help="Wyświetl trendy adopcji organizacji (DAU/WAU/MAU)")
    p_adopt.add_argument("--days", type=int, default=14, help="Liczba ostatnich dni do analizy")
    p_adopt.add_argument("--format", choices=["table", "json"], default="table", help="Format wyjściowy (table lub json)")

    # 3. Komenda Podziału Funkcjonalności
    p_feat = subparsers.add_parser("features", help="Wyświetl statystyki użycia poszczególnych modułów Gemini Enterprise")
    p_feat.add_argument("--format", choices=["table", "json"], default="table", help="Format wyjściowy (table lub json)")

    # 4. Komenda Obserwowalności i Śladów
    p_obs = subparsers.add_parser("observability", help="Sprawdź ustawienia obserwowalności OpenTelemetry, metryki zaangażowania i ślady")
    p_obs.add_argument("--days", type=int, default=7, help="Okno analizy metryk w dniach")
    p_obs.add_argument("--traces", action="store_true", help="Dołącz ostatnie rozproszone ślady (Cloud Trace)")
    p_obs.add_argument("--format", choices=["table", "json"], default="table", help="Format wyjściowy (table lub json)")

    # 5. Komenda Limitów Kwotowych
    p_quota = subparsers.add_parser("quotas", help="Wyświetl limity kwotowe (quotas), status zużycia i harmonogram resetowania")
    p_quota.add_argument("--format", choices=["table", "json"], default="table", help="Format wyjściowy (table lub json)")

    # 6. Komenda Raportu Markdown
    p_rep = subparsers.add_parser("report", help="Wygeneruj pełny raport markdown z telemetrii i obserwowalności")
    p_rep.add_argument("--output", help="Opcjonalna ścieżka pliku wyjściowego")
    p_rep.add_argument("--days", type=int, default=14, help="Liczba dni do uwzględnienia w raporcie")

    args = parser.parse_args()
    engine_val = args.engine_id_flag or args.engine
    service = TelemetryService(
        project_id=args.project,
        dataset_id=args.dataset,
        location=args.location,
        engine_id=engine_val
    )

    if args.command == "utilization":
        if args.daily:
            results = service.get_user_daily_breakdown(start_date=args.from_date, end_date=args.to_date, user_id=args.user)
            if args.format == "json":
                print(json.dumps(results, indent=2))
            else:
                if not results:
                    if args.user:
                        print(f"\nUżytkownik '{args.user}' nie posiada żadnych wpisów aktywności w wybranym okresie (zerowa utylizacja).")
                    else:
                        print("Brak wpisów dziennej aktywności dla podanych kryteriów.")
                    return
                print(f"\n=== Raport Dziennej Utylizacji Użytkownika ({len(results)} wpisów dziennych) ===")
                print(f"{'Data':<12} | {'Identyfikator Użytkownika':<28} | {'Zdarzenia':<9} | {'Zapytania':<9} | {'Obrazy':<7} | {'Deep Rsrch':<10} | {'Agenty':<7} | {'Wywoł. Autora':<13} | {'Wywoł. w Org':<13} | {'Tokeny':<9}")
                print("-" * 168)
                for r in results:
                    author_call = f"{r.get('author_agent_invocations', 0)} ({r.get('author_agent_sessions', 0)})"
                    org_call = f"{r.get('org_agent_invocations', 0)} ({r.get('org_agent_sessions', 0)}/{r.get('org_agent_unique_callers', 0)})"
                    print(f"{r['activity_date']:<12} | {r['user_id']:<28} | {r['total_events']:<9} | {r['assistant_queries']:<9} | {r.get('images_generated', 0):<7} | {r['deep_research_count']:<10} | {r['agents_created']:<7} | {author_call:<13} | {org_call:<13} | {r['total_tokens']:<9,}")
        else:
            order = "asc" if args.bottom else args.order
            limit = args.bottom or args.limit
            results = service.get_user_summary(start_date=args.from_date, end_date=args.to_date, user_id=args.user, order_by=order, limit=limit)
            if args.format == "json":
                print(json.dumps(results, indent=2))
            else:
                if not results:
                    if args.user:
                        print(f"\nUżytkownik '{args.user}' posiada zerową utylizację (0 zapytań, 0 sesji Deep Research, 0 utworzonych agentów, 0 tokenów).")
                    else:
                        print("Brak danych utylizacji dla podanych kryteriów.")
                    return
                header_title = f"Najmniej Aktywnych Użytkowników (Bottom {len(results)})" if (args.bottom or order == "asc") else f"Zbiorcze Podsumowanie Utylizacji Użytkowników ({len(results)} użytkowników)"
                print(f"\n=== {header_title} ===")
                print(f"{'Identyfikator Użytkownika':<28} | {'Aktywne Dni':<11} | {'Zdarzenia':<9} | {'Zapytania':<9} | {'Obrazy':<7} | {'Deep Rsrch':<10} | {'Agenty':<7} | {'Wywoł. Autora':<13} | {'Wywoł. w Org':<13} | {'Tokeny':<9}")
                print("-" * 168)
                for r in results:
                    author_call = f"{r.get('author_agent_invocations', 0)} ({r.get('author_agent_sessions', 0)})"
                    org_call = f"{r.get('org_agent_invocations', 0)} ({r.get('org_agent_sessions', 0)}/{r.get('org_agent_unique_callers', 0)})"
                    print(f"{r['user_id']:<28} | {r['active_days']:<11} | {r['total_events']:<9} | {r['assistant_queries']:<9} | {r.get('images_generated', 0):<7} | {r['deep_research_count']:<10} | {r['agents_created']:<7} | {author_call:<13} | {org_call:<13} | {r['total_tokens']:<9,}")
                print("\nWskazówka: Dodaj flagę '--daily', aby zobaczyć aktywność każdego użytkownika dzień po dniu.")

    elif args.command == "adoption":
        results = service.get_daily_adoption(days=args.days)
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\n=== Trendy Dziennej Adopcji w Organizacji (Ostatnie {args.days} Dni) ===")
            print(f"{'Data':<12} | {'DAU':<5} | {'Zdarzenia':<9} | {'Zapytania':<9} | {'Obrazy':<7} | {'Deep Rsrch':<10} | {'Agenty':<7} | {'Tokeny':<10}")
            print("-" * 87)
            for r in results:
                print(f"{r['activity_date']:<12} | {r['daily_active_users']:<5} | {r['total_interactions']:<9} | {r['total_assistant_queries']:<9} | {r.get('total_images_generated', 0):<7} | {r['total_deep_research_queries']:<10} | {r['total_agents_created']:<7} | {r['total_tokens_burned']:<10,}")

    elif args.command == "features":
        results = service.get_feature_breakdown()
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\n=== Statystyka Użycia Modułów i Funkcji ===")
            print(f"{'Nazwa Funkcjonalności':<35} | {'Wywołania':<12} | {'Użytkownicy':<15}")
            print("-" * 68)
            for r in results:
                print(f"{r['feature_name']:<35} | {r['total_calls']:<12} | {r['distinct_users']:<15}")

    elif args.command == "observability":
        metrics = service.get_observability_metrics(days=args.days)
        traces = service.get_recent_traces(limit=10) if args.traces else []
        if args.format == "json":
            out = {"metrics": metrics, "recent_traces": traces}
            print(json.dumps(out, indent=2))
        else:
            cfg = metrics["observability_settings"]
            print(f"\n=== Gemini Enterprise: Metryki Obserwowalności i OpenTelemetry ===")
            print(f"• Identyfikator Silnika:       {cfg.get('engine_id')}")
            print(f"• Lokalizacja:                 {cfg.get('location')}")
            print(f"• Obserwowalność Włączona:     {cfg.get('observability_enabled')}")
            print(f"• Wrażliwe Logowanie Włączone: {cfg.get('sensitive_logging_enabled')}")
            print(f"• Typ Aplikacji:               {cfg.get('app_type')}")
            print("-" * 68)
            print(f"• Liczba Sesji Agenta:         {metrics['total_agent_sessions']}")
            print(f"• Liczba Tur Konwersacyjnych:  {metrics['total_agent_turns']}")
            print(f"• Głębokość Konwersacji:       {metrics['conversational_depth_turns_per_session']} tury/sesję")
            print(f"• Sesje z Użyciem Narzędzi:    {metrics['total_sessions_with_tool']}")
            print(f"• Wskaźnik Adopcji Narzędzi:   {metrics['tool_adoption_rate_pct']}%")
            print(f"• Łączna Liczba Zapytań:       {metrics['total_engine_requests']}")
            print(f"• Średni Czas do 1. Tokena:    {metrics['avg_time_to_first_token_ms'] or 'Brak danych'} ms")
            print(f"• Średni Czas Całkowity:       {metrics['avg_request_total_latency_ms'] or 'Brak danych'} ms")

            if args.traces and traces:
                print(f"\n=== Ostatnie Rozproszone Ślady OpenTelemetry ({len(traces)} wpisy) ===")
                print(f"{'Czas (UTC)':<20} | {'Identyfikator Śladu (Trace ID)':<34} | {'Metoda':<14} | {'Użytkownik':<26} | {'Status':<8}")
                print("-" * 110)
                for t in traces:
                    print(f"{t['timestamp'][:19]:<20} | {t['trace_id']:<34} | {t['method_name']:<14} | {t['user_id']:<26} | {t['answer_state']:<8}")

    elif args.command == "quotas":
        quotas = service.get_realtime_quotas()
        if args.format == "json":
            print(json.dumps(quotas, indent=2))
        else:
            print(f"\n=== Status Limitów Kwotowych Gemini Enterprise (Quotas & Overages) ===")
            for k, v in quotas.items():
                if isinstance(v, dict) and "metric" in v:
                    print(f"• {k:<30}: {v['value']} ({v['status']})")
                elif isinstance(v, dict):
                    print(f"\n{k}:")
                    for sub_k, sub_v in v.items():
                        print(f"  - {sub_k:<45}: {sub_v}")

    elif args.command == "report":
        digest = service.generate_digest_markdown(days=args.days)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(digest)
            print(f"Raport zapisano do pliku: {args.output}")
        else:
            print(digest)

if __name__ == "__main__":
    main()
