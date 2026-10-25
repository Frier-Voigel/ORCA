"""Test suite validating all mock files against shared schemas and ensuring consistency."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Ensure root workspace directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pydantic import TypeAdapter

from api.schemas import (
    CascadeForecast,
    Graph,
    LogLine,
    MetricTick,
    PredictionResponse,
    RecoveryResponse,
    RootCauseResponse,
    SystemState,
)
import config

MOCKS_DIR = Path(__file__).resolve().parent.parent / "mocks"
EXPECTED_SERVICES = set(config.SERVICES)
EXPECTED_TIMESTAMP = 1730000000


class TestMockContracts(unittest.TestCase):
    """Validate each mock file against its Pydantic schema and cross-contract rules."""

    def test_01_graph_mock(self):
        """Graph mock must validate and contain all 12 services."""
        path = MOCKS_DIR / "graph.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = Graph.model_validate(data)
        self.assertEqual(len(graph.nodes), 12, "Graph must contain exactly 12 service nodes")

        node_ids = {n.id for n in graph.nodes}
        self.assertEqual(node_ids, EXPECTED_SERVICES, "Graph nodes must match config.SERVICES")

        for edge in graph.edges:
            self.assertIn(edge.source, EXPECTED_SERVICES, f"Unknown source node: {edge.source}")
            self.assertIn(edge.target, EXPECTED_SERVICES, f"Unknown target node: {edge.target}")
            self.assertTrue(0.0 <= edge.weight <= 1.0, f"Weight out of bounds: {edge.weight}")
            self.assertIn(edge.kind, ("hard", "soft"), f"Invalid edge kind: {edge.kind}")

    def test_02_metrics_mock(self):
        """Metrics mock must validate for all 12 services at the expected timestamp."""
        path = MOCKS_DIR / "metrics.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        adapter = TypeAdapter(list[MetricTick])
        metrics = adapter.validate_python(data)

        self.assertEqual(len(metrics), 12, "Metrics must contain 1 row per service")
        metric_services = {m.service for m in metrics}
        self.assertEqual(metric_services, EXPECTED_SERVICES, "Metrics must cover all 12 services")

        for m in metrics:
            self.assertEqual(m.ts, EXPECTED_TIMESTAMP, f"Metric timestamp mismatch for {m.service}")
            self.assertTrue(0.0 <= m.error_rate <= 1.0)
            self.assertTrue(0.0 <= m.cpu <= 1.0)
            self.assertTrue(0.0 <= m.mem <= 1.0)
            self.assertGreaterEqual(m.queue_depth, 0)
            self.assertIn(m.status, ("healthy", "degraded", "failed"))

    def test_03_logs_mock(self):
        """Logs mock (JSON and JSONL) must validate against LogLine schema."""
        json_path = MOCKS_DIR / "logs.json"
        jsonl_path = MOCKS_DIR / "logs.jsonl"
        self.assertTrue(json_path.exists(), f"Missing mock file: {json_path}")
        self.assertTrue(jsonl_path.exists(), f"Missing mock file: {jsonl_path}")

        # Validate JSON array
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        adapter = TypeAdapter(list[LogLine])
        logs_from_json = adapter.validate_python(data)
        self.assertGreater(len(logs_from_json), 0, "logs.json should not be empty")

        for line in logs_from_json:
            self.assertIn(line.service, EXPECTED_SERVICES)
            self.assertIn(line.level, ("INFO", "WARN", "ERROR", "DEBUG"))
            self.assertTrue(len(line.message) > 0)

        # Validate JSONL line-by-line
        logs_from_jsonl = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if raw_line:
                    line_data = json.loads(raw_line)
                    logs_from_jsonl.append(LogLine.model_validate(line_data))

        self.assertEqual(len(logs_from_json), len(logs_from_jsonl), "JSON and JSONL log counts must match")

    def test_04_predictions_mock(self):
        """Predictions mock must validate and cover failure probabilities for services."""
        path = MOCKS_DIR / "predictions.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        preds = PredictionResponse.model_validate(data)
        self.assertEqual(preds.ts, EXPECTED_TIMESTAMP)
        self.assertEqual(len(preds.predictions), 12, "Predictions must cover all 12 services")

        pred_services = {p.service for p in preds.predictions}
        self.assertEqual(pred_services, EXPECTED_SERVICES)

        for p in preds.predictions:
            self.assertTrue(0.0 <= p.fail_prob <= 1.0)
            self.assertGreater(p.horizon_s, 0)
            self.assertIsInstance(p.top_signals, list)

    def test_05_cascade_mock(self):
        """Cascade mock must validate paths and blast radius."""
        path = MOCKS_DIR / "cascade.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cascade = CascadeForecast.model_validate(data)
        self.assertEqual(cascade.ts, EXPECTED_TIMESTAMP)
        self.assertGreater(len(cascade.paths), 0, "Cascade must contain predicted propagation paths")

        for path_item in cascade.paths:
            self.assertIn(path_item.from_node, EXPECTED_SERVICES)
            self.assertIn(path_item.to_node, EXPECTED_SERVICES)
            self.assertTrue(0.0 <= path_item.prob <= 1.0)
            self.assertGreaterEqual(path_item.eta_s, 0)

        # Blast radius keys must match all 12 services
        self.assertEqual(set(cascade.blast_radius.keys()), EXPECTED_SERVICES)

    def test_06_root_cause_mock(self):
        """Root cause mock must validate candidates and identify db-primary as top cause."""
        path = MOCKS_DIR / "root_cause.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rc = RootCauseResponse.model_validate(data)
        self.assertEqual(rc.ts, EXPECTED_TIMESTAMP)
        self.assertGreater(len(rc.candidates), 0)

        for c in rc.candidates:
            self.assertIn(c.service, EXPECTED_SERVICES)
            self.assertTrue(0.0 <= c.score <= 1.0)
            self.assertTrue(len(c.explanation) > 0)

        # Top candidate in the scenario should be db-primary
        self.assertEqual(rc.candidates[0].service, "db-primary")
        self.assertGreaterEqual(rc.candidates[0].score, 0.8)

    def test_07_recovery_mock(self):
        """Recovery mock must validate options against allowed strategies."""
        path = MOCKS_DIR / "recovery.json"
        self.assertTrue(path.exists(), f"Missing mock file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rec = RecoveryResponse.model_validate(data)
        self.assertGreater(len(rec.options), 0)

        recommended_count = 0
        for opt in rec.options:
            self.assertIn(opt.strategy, config.STRATEGIES, f"Strategy {opt.strategy} not in config.STRATEGIES")
            self.assertIn(opt.target, EXPECTED_SERVICES)
            self.assertGreaterEqual(opt.services_saved, 0)
            self.assertGreaterEqual(opt.est_recovery_s, 0)
            self.assertTrue(0.0 <= opt.cost <= 1.0)
            self.assertTrue(0.0 <= opt.risk <= 1.0)
            self.assertTrue(0.0 <= opt.score <= 1.0)
            self.assertTrue(len(opt.projected_health) > 0)
            if opt.recommended:
                recommended_count += 1

        self.assertEqual(recommended_count, 1, "Exactly one recovery option must be marked recommended")

    def test_08_state_mock_embeds_other_mocks(self):
        """state.json must validate against SystemState and embed the exact contents of the other mocks."""
        state_path = MOCKS_DIR / "state.json"
        self.assertTrue(state_path.exists(), f"Missing mock file: {state_path}")

        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        state = SystemState.model_validate(state_data)
        self.assertEqual(state.ts, EXPECTED_TIMESTAMP)
        self.assertEqual(state.tick, 128)
        self.assertTrue(state.running)
        self.assertTrue(state.incident.active)
        self.assertIsNotNone(state.incident.fault)
        self.assertEqual(state.incident.fault.service, "db-primary")
        self.assertEqual(state.incident.fault.type, "slow_query")
        self.assertIn(state.incident.fault.type, config.FAULT_TYPES)

        # History must contain all 12 services
        self.assertEqual(set(state.history.fail_prob.keys()), EXPECTED_SERVICES)

        # Verify embedding matches individual files
        with open(MOCKS_DIR / "graph.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["graph"], json.load(f), "state.json graph must match graph.json")

        with open(MOCKS_DIR / "metrics.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["metrics"], json.load(f), "state.json metrics must match metrics.json")

        with open(MOCKS_DIR / "logs.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["logs"], json.load(f), "state.json logs must match logs.json")

        with open(MOCKS_DIR / "predictions.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["predictions"], json.load(f), "state.json predictions must match predictions.json")

        with open(MOCKS_DIR / "cascade.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["cascade"], json.load(f), "state.json cascade must match cascade.json")

        with open(MOCKS_DIR / "root_cause.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["root_cause"], json.load(f), "state.json root_cause must match root_cause.json")

        with open(MOCKS_DIR / "recovery.json", "r", encoding="utf-8") as f:
            self.assertEqual(state_data["recovery"], json.load(f), "state.json recovery must match recovery.json")


if __name__ == "__main__":
    unittest.main()
