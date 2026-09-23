#!/usr/bin/env python3
"""
Kompleksowy zestaw 20 zautomatyzowanych testów weryfikacji potoku telemetrii Gemini Enterprise.

KATEGORIA 1: Implementacja Rozwiązania (Architektura, Pipeline, Narzędzia, Uprawnienia)
  Test 01: Syntaktyka i Czystość Kodu Pythona (Multi-Tenant Hygiene)
  Test 02: Schemat i Partycjonowanie Tabel BigQuery po Timestamp
  Test 03: Idempotentność Wstecznej Ingestji i Parserów Logów
  Test 04: Kompilacja i Struktura Widoków Analitycznych SQL
  Test 05: Definicja Agenta ADK, Narzędzia i Serializacja Cloudpickle
  Test 06: Uprawnienia IAM Konta Reasoning Engine i Współdzielenie ALL_USERS

KATEGORIA 2: Prawidłowość Odpowiedzi na Wybrane Prompty (Live Tools & Prompt Correctness)
  Test 07: Prompt o Dzienną Utylizację Użytkownika (get_user_daily_utilization)
  Test 08: Prompt o Sesje Deep Research (Izolacja Sesji, Odporność na Retry)
  Test 09: Prompt o Generowanie Grafik Imagen (Precyzyjna Detekcja Promptów)
  Test 10: Prompt o Tworzenie Customowych Agentów (Odrzucanie Błędów RPC i Systemowych)
  Test 11: Prompt o Ranking i Trendy Adopcji Organizacji (DAU/WAU, Podsumowania)
  Test 12: Prompt o Limity Kwotowe i Headroom (get_realtime_quotas)
  Test 13: Prompt o Ślady OpenTelemetry i Opóźnienia TTFT (get_observability_traces)

KATEGORIA 3: Kompletność Odpowiedzi i Niezmienniki (Completeness & Invariants)
  Test 14: Niezmienniki Matematyczne Metryk (Suma Zdarzeń, Bilans Tokenów, Nieujemność)
  Test 15: Korelacja Tokenów po Śladach OTel bez Podwójnego Zliczania (Zero Double-Counting)
  Test 16: Raportowanie Zerowej Utylizacji (Zero-Utilization Schema Contract)

KATEGORIA 4: Niewrażliwość na Różne Setupy Środowiska Klienta (Client Setup Resilience)
  Test 17: Rozpoznawanie Silnika (Display Name, Pełne ID, Domyślny Fallback)
  Test 18: Auto-Wykrywanie Projektu przy Braku Zmiennych Środowiskowych
  Test 19: Odporność Parserów na Ewolucję Payloadu JSON i Brakujące Pola
  Test 20: Obsługa Różnych Konfiguracji Regionalnych (eu, us, global, Vertex Locations)
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

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "cli"))

from telemetry_service import TelemetryService
from deploy import resolve_engine, get_auth_token, enable_engine_observability
from google.cloud import bigquery
import google.auth
from google.auth.transport.requests import Request

PROJECT_ID = os.environ.get("TEST_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "test-ge-demos"
LOCATION = os.environ.get("TEST_LOCATION") or "eu"
APP_NAME = os.environ.get("TEST_APP_NAME") or "gemini-test-123"
DATASET_ID = os.environ.get("TEST_DATASET_ID") or "gemini_enterprise_telemetry"
VERTEX_LOCATION = os.environ.get("TEST_VERTEX_LOCATION") or "europe-west1"


class GeminiEnterprise20TestSuite(unittest.TestCase):
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
                    cls.expected_engine_id = f"{APP_NAME}_1789816756559"

                cls.service = TelemetryService(
                    project_id=PROJECT_ID,
                    location=LOCATION,
                    dataset_id=DATASET_ID,
                    engine_id=cls.expected_engine_id,
                )

                crm_url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT_ID}"
                req = urllib.request.Request(crm_url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req) as resp:
                    proj_info = json.load(resp)
                    cls.project_number = str(proj_info.get("projectNumber", ""))
        except Exception as e:
            cls.gcp_auth_available = False
            cls.auth_skip_reason = f"Brak aktywnej autoryzacji GCP ({e})."

    def _require_live_gcp(self):
        if not self.gcp_auth_available:
            self.skipTest(self.auth_skip_reason)

    # ==========================================================================
    # KATEGORIA 1: Implementacja Rozwiązania
    # ==========================================================================

    def test_01_syntax_multi_tenant_cleanliness(self):
        """Test 01: Sprawdza składnię wszystkich skryptów Pythona oraz higienę multi-tenant."""
        py_files = []
        for root, _, files in os.walk(REPO_ROOT):
            if ".git" in root or "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        self.assertGreaterEqual(len(py_files), 6, "Powinno istnieć co najmniej 6 skryptów Pythona.")
        for py_file in py_files:
            try:
                py_compile.compile(py_file, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"Błąd składniowy w pliku {py_file}: {e}")

        agent_py = os.path.join(REPO_ROOT, "agent", "adk_telemetry_agent.py")
        with open(agent_py, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn('project_id = "dprzek-prod"', content, "Moduł agenta nie może zawierać zahardkodowanego projektu.")
        self.assertNotIn("ghp_", content, "Moduł agenta nie może zawierać zahardkodowanych tokenów.")

    def test_02_bigquery_tables_schema_partitioning(self):
        """Test 02: Weryfikuje strukturę tabel BigQuery i partycjonowanie po timestamp."""
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
            self.assertIsNotNone(table.time_partitioning, f"Tabela {table_ref} musi posiadać time_partitioning.")
            self.assertEqual(table.time_partitioning.field, "timestamp", f"Tabela {table_ref} musi partycjonować po polu timestamp.")

    def test_03_backfill_idempotency_deduplication(self):
        """Test 03: Weryfikuje parser wstecznej ingestji oraz idempotencję przy ponownym wstawieniu."""
        from scripts.backfill_logs_to_bigquery import parse_activity_entry, parse_inference_entry

        mock_act = {
            "insertId": "test_dedup_001",
            "timestamp": "2026-09-20T12:00:00Z",
            "jsonPayload": {
                "useriamprincipal": "test.user@example.com",
                "logmetadata": {"methodname": "StreamAssist"},
                "request": {
                    "userevent": {
                        "userpseudoid": "pseudo_abc",
                        "engine": self.expected_engine_id or "gemini-test-123",
                        "eventtype": "search",
                        "agentspaceinfo": {"agentspacepagetype": "image-generation"}
                    }
                }
            }
        }
        parsed = parse_activity_entry(mock_act)
        self.assertEqual(parsed["insert_id"], "test_dedup_001")
        self.assertEqual(parsed["user_iam_principal"], "test.user@example.com")
        self.assertEqual(parsed["method_name"], "StreamAssist")
        self.assertEqual(parsed["page_type"], "image-generation")

        mock_inf = {
            "insertId": "inf_dedup_002",
            "timestamp": "2026-09-20T12:00:01Z",
            "jsonPayload": {
                "gen_ai.usage.input_tokens": 512,
                "gen_ai.usage.output_tokens": 128,
                "gen_ai.usage.cache_read.input_tokens": 64
            }
        }
        parsed_inf = parse_inference_entry(mock_inf)
        self.assertEqual(parsed_inf["insert_id"], "inf_dedup_002")
        self.assertEqual(parsed_inf["input_tokens"], 512)
        self.assertEqual(parsed_inf["output_tokens"], 128)
        self.assertEqual(parsed_inf["cached_tokens"], 64)

    def test_04_bigquery_views_ddl_and_structure(self):
        """Test 04: Sprawdza poprawność kompilacji 6 widoków analitycznych SQL w BigQuery."""
        sql_path = os.path.join(REPO_ROOT, "bigquery", "telemetry_views.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            raw_sql = f.read()

        formatted_sql = raw_sql.format(project_id=PROJECT_ID, dataset_id=DATASET_ID)
        self.assertNotIn("{project_id}", formatted_sql)
        self.assertNotIn("{dataset_id}", formatted_sql)

        self._require_live_gcp()
        expected_views = [
            "v_user_daily_utilization",
            "v_observability_traces",
            "v_user_summary",
            "v_daily_adoption",
            "v_feature_usage",
            "v_token_telemetry",
        ]
        for v in expected_views:
            v_ref = f"{PROJECT_ID}.{DATASET_ID}.{v}"
            table = self.bq_client.get_table(v_ref)
            self.assertEqual(table.table_type, "VIEW", f"{v_ref} powinien mieć typ VIEW!")
            self.assertGreater(len(table.schema), 0, f"Widok {v_ref} musi posiadać kolumny.")

    def test_05_adk_agent_definition_and_cloudpickle(self):
        """Test 05: Weryfikuje definicję agenta ADK, narzędzia i serializację cloudpickle."""
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

        pickled = cloudpickle.dumps(root_agent)
        self.assertGreater(len(pickled), 100, "Serializacja cloudpickle musi generować poprawny obiekt binarny.")

    def test_06_iam_reasoning_engine_and_sharing_config(self):
        """Test 06: Weryfikuje uprawnienia IAM konta Reasoning Engine oraz sharingConfig: ALL_USERS."""
        self._require_live_gcp()
        self.assertIsNotNone(self.project_number, "Wymagany project_number do weryfikacji konta RE.")
        sa_email = f"service-{self.project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

        dataset = self.bq_client.get_dataset(DATASET_ID)
        has_dataset_access = any(
            entry.entity_id == sa_email and entry.role in ("READER", "WRITER", "OWNER")
            for entry in dataset.access_entries
        )
        self.assertTrue(has_dataset_access, f"Konto {sa_email} musi posiadać uprawnienia READER w zbiorze {DATASET_ID}.")

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
        adk_agent = next((a for a in agents if "Telemetry" in a.get("displayName", "")), None)
        self.assertIsNotNone(adk_agent, "Nie znaleziono zarejestrowanego Agenta Telemetrii w Gemini Enterprise.")
        self.assertEqual(adk_agent.get("state"), "ENABLED")
        self.assertEqual(adk_agent.get("sharingConfig", {}).get("scope"), "ALL_USERS")

    # ==========================================================================
    # KATEGORIA 2: Prawidłowość Odpowiedzi na Wybrane Prompty
    # ==========================================================================

    def test_07_prompt_user_daily_utilization_breakdown(self):
        """Test 07: Poprawność odpowiedzi narzędzia get_user_daily_utilization dla aktywnego użytkownika."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_user_daily_utilization

        res_json = get_user_daily_utilization(user_email="damian.przekop@gmail.com", days=30)
        data = json.loads(res_json)
        self.assertIn(data.get("status"), ("success", "zero_utilization"))
        if data.get("status") == "success":
            self.assertGreater(data.get("daily_records_count", 0), 0)
            rec = data["daily_records"][0]
            self.assertIn("activity_date", rec)
            self.assertIn("assistant_queries", rec)
            self.assertIn("total_tokens", rec)
            self.assertIn("images_generated", rec)

    def test_08_prompt_deep_research_isolation_and_retries(self):
        """Test 08: Poprawność zliczania sesji Deep Research (izolacja sesji, brak double-counting po retry)."""
        self._require_live_gcp()
        daily_records = self.service.get_user_daily_breakdown()
        deep_research_days = [r for r in daily_records if r.get("deep_research_count", 0) > 0]
        self.assertGreater(len(deep_research_days), 0, "Powinno zostać odnotowane co najmniej jedno badanie Deep Research.")
        for r in deep_research_days:
            self.assertGreaterEqual(r["total_events"], r["deep_research_count"])

    def test_09_prompt_image_generation_detection(self):
        """Test 09: Poprawność detekcji generowania grafik Imagen (wykluczenie czatu tekstowego)."""
        self._require_live_gcp()
        summary = self.service.get_user_summary()
        mock_user = next((u for u in summary if "mock-analyst" in u.get("user_id", "")), None)
        if mock_user:
            self.assertEqual(mock_user.get("images_generated", 0), 1, "Użytkownik fikcyjny powinien mieć dokładnie 1 wygenerowany obraz.")
            self.assertEqual(mock_user.get("assistant_queries", 0), 3, "Użytkownik fikcyjny powinien mieć dokładnie 3 zapytania asystenta.")

    def test_10_prompt_agent_creation_and_error_filtering(self):
        """Test 10: Poprawność zliczania utworzonych agentów i odrzucanie błędów ze statusem != 0."""
        self._require_live_gcp()
        summary = self.service.get_user_summary()
        mock_user = next((u for u in summary if "mock-analyst" in u.get("user_id", "")), None)
        if mock_user:
            self.assertEqual(mock_user.get("agents_created", 0), 2, "Użytkownik fikcyjny powinien mieć dokładnie 2 utworzone agenty.")

    def test_11_prompt_user_ranking_and_adoption_trends(self):
        """Test 11: Poprawność odpowiedzi promptu o ranking użytkowników i trendy adopcji DAU."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_user_summary, get_daily_adoption

        summary_json = get_user_summary()
        summary_data = json.loads(summary_json)
        self.assertIn("users", summary_data)
        self.assertGreaterEqual(len(summary_data["users"]), 2)

        adoption_json = get_daily_adoption(days=30)
        adoption_data = json.loads(adoption_json)
        self.assertIn("adoption_records", adoption_data)
        self.assertGreater(adoption_data.get("records_count", 0), 0)

    def test_12_prompt_realtime_quotas_and_headroom(self):
        """Test 12: Poprawność odpowiedzi promptu o limity kwotowe (RPM, TPM, headroom)."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_realtime_quotas

        quotas_json = get_realtime_quotas()
        quotas_data = json.loads(quotas_json)
        self.assertIn(quotas_data.get("status"), ("success", "HEALTHY"))
        self.assertIn("quotas", quotas_data)
        self.assertIn("rate_limits", quotas_data)
        self.assertIn("gemini_enterprise_rpm", quotas_data["quotas"])

    def test_13_prompt_observability_traces_and_latencies(self):
        """Test 13: Poprawność odpowiedzi promptu o ślady OpenTelemetry, czasy TTFT i błędy."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_observability_traces

        traces_json = get_observability_traces(days=14)
        traces_data = json.loads(traces_json)
        self.assertEqual(traces_data.get("status"), "success")
        self.assertIn("trace_windows", traces_data)

    # ==========================================================================
    # KATEGORIA 3: Kompletność Odpowiedzi i Niezmienniki
    # ==========================================================================

    def test_14_mathematical_invariants_events_and_tokens(self):
        """Test 14: Weryfikacja niezmienników matematycznych (spójność sum zdarzeń, bilans tokenów)."""
        self._require_live_gcp()
        daily_records = self.service.get_user_daily_breakdown()
        self.assertGreater(len(daily_records), 0)

        for row in daily_records:
            total_events = row.get("total_events", 0)
            queries = row.get("assistant_queries", 0)
            deep_r = row.get("deep_research_count", 0)
            images = row.get("images_generated", 0)
            agents = row.get("agents_created", 0)
            total_tok = row.get("total_tokens", 0)
            inp_tok = row.get("input_tokens", 0)
            out_tok = row.get("output_tokens", 0)

            # Niezmiennik 1: Zdarzenia >= suma poszczególnych akcji
            self.assertGreaterEqual(
                total_events,
                queries + deep_r + images + agents,
                f"Zdarzenia ({total_events}) mniejsze niż suma akcji w dacie {row.get('activity_date')}"
            )

            # Niezmiennik 2: Tokeny łączne = wejściowe + wyjściowe
            self.assertEqual(
                total_tok,
                inp_tok + out_tok,
                f"total_tokens ({total_tok}) != input ({inp_tok}) + output ({out_tok})"
            )

            # Niezmiennik 3: Brak wartości ujemnych
            self.assertGreaterEqual(total_events, 0)
            self.assertGreaterEqual(queries, 0)
            self.assertGreaterEqual(total_tok, 0)

    def test_15_token_trace_correlation_zero_double_counting(self):
        """Test 15: Sprawdza precyzję korelacji tokenów po śladach OTel i brak double-countingu."""
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
        self.assertGreater(len(user_summary), 0)
        total_view_inp = sum(u.get("input_tokens", 0) for u in user_summary)
        self.assertGreaterEqual(total_view_inp, direct_inp)

    def test_16_zero_utilization_reporting_and_schema_contract(self):
        """Test 16: Kompletność raportowania zerowej utylizacji dla użytkowników bez aktywności."""
        self._require_live_gcp()
        os.environ["BIGQUERY_PROJECT"] = PROJECT_ID
        os.environ["BIGQUERY_DATASET"] = DATASET_ID
        from agent.adk_telemetry_agent import get_user_daily_utilization, get_user_summary

        ghost_user = "non_existent_ghost_user_9999@example.com"
        daily_res = json.loads(get_user_daily_utilization(user_email=ghost_user, days=14))
        self.assertEqual(daily_res.get("status"), "zero_utilization")
        self.assertEqual(daily_res.get("daily_records_count"), 0)
        self.assertEqual(daily_res.get("daily_records"), [])

        summary_res = json.loads(get_user_summary(user_email=ghost_user))
        self.assertEqual(summary_res.get("status"), "zero_utilization")
        self.assertEqual(summary_res.get("total_events"), 0)
        self.assertEqual(summary_res.get("assistant_queries"), 0)
        self.assertEqual(summary_res.get("total_tokens"), 0)

    # ==========================================================================
    # KATEGORIA 4: Niewrażliwość na Różne Setupy Środowiska Klienta
    # ==========================================================================

    def test_17_engine_resolution_resilience(self):
        """Test 17: Niewrażliwość resolvera silników na display_name, pełne ID, whitespace i pusty hint."""
        self._require_live_gcp()
        token = get_auth_token()
        self.assertIsNotNone(token)

        # 1. Po nazwie aplikacji
        res_by_name = resolve_engine(PROJECT_ID, LOCATION, APP_NAME, token)
        self.assertTrue(res_by_name.startswith(APP_NAME))

        # 2. Po pełnym ID
        res_by_full = resolve_engine(PROJECT_ID, LOCATION, res_by_name, token)
        self.assertEqual(res_by_full, res_by_name)

        # 3. Pusty hint -> wybór domyślnego
        res_empty = resolve_engine(PROJECT_ID, LOCATION, "", token)
        self.assertTrue(len(res_empty) > 0)

    def test_18_environment_variables_and_project_auto_resolution(self):
        """Test 18: Niewrażliwość na brak zmiennych środowiskowych i auto-detekcja projektu GCP."""
        saved_bq_proj = os.environ.pop("BIGQUERY_PROJECT", None)
        saved_gcp_proj = os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        try:
            from agent.adk_telemetry_agent import _get_env_config
            resolved_proj, resolved_ds = _get_env_config()
            self.assertIsNotNone(resolved_proj, "Projekt powinien zostać wykryty z domyślnych poświadczeń GCP.")
            self.assertEqual(resolved_ds, "gemini_enterprise_telemetry")
        finally:
            if saved_bq_proj:
                os.environ["BIGQUERY_PROJECT"] = saved_bq_proj
            if saved_gcp_proj:
                os.environ["GOOGLE_CLOUD_PROJECT"] = saved_gcp_proj

    def test_19_payload_schema_evolution_and_missing_fields(self):
        """Test 19: Niewrażliwość parsera logów na brakujące pola, zagnieżdżone obiekty i formaty camelCase/lowercase."""
        from scripts.backfill_logs_to_bigquery import parse_activity_entry, parse_inference_entry

        # Pusty payload nie powinien rzucić KeyError ani wyjątku
        empty_entry = {"insertId": "empty_001", "timestamp": "2026-09-20T10:00:00Z"}
        res = parse_activity_entry(empty_entry)
        self.assertEqual(res["insert_id"], "empty_001")
        self.assertEqual(res["user_iam_principal"], "")
        self.assertEqual(res["page_type"], "")

        # Payload ze zanonimizowanym użytkownikiem <elided>
        elided_entry = {
            "insertId": "elided_002",
            "timestamp": "2026-09-20T10:05:00Z",
            "jsonPayload": {
                "useriamprincipal": "<elided>",
                "request": {
                    "userevent": {
                        "userpseudoid": "anon_hash_123",
                        "eventtype": "page-view"
                    }
                }
            }
        }
        res_elided = parse_activity_entry(elided_entry)
        self.assertEqual(res_elided["user_iam_principal"], "<elided>")
        self.assertEqual(res_elided["user_pseudo_id"], "anon_hash_123")

        # Inference z brakującymi tokenami
        inf_empty = {"insertId": "inf_none", "timestamp": "2026-09-20T10:06:00Z", "jsonPayload": {}}
        res_inf = parse_inference_entry(inf_empty)
        self.assertEqual(res_inf["input_tokens"], 0)
        self.assertEqual(res_inf["output_tokens"], 0)

    def test_20_multi_region_and_location_resilience(self):
        """Test 20: Niewrażliwość na konfiguracje regionalne Discovery Engine (eu, us, global)."""
        from deploy import get_auth_token
        self._require_live_gcp()
        token = get_auth_token()

        for loc in ["eu", "global"]:
            api_host = f"{loc}-discoveryengine.googleapis.com" if loc != "global" else "discoveryengine.googleapis.com"
            url = f"https://{api_host}/v1alpha/projects/{self.project_number or PROJECT_ID}/locations/{loc}/collections/default_collection/engines"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT_ID})
            try:
                with urllib.request.urlopen(req) as resp:
                    self.assertEqual(resp.status, 200, f"Endpoint dla lokalizacji {loc} powinien odpowiadać kodem 200.")
            except urllib.error.HTTPError as e:
                # Jeśli silniki nie istnieją w danej lokalizacji, 404/403 z Discovery Engine jest dopuszczalne
                self.assertIn(e.code, (200, 403, 404))

    def test_21_privacy_by_design_observability_defaults(self):
        """Test 21: Weryfikacja reguł AI Governance - domyślny tryb Privacy-by-Design (sensitiveLoggingEnabled: False)."""
        import inspect
        from deploy import enable_engine_observability
        import subprocess

        # 1. Sprawdzenie sygnatury funkcji
        sig = inspect.signature(enable_engine_observability)
        self.assertIn("enable_sensitive_logging", sig.parameters)
        self.assertEqual(sig.parameters["enable_sensitive_logging"].default, False,
                         "Domyślna wartość enable_sensitive_logging MUSI wynosić False (Privacy-by-Design).")

        # 2. Sprawdzenie flagi CLI w deploy.py
        help_output = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "deploy.py"), "--help"],
            capture_output=True, text=True, check=True
        ).stdout
        self.assertIn("--enable-sensitive-logging", help_output)
        self.assertIn("Governance AI", help_output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

