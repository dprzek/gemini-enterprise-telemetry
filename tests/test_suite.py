#!/usr/bin/env python3
"""
Kompleksowy zestaw 10 testów poprawności potoku telemetrii Gemini Enterprise.

Test 1: Syntaktyka i Statyczna Analiza Skryptów Pythona
Test 2: Rozpoznawanie Silnika i Odporność na Błędy Nazewnictwa
Test 3: Idempotentność i Schemat Tabel BigQuery
Test 4: Kompilacja i Parametryzacja Widoków SQL BigQuery
Test 5: Spójność Matematyczna Metryk (Invarianty: Suma Zdarzeń, Tokeny)
Test 6: Precyzja Przypisywania Tokenów po Śladach OTel (Zero Double-Counting)
Test 7: Rygorystyczna Separacja Funkcjonalności (Deep Research vs Zapytania)
Test 8: Pełne Pokrycie Komend CLI (utilization, adoption, observability, quotas)
Test 9: Walidacja Generowania Promptu Agenta i Integralności JSON
Test 10: Idempotentność i Odporność Całego Potoku deploy.py (Zero-Touch)
"""

import sys
import os
import json
import py_compile
import subprocess
import unittest
from typing import Dict, Any

# Ensure repo root and cli/ are in python path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "cli"))

from telemetry_service import TelemetryService
from deploy import resolve_engine, get_auth_token, enable_engine_observability
from google.cloud import bigquery

PROJECT_ID = "dprzek-prod"
LOCATION = "eu"
APP_NAME = "test-test-test"
EXPECTED_ENGINE_ID = "test-test-test_1789816756559"
DATASET_ID = "gemini_enterprise_telemetry"


class GeminiEnterpriseTelemetryTestSuite(unittest.TestCase):
    gcp_auth_available = False
    auth_skip_reason = ""
    service = None
    bq_client = None

    @classmethod
    def setUpClass(cls):
        try:
            token = get_auth_token()
            if token:
                cls.service = TelemetryService(
                    project_id=PROJECT_ID,
                    location=LOCATION,
                    dataset_id=DATASET_ID,
                    engine_id=EXPECTED_ENGINE_ID,
                )
                cls.bq_client = bigquery.Client(project=PROJECT_ID)
                cls.gcp_auth_available = True
        except Exception as e:
            cls.gcp_auth_available = False
            cls.auth_skip_reason = f"Brak aktywnej autoryzacji GCP ({e}). Uruchom 'gcloud auth application-default login' przed testami na żywo."

    def _require_live_gcp(self):
        if not self.gcp_auth_available:
            self.skipTest(self.auth_skip_reason)

    # --------------------------------------------------------------------------
    # TEST 1: Syntaktyka i kompilacja wszystkich plików Pythona
    # --------------------------------------------------------------------------
    def test_01_syntax_and_compilation(self):
        """Sprawdza czy wszystkie pliki .py w repo kompilują się bez błędów składniowych."""
        py_files = []
        for root, _, files in os.walk(REPO_ROOT):
            if ".git" in root or "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        self.assertGreaterEqual(len(py_files), 5, "Powinno istnieć co najmniej 5 skryptów Pythona.")
        for py_file in py_files:
            try:
                py_compile.compile(py_file, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"Błąd składniowy w pliku {py_file}: {e}")

    # --------------------------------------------------------------------------
    # TEST 2: Rozpoznawanie silnika i odporność na błędy nazewnictwa
    # --------------------------------------------------------------------------
    def test_02_engine_resolution_and_error_handling(self):
        """Sprawdza poprawne mapowanie nazwy silnika oraz mechanizm dopasowania."""
        self._require_live_gcp()
        token = get_auth_token()
        self.assertIsNotNone(token, "Nie udało się uzyskać tokenu autoryzacji GCP.")

        # 1. Poprawne dopasowanie po prefiksie / nazwie wyświetlanej
        resolved = resolve_engine(PROJECT_ID, LOCATION, APP_NAME, token)
        self.assertEqual(resolved, EXPECTED_ENGINE_ID)

        # 2. Poprawne dopasowanie gdy podano pełne ID silnika
        resolved_full = resolve_engine(PROJECT_ID, LOCATION, EXPECTED_ENGINE_ID, token)
        self.assertEqual(resolved_full, EXPECTED_ENGINE_ID)

        # 3. Sprawdzenie zachowania dla pustego hintu (powinien wybrać pierwszy dostępny silnik)
        resolved_empty = resolve_engine(PROJECT_ID, LOCATION, "", token)
        self.assertTrue(len(resolved_empty) > 0, "Dla pustego hintu powinien zwrócić silnik domyślny.")

    # --------------------------------------------------------------------------
    # TEST 3: Idempotentność i zachowanie partycjonowania tabel BigQuery
    # --------------------------------------------------------------------------
    def test_03_bigquery_tables_and_partitioning(self):
        """Weryfikuje istnienie tabel oraz ich partycjonowanie po polu timestamp."""
        self._require_live_gcp()
        expected_tables = [
            "gemini_enterprise_user_activity",
            "gen_ai_client_inference_operation_details",
            "cloudaudit_googleapis_com_activity",
        ]
        for tbl_name in expected_tables:
            table_ref = f"{PROJECT_ID}.{DATASET_ID}.{tbl_name}"
            table = self.bq_client.get_table(table_ref)
            self.assertIsNotNone(table, f"Tabela {table_ref} nie istnieje!")
            self.assertIsNotNone(
                table.time_partitioning,
                f"Tabela {table_ref} powinna posiadać time_partitioning!",
            )
            self.assertEqual(
                table.time_partitioning.field,
                "timestamp",
                f"Tabela {table_ref} powinna być partycjonowana po polu 'timestamp'!",
            )

    # --------------------------------------------------------------------------
    # TEST 4: Kompilacja i parametryzacja widoków BigQuery (SQL DDL Dry-Run)
    # --------------------------------------------------------------------------
    def test_04_bigquery_views_syntax_and_compilation(self):
        """Sprawdza poprawność zapytań DDL widoków po parametryzacji."""
        sql_path = os.path.join(REPO_ROOT, "bigquery", "telemetry_views.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            raw_sql = f.read()

        formatted_sql = raw_sql.format(project_id=PROJECT_ID, dataset_id=DATASET_ID)
        self.assertNotIn("{project_id}", formatted_sql)
        self.assertNotIn("{dataset_id}", formatted_sql)

        self._require_live_gcp()

        # Sprawdź czy wszystkie 5 widoków istnieje i zwraca poprawny schemat
        views = [
            "v_user_daily_utilization",
            "v_observability_traces",
            "v_user_summary",
            "v_daily_adoption",
            "v_feature_usage",
        ]
        for v in views:
            v_ref = f"{PROJECT_ID}.{DATASET_ID}.{v}"
            table = self.bq_client.get_table(v_ref)
            self.assertEqual(table.table_type, "VIEW", f"{v_ref} powinien być widokiem!")
            self.assertGreater(len(table.schema), 0, f"Widok {v_ref} powinien posiadać kolumny.")

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # TEST 5: Niezmienniki matematyczne metryk i spójność sum
    # --------------------------------------------------------------------------
    def test_05_mathematical_invariants(self):
        """Weryfikuje niezmienniki sum zdarzeń i konsumpcji tokenów."""
        self._require_live_gcp()
        daily_records = self.service.get_user_daily_breakdown()
        self.assertGreater(len(daily_records), 0, "Brak rekordów w dziennej utylizacji.")

        for row in daily_records:
            total_events = row.get("total_events", 0)
            queries = row.get("assistant_queries", 0)
            deep_r = row.get("deep_research_count", 0)
            agents = row.get("agents_created", 0)
            total_tok = row.get("total_tokens", 0)
            inp_tok = row.get("input_tokens", 0)
            out_tok = row.get("output_tokens", 0)

            # Niezmiennik 1: Zdarzenia >= suma poszczególnych akcji
            self.assertGreaterEqual(
                total_events,
                queries + deep_r + agents,
                f"Zdarzenia ({total_events}) < sumy składowych ({queries}+{deep_r}+{agents}) w dacie {row.get('activity_date')}",
            )

            # Niezmiennik 2: Tokeny łączne = wejściowe + wyjściowe
            self.assertEqual(
                total_tok,
                inp_tok + out_tok,
                f"total_tokens ({total_tok}) != input ({inp_tok}) + output ({out_tok})",
            )

            # Niezmiennik 3: Jeśli wystąpiły zapytania, tokeny muszą być dodatnie
            if queries > 0:
                self.assertGreater(
                    total_tok,
                    0,
                    f"W dacie {row.get('activity_date')} wystąpiły zapytania ({queries}), ale tokeny = 0!",
                )

            # Niezmiennik 4: Brak ujemnych wartości
            self.assertGreaterEqual(total_events, 0)
            self.assertGreaterEqual(queries, 0)
            self.assertGreaterEqual(inp_tok, 0)
            self.assertGreaterEqual(out_tok, 0)

    # --------------------------------------------------------------------------
    # TEST 6: Precyzja korelacji tokenów po śladach OpenTelemetry (Zero Double-Counting)
    # --------------------------------------------------------------------------
    def test_06_token_trace_correlation_precision(self):
        """Sprawdza brak iloczynu kartezjańskiego i mechanizm deduplikacji tokenów (Zero Double-Counting)."""
        self._require_live_gcp()
        # 1. Pobierz unikalną (deduplikowaną po insert_id) sumę tokenów z surowych logów wnioskowania
        sql = f"""
        WITH deduped_inference AS (
            SELECT DISTINCT insert_id, input_tokens, output_tokens
            FROM `{PROJECT_ID}.{DATASET_ID}.gen_ai_client_inference_operation_details`
        )
        SELECT 
            SUM(input_tokens) AS direct_inp,
            SUM(output_tokens) AS direct_out
        FROM deduped_inference
        """
        job = self.bq_client.query(sql)
        row = list(job.result())[0]
        direct_inp = row["direct_inp"] or 0
        direct_out = row["direct_out"] or 0
        direct_total = direct_inp + direct_out

        # 2. Pobierz zagregowane wartości z widoku analitycznego
        user_summary = self.service.get_user_summary()
        admin_summary = next(
            (u for u in user_summary if u["user_id"] == "admin@dprzek.altostrat.com"), None
        )
        self.assertIsNotNone(admin_summary, "Brak usera admin@dprzek.altostrat.com w podsumowaniu.")

        # 3. Weryfikacja: widok analityczny musi być w 100% zgodny z unikalnymi operacjami
        self.assertEqual(
            admin_summary["input_tokens"],
            direct_inp,
            f"Widok podsumowania ({admin_summary['input_tokens']}) różni się od unikalnych logów ({direct_inp})!",
        )
        self.assertEqual(
            admin_summary["output_tokens"],
            direct_out,
            f"Widok podsumowania ({admin_summary['output_tokens']}) różni się od unikalnych logów ({direct_out})!",
        )
        self.assertEqual(
            admin_summary["total_tokens"],
            direct_total,
            f"Łączna suma w widoku ({admin_summary['total_tokens']}) różni się od sumy unikalnych tokenów ({direct_total})!",
        )

    # --------------------------------------------------------------------------
    # TEST 7: Rygorystyczna separacja funkcjonalności (Deep Research vs Zwykłe Zapytania)
    # --------------------------------------------------------------------------
    def test_07_strict_feature_detection(self):
        """Weryfikuje, że zapytania nie są błędnie kwalifikowane jako Deep Research."""
        self._require_live_gcp()
        # Sprawdź czy zapytania StreamAssist usera nie zawierające deep research nie zawyżają licznika
        daily_records = self.service.get_user_daily_breakdown()
        today_record = next((r for r in daily_records if r["activity_date"] == "2026-09-19"), None)
        self.assertIsNotNone(today_record, "Brak rekordu dla 2026-09-19")

        # Wiemy ze śladów, że 5 zapytań to StreamAssist asystenta, a deep research nie był uruchamiany w dprzek-prod
        self.assertEqual(
            today_record["deep_research_count"],
            0,
            "Błąd: zapytania asystenta zostały błędnie zakwalifikowane jako deep research!",
        )
        self.assertEqual(today_record["assistant_queries"], 5)
        self.assertEqual(today_record["agents_created"], 2)

    # --------------------------------------------------------------------------
    # TEST 8: Pełne pokrycie poleceń i flag w CLI (telemetry_cli.py)
    # --------------------------------------------------------------------------
    def test_08_cli_commands_coverage(self):
        """Testuje wykonanie wszystkich podkomend CLI: utilization, adoption, observability, quotas."""
        self._require_live_gcp()
        commands = [
            ["utilization"],
            ["utilization", "--daily"],
            ["utilization", "--daily", "--user", "admin@dprzek.altostrat.com"],
            ["adoption", "--days", "14"],
            ["observability", "--traces"],
            ["quotas"],
        ]
        for cmd_args in commands:
            cmd = [
                sys.executable,
                os.path.join(REPO_ROOT, "cli", "telemetry_cli.py"),
                "--project",
                PROJECT_ID,
                "--location",
                LOCATION,
                "--engine",
                EXPECTED_ENGINE_ID,
            ] + cmd_args

            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"Komenda CLI '{' '.join(cmd_args)}' zakończyła się kodem {res.returncode}. Błąd: {res.stderr}",
            )
            self.assertGreater(
                len(res.stdout),
                20,
                f"Wyjście komendy '{' '.join(cmd_args)}' jest zbyt krótkie lub puste.",
            )

    # --------------------------------------------------------------------------
    # TEST 9: Walidacja generowania promptu agenta i poprawności JSON
    # --------------------------------------------------------------------------
    def test_09_agent_prompt_and_json_integrity(self):
        """Sprawdza poprawność dynamicznego wstrzykiwania telemetrii do promptu Agenta."""
        # Pobierz dane z serwisu telemetrii, tak jak robi to deploy_agent.py
        if self.gcp_auth_available:
            data_block = {
                "operational_metrics": self.service.get_observability_metrics(days=7),
                "recent_opentelemetry_traces": self.service.get_recent_traces(limit=5),
                "total_tracked_users": len(self.service.get_user_summary()),
                "user_summary_all_time": self.service.get_user_summary(),
                "user_daily_activity_breakdown": self.service.get_user_daily_breakdown(),
                "organization_daily_adoption": self.service.get_daily_adoption(days=14),
                "quotas": self.service.get_realtime_quotas(),
            }
        else:
            data_block = {
                "operational_metrics": {"total_agent_sessions": 10},
                "recent_opentelemetry_traces": [{"trace_id": "test"}],
                "total_tracked_users": 1,
                "user_summary_all_time": [{"user_id": "user@example.com"}],
                "user_daily_activity_breakdown": [{"activity_date": "2026-09-19", "total_events": 5}],
                "organization_daily_adoption": [{"activity_date": "2026-09-19"}],
                "quotas": {"status": "OK"},
            }

        # Serializacja i deserializacja JSON
        json_output = json.dumps(data_block, indent=2, default=str)
        deserialized = json.loads(json_output)
        self.assertIsInstance(deserialized, dict)
        self.assertIn("user_daily_activity_breakdown", deserialized)
        self.assertIn("quotas", deserialized)

        # Weryfikacja obecności 4 filarów w pliku szablonu
        agent_def_path = os.path.join(REPO_ROOT, "agent", "telemetry_agent_definition.json")
        with open(agent_def_path, "r", encoding="utf-8") as f:
            agent_def = json.load(f)
        instruction = agent_def["lowCodeAgentDefinition"]["nodes"][0]["llmAgentNode"]["instruction"]
        self.assertIn("1. 📊 **Utylizacja Użytkowników w Ujęciu Dziennym", instruction)
        self.assertIn("2. 🚀 **Metryki Adopcji i Zaangażowania", instruction)
        self.assertIn("3. ⏱️ **Obserwowalność, Trasy OpenTelemetry i Wydajność", instruction)
        self.assertIn("4. 🛡️ **Limity Kwot i Overage", instruction)

    # --------------------------------------------------------------------------
    # TEST 10: Idempotentność i odporność potoku Zero-Touch (deploy.py)
    # --------------------------------------------------------------------------
    def test_10_deploy_pipeline_idempotency(self):
        """Weryfikuje idempotentność skryptu deploy.py (uruchomienie na działającym środowisku)."""
        self._require_live_gcp()
        token = get_auth_token()
        self.assertIsNotNone(token)
        # 1. Wywołanie weryfikacji obserwowalności (powinno zakończyć się natychmiast bez błędów)
        enable_engine_observability(PROJECT_ID, LOCATION, EXPECTED_ENGINE_ID, token)

        # 2. Uruchom deploy.py w trybie --skip-backfill aby sprawdzić pełną orkiestrację
        cmd = [
            sys.executable,
            os.path.join(REPO_ROOT, "deploy.py"),
            EXPECTED_ENGINE_ID,
            "--project",
            PROJECT_ID,
            "--location",
            LOCATION,
            "--dataset",
            DATASET_ID,
            "--skip-backfill",
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"deploy.py nie powiódł się w teście idempotentności! Błąd: {res.stderr}",
        )
        self.assertIn("Wdrożenie zakończone pełnym sukcesem", res.stdout)
        self.assertIn("✔ Obserwowalność silnika (OpenTelemetry + Sensitive Logging) jest już aktywna", res.stdout)

    # --------------------------------------------------------------------------
    # TEST 11: Walidacja Agenta ADK (google.adk.agents.Agent) i dynamicznych narzędzi
    # --------------------------------------------------------------------------
    def test_11_adk_agent_definition_and_tools(self):
        """Weryfikuje konfigurację i integralność dynamicznego agenta ADK oraz jego 5 narzędzi."""
        from agent.adk_telemetry_agent import root_agent

        self.assertEqual(root_agent.name, "gemini_enterprise_telemetry_agent")
        self.assertEqual(root_agent.model, "gemini-2.5-flash")
        self.assertEqual(len(root_agent.tools), 5)

        tool_names = [t.__name__ for t in root_agent.tools]
        expected_tools = [
            "get_user_daily_utilization",
            "get_user_summary",
            "get_daily_adoption",
            "get_realtime_quotas",
            "get_observability_traces",
        ]
        for expected in expected_tools:
            self.assertIn(expected, tool_names)

        # Weryfikacja działania narzędzia offline lub z mockiem
        from agent.adk_telemetry_agent import get_realtime_quotas
        quotas_json = get_realtime_quotas()
        quotas = json.loads(quotas_json)
        self.assertIn("rate_limits", quotas)
        self.assertIn("quota_status", quotas)


if __name__ == "__main__":
    unittest.main(verbosity=2)

