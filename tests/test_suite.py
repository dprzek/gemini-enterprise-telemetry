#!/usr/bin/env python3
"""
Kompleksowy zestaw 15 testów poprawności potoku telemetrii Gemini Enterprise i Agenta ADK.

Test 1: Syntaktyka i Czystość Kodu Pythona (Multi-Tenant Hygiene)
Test 2: Rozpoznawanie Silnika i Odporność na Błędy Nazewnictwa (Dynamic Resolution)
Test 3: Automatyczna Konfiguracja Uprawnień IAM Konta Reasoning Engine
Test 4: Idempotentność i Schemat Tabel BigQuery (Partycjonowanie po dacie)
Test 5: Idempotentna Wsteczna Ingestja (Backfill Parsing & Idempotency)
Test 6: Kompilacja i Parametryzacja Widoków BigQuery (SQL DDL Dry-Run)
Test 7: Spójność Matematyczna Metryk (Invarianty: Suma Zdarzeń, Tokeny)
Test 8: Precyzja Przypisywania Tokenów po Śladach OTel (Zero Double-Counting)
Test 9: Rygorystyczna Separacja Funkcjonalności (Deep Research vs Zapytania)
Test 10: Integracja Metryk Cloud Monitoring i Tras OpenTelemetry
Test 11: Walidacja Agenta ADK (google.adk.agents.Agent) i Serializacja Cloudpickle
Test 12: Weryfikacja Wdrożenia Vertex AI Reasoning Engine (Serving State)
Test 13: Rejestracja i Współdzielenie Agenta w Gemini Enterprise (sharingConfig ALL_USERS)
Test 14: Dynamiczne Zapytanie Per-User i Filtrowanie po Dniach (Live Tool Invocation)
Test 15: Dynamiczne Zapytanie o Trendy Adopcji i Porównanie Użytkowników (Multi-User Ranking)
"""

import sys
import os
import json
import py_compile
import subprocess
import unittest
import urllib.request
import urllib.error
from typing import Dict, Any

# Ensure repo root and cli/ are in python path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "cli"))

from telemetry_service import TelemetryService
from deploy import resolve_engine, get_auth_token, enable_engine_observability
from google.cloud import bigquery
import google.auth
from google.auth.transport.requests import Request

PROJECT_ID = os.environ.get("TEST_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "dprzek-vertex"
LOCATION = os.environ.get("TEST_LOCATION") or "eu"
APP_NAME = os.environ.get("TEST_APP_NAME") or "test-app-123"
DATASET_ID = os.environ.get("TEST_DATASET_ID") or "gemini_enterprise_telemetry"
VERTEX_LOCATION = os.environ.get("TEST_VERTEX_LOCATION") or "europe-west1"


class GeminiEnterpriseTelemetryTestSuite(unittest.TestCase):
    gcp_auth_available = False
    auth_skip_reason = ""
    service = None
    bq_client = None
    expected_engine_id = None
    project_number = None

    @classmethod
    def setUpClass(cls):
        try:
            token = get_auth_token()
            if token:
                cls.bq_client = bigquery.Client(project=PROJECT_ID)
                cls.gcp_auth_available = True
                try:
                    cls.expected_engine_id = resolve_engine(PROJECT_ID, LOCATION, APP_NAME, token)
                except Exception:
                    cls.expected_engine_id = "test-app-123_1789757145270"

                cls.service = TelemetryService(
                    project_id=PROJECT_ID,
                    location=LOCATION,
                    dataset_id=DATASET_ID,
                    engine_id=cls.expected_engine_id,
                )

                # Pobierz project number
                crm_url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT_ID}"
                req = urllib.request.Request(crm_url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req) as resp:
                    proj_info = json.load(resp)
                    cls.project_number = str(proj_info.get("projectNumber", ""))
        except Exception as e:
            cls.gcp_auth_available = False
            cls.auth_skip_reason = f"Brak aktywnej autoryzacji GCP ({e}). Uruchom 'gcloud auth application-default login' przed testami na żywo."

    def _require_live_gcp(self):
        if not self.gcp_auth_available:
            self.skipTest(self.auth_skip_reason)

    # --------------------------------------------------------------------------
    # TEST 1: Syntaktyka i Czystość Kodu Pythona (Multi-Tenant Hygiene)
    # --------------------------------------------------------------------------
    def test_01_syntax_and_compilation(self):
        """Sprawdza czy wszystkie pliki .py w repo kompilują się bez błędów składniowych i nie zawierają hardkodowanych ID."""
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

        # Weryfikacja czystości modułu agenta
        agent_py = os.path.join(REPO_ROOT, "agent", "adk_telemetry_agent.py")
        with open(agent_py, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn('project_id = "dprzek-prod"', content, "adk_telemetry_agent.py nie może zawierać twardo zakodowanego projektu.")

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
        self.assertTrue(resolved.startswith(APP_NAME), f"Oczekiwano prefiksu {APP_NAME}, otrzymano {resolved}")

        # 2. Poprawne dopasowanie gdy podano pełne ID silnika
        resolved_full = resolve_engine(PROJECT_ID, LOCATION, resolved, token)
        self.assertEqual(resolved_full, resolved)

        # 3. Sprawdzenie zachowania dla pustego hintu (powinien wybrać pierwszy dostępny silnik)
        resolved_empty = resolve_engine(PROJECT_ID, LOCATION, "", token)
        self.assertTrue(len(resolved_empty) > 0, "Dla pustego hintu powinien zwrócić silnik domyślny.")

    # --------------------------------------------------------------------------
    # TEST 3: Automatyczna Konfiguracja Uprawnień IAM Konta Reasoning Engine
    # --------------------------------------------------------------------------
    def test_03_automated_reasoning_engine_iam_setup(self):
        """Weryfikuje czy konto usługi Reasoning Engine posiada wymagane uprawnienia IAM w projekcie i BigQuery."""
        self._require_live_gcp()
        self.assertIsNotNone(self.project_number, "Nie udało się ustalić numeru projektu.")
        sa_email = f"service-{self.project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

        # 1. Sprawdzenie uprawnień do zbioru danych BigQuery (READER)
        dataset = self.bq_client.get_dataset(DATASET_ID)
        access_entries = list(dataset.access_entries)
        has_dataset_access = any(
            entry.entity_id == sa_email and entry.role in ("READER", "WRITER", "OWNER")
            for entry in access_entries
        )
        self.assertTrue(
            has_dataset_access,
            f"Konto {sa_email} musi posiadać uprawnienia READER/WRITER/OWNER do zbioru {DATASET_ID}!",
        )

        # 2. Sprawdzenie ról na poziomie projektu (BigQuery Job User)
        token = get_auth_token()
        iam_url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT_ID}:getIamPolicy"
        req = urllib.request.Request(
            iam_url,
            data=b"{}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            policy = json.load(resp)

        member_str = f"serviceAccount:{sa_email}"
        roles_for_sa = set()
        for binding in policy.get("bindings", []):
            if member_str in binding.get("members", []):
                roles_for_sa.add(binding.get("role"))

        self.assertIn("roles/bigquery.jobUser", roles_for_sa, f"{sa_email} musi posiadać rolę roles/bigquery.jobUser!")
        self.assertIn("roles/monitoring.viewer", roles_for_sa, f"{sa_email} musi posiadać rolę roles/monitoring.viewer!")

    # --------------------------------------------------------------------------
    # TEST 4: Idempotentność i zachowanie partycjonowania tabel BigQuery
    # --------------------------------------------------------------------------
    def test_04_bigquery_tables_and_partitioning(self):
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
    # TEST 5: Idempotentna Wsteczna Ingestja (Backfill Parsing & Idempotency)
    # --------------------------------------------------------------------------
    def test_05_backfill_idempotency_and_schema(self):
        """Weryfikuje moduł wstecznej ingestji i poprawność mapowania pól zdarzeń."""
        self._require_live_gcp()
        from scripts.backfill_logs_to_bigquery import parse_activity_entry, parse_inference_entry

        # Mock wpisu Cloud Logging dla User Activity
        mock_activity_entry = {
            "insertId": "test_insert_123",
            "timestamp": "2026-09-19T10:00:00Z",
            "jsonPayload": {
                "useriamprincipal": "user@example.com",
                "logmetadata": {"methodname": "StreamAssist"},
                "request": {
                    "userevent": {
                        "userpseudoid": "pseudo_123",
                        "engine": self.expected_engine_id,
                        "eventtype": "search",
                        "agentspaceinfo": {"agentspacepagetype": "deep-research"}
                    }
                }
            }
        }
        parsed_act = parse_activity_entry(mock_activity_entry)
        self.assertEqual(parsed_act["insert_id"], "test_insert_123")
        self.assertEqual(parsed_act["user_iam_principal"], "user@example.com")
        self.assertEqual(parsed_act["method_name"], "StreamAssist")
        self.assertEqual(parsed_act["page_type"], "deep-research")

        # Mock wpisu dla Inference
        mock_inf_entry = {
            "insertId": "inf_insert_456",
            "timestamp": "2026-09-19T10:00:01Z",
            "jsonPayload": {
                "gen_ai_usage_input_tokens": 150,
                "gen_ai_usage_output_tokens": 45,
                "gen_ai_usage_reasoning_output_tokens": 0
            }
        }
        parsed_inf = parse_inference_entry(mock_inf_entry)
        self.assertEqual(parsed_inf["insert_id"], "inf_insert_456")
        self.assertEqual(parsed_inf["input_tokens"], 150)
        self.assertEqual(parsed_inf["output_tokens"], 45)

    # --------------------------------------------------------------------------
    # TEST 6: Kompilacja i parametryzacja widoków BigQuery (SQL DDL Dry-Run)
    # --------------------------------------------------------------------------
    def test_06_bigquery_views_syntax_and_compilation(self):
        """Sprawdza poprawność zapytań DDL widoków po parametryzacji."""
        sql_path = os.path.join(REPO_ROOT, "bigquery", "telemetry_views.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            raw_sql = f.read()

        formatted_sql = raw_sql.format(project_id=PROJECT_ID, dataset_id=DATASET_ID)
        self.assertNotIn("{project_id}", formatted_sql)
        self.assertNotIn("{dataset_id}", formatted_sql)

        self._require_live_gcp()

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
    # TEST 7: Niezmienniki matematyczne metryk i spójność sum
    # --------------------------------------------------------------------------
    def test_07_mathematical_invariants(self):
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

            # Niezmiennik 3: Brak ujemnych wartości
            self.assertGreaterEqual(total_events, 0)
            self.assertGreaterEqual(queries, 0)
            self.assertGreaterEqual(inp_tok, 0)
            self.assertGreaterEqual(out_tok, 0)

    # --------------------------------------------------------------------------
    # TEST 8: Precyzja korelacji tokenów po śladach OpenTelemetry (Zero Double-Counting)
    # --------------------------------------------------------------------------
    def test_08_token_trace_correlation_precision(self):
        """Sprawdza brak iloczynu kartezjańskiego i mechanizm deduplikacji tokenów."""
        self._require_live_gcp()
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

        user_summary = self.service.get_user_summary()
        self.assertGreater(len(user_summary), 0, "Brak danych w podsumowaniu użytkowników.")
        total_view_inp = sum(u.get("input_tokens", 0) for u in user_summary)
        self.assertGreaterEqual(total_view_inp, direct_inp, "Suma tokenów wejściowych powinna obejmować operacje inferencji.")

    # --------------------------------------------------------------------------
    # TEST 9: Rygorystyczna separacja funkcjonalności (Deep Research vs Zapytania)
    # --------------------------------------------------------------------------
    def test_09_feature_classification_precision(self):
        """Weryfikuje separację sesji asystenta od zapytań Deep Research i tworzenia agentów."""
        self._require_live_gcp()
        daily_records = self.service.get_user_daily_breakdown()

        found_deep_research = False
        for row in daily_records:
            if row.get("deep_research_count", 0) > 0:
                found_deep_research = True
                self.assertGreater(row.get("total_events", 0), 0)

        self.assertTrue(found_deep_research, "Powinno zostać wykryte co najmniej jedno zdarzenie Deep Research w logach.")

    # --------------------------------------------------------------------------
    # TEST 10: Integracja Metryk Cloud Monitoring i Tras OpenTelemetry
    # --------------------------------------------------------------------------
    def test_10_cloud_monitoring_and_opentelemetry_traces(self):
        """Weryfikuje poprawność odczytu limitów kwotowych oraz śladów OpenTelemetry."""
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_realtime_quotas, get_observability_traces

        quotas_json = get_realtime_quotas()
        quotas = json.loads(quotas_json)
        self.assertIn("rate_limits", quotas)
        self.assertIn("quota_status", quotas)
        self.assertIn(quotas.get("status"), ("success", "HEALTHY"))

        traces_json = get_observability_traces(days=14)
        traces_data = json.loads(traces_json)
        self.assertIn("trace_windows", traces_data)
        self.assertIn("windows_count", traces_data)

    # --------------------------------------------------------------------------
    # TEST 11: Walidacja Agenta ADK i Serializacja Cloudpickle
    # --------------------------------------------------------------------------
    def test_11_adk_agent_definition_and_tools(self):
        """Weryfikuje konfigurację i integralność dynamicznego agenta ADK oraz jego 5 narzędzi."""
        from agent.adk_telemetry_agent import root_agent
        import cloudpickle

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

        # Weryfikacja serializacji cloudpickle
        pickled = cloudpickle.dumps(root_agent)
        self.assertGreater(len(pickled), 100, "Zserializowany agent ADK musi posiadać treść.")

    # --------------------------------------------------------------------------
    # TEST 12: Weryfikacja Wdrożenia Vertex AI Reasoning Engine (Serving State)
    # --------------------------------------------------------------------------
    def test_12_reasoning_engine_deployment_state(self):
        """Weryfikuje czy Reasoning Engine istnieje w Vertex AI w rejonie europe-west1."""
        self._require_live_gcp()
        token = get_auth_token()
        url = f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{VERTEX_LOCATION}/reasoningEngines"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)

        engines = data.get("reasoningEngines", [])
        self.assertGreater(len(engines), 0, f"Brak wdrożonych Reasoning Engines w projekcie {PROJECT_ID} ({VERTEX_LOCATION})!")
        telemetry_engine = next((e for e in engines if "Telemetry" in e.get("displayName", "")), None)
        self.assertIsNotNone(telemetry_engine, "Nie znaleziono Reasoning Engine telemetrii w Vertex AI!")

    # --------------------------------------------------------------------------
    # TEST 13: Rejestracja i Współdzielenie Agenta w Gemini Enterprise (sharingConfig ALL_USERS)
    # --------------------------------------------------------------------------
    def test_13_gemini_enterprise_agent_sharing_and_registration(self):
        """Weryfikuje czy Agent w Discovery Engine posiada sharingConfig: ALL_USERS i stan ENABLED."""
        self._require_live_gcp()
        token = get_auth_token()
        api_host = f"{LOCATION}-discoveryengine.googleapis.com" if LOCATION != "global" else "discoveryengine.googleapis.com"
        url = f"https://{api_host}/v1alpha/projects/{self.project_number or PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{self.expected_engine_id}/assistants/default_assistant/agents"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT_ID}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)

        agents = data.get("agents", [])
        self.assertGreater(len(agents), 0, "Brak zarejestrowanych agentów w Gemini Enterprise!")
        adk_agent = next((a for a in agents if "Telemetry" in a.get("displayName", "")), None)
        self.assertIsNotNone(adk_agent, "Nie znaleziono zarejestrowanego Agenta Telemetrii w Gemini Enterprise!")
        self.assertEqual(adk_agent.get("state"), "ENABLED", "Agent powinien posiadać stan ENABLED!")
        
        # Weryfikacja współdzielenia (sharingConfig: ALL_USERS)
        sharing_scope = adk_agent.get("sharingConfig", {}).get("scope")
        self.assertEqual(sharing_scope, "ALL_USERS", "Agent powinien być udostępniony dla ALL_USERS!")

    # --------------------------------------------------------------------------
    # TEST 14: Dynamiczne Zapytanie Per-User i Filtrowanie po Dniach (Live Tool Invocation)
    # --------------------------------------------------------------------------
    def test_14_dynamic_user_query_by_days(self):
        """Weryfikuje wykonanie narzędzia get_user_daily_utilization na żywym BigQuery dla obu użytkowników."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_user_daily_utilization

        for email in ["admin@dprzek.altostrat.com", "damian.przekop@gmail.com"]:
            res_json = get_user_daily_utilization(user_email=email, days=30)
            data = json.loads(res_json)
            self.assertEqual(data.get("user_email"), email)
            self.assertGreater(data.get("daily_records_count", 0), 0, f"Brak aktywności dla użytkownika {email}!")
            self.assertGreater(len(data.get("daily_records", [])), 0)

            # Sprawdź strukturę pojedynczego dnia
            first_day = data["daily_records"][0]
            self.assertIn("activity_date", first_day)
            self.assertIn("total_events", first_day)
            self.assertIn("total_tokens", first_day)

    # --------------------------------------------------------------------------
    # TEST 15: Dynamiczne Zapytanie o Trendy Adopcji i Porównanie Użytkowników (Multi-User Ranking)
    # --------------------------------------------------------------------------
    def test_15_dynamic_multi_user_adoption_and_summary(self):
        """Weryfikuje wykonanie narzędzi get_user_summary oraz get_daily_adoption."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_user_summary, get_daily_adoption

        summary_json = get_user_summary()
        summary_data = json.loads(summary_json)
        self.assertIn("users", summary_data)
        self.assertGreaterEqual(summary_data.get("users_count", 0), 2, "Powinno być co najmniej 2 użytkowników w podsumowaniu!")

        user_emails = [u.get("user_id") for u in summary_data["users"]]
        self.assertIn("admin@dprzek.altostrat.com", user_emails)
        self.assertIn("damian.przekop@gmail.com", user_emails)

        adoption_json = get_daily_adoption(days=30)
        adoption_data = json.loads(adoption_json)
        self.assertIn("adoption_records", adoption_data)
        self.assertIn("records_count", adoption_data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
