"""Test suite for FastAPI backend endpoints (api/main.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from starlette.testclient import TestClient

from api.main import app
from api.schemas import SystemState


class TestAPI(unittest.TestCase):
    """Verifies all FastAPI routes, mock integration, and control loop."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_get_state_matches_contract(self):
        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        validated = SystemState.model_validate(data)
        self.assertEqual(len(validated.graph.nodes), 12)
        self.assertEqual(len(validated.metrics), 12)
        self.assertIn("db-primary", validated.history.fail_prob)

    def test_control_pause_play(self):
        resp = self.client.post("/api/control", json={"action": "pause", "speed": 2.0})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["running"])
        self.assertEqual(resp.json()["speed"], 2.0)

        resp2 = self.client.post("/api/control", json={"action": "play", "speed": 1.0})
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["running"])

    def test_inject_fault_and_cascade(self):
        resp = self.client.post("/api/inject-fault", json={"service": "db-primary", "type": "slow_query"})
        self.assertEqual(resp.status_code, 200)

        state_resp = self.client.get("/api/state")
        state = state_resp.json()
        self.assertTrue(state["incident"]["active"])
        self.assertEqual(state["incident"]["fault"]["service"], "db-primary")

    def test_apply_strategy(self):
        resp = self.client.post("/api/apply-strategy", json={"strategy": "failover_to_replica", "target": "db-primary"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "applied")

    def test_reset(self):
        resp = self.client.post("/api/reset")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "reset"})

        state_resp = self.client.get("/api/state")
        state = state_resp.json()
        self.assertEqual(state["tick"], 5)  # initial baseline ticks


    def test_live_simulation_mode(self):
        """Test API when mock flags are disabled and live modules run."""
        import config as C
        orig_sim = C.MOCK_SIM
        orig_pred = C.MOCK_PREDICTOR
        orig_casc = C.MOCK_CASCADE
        orig_rca = C.MOCK_RCA
        orig_rec = C.MOCK_RECOVERY
        try:
            C.MOCK_SIM = False
            C.MOCK_PREDICTOR = False
            C.MOCK_CASCADE = False
            C.MOCK_RCA = False
            C.MOCK_RECOVERY = False

            # Reset and step live simulator
            self.client.post("/api/reset")
            self.client.post("/api/inject-fault", json={"service": "db-primary", "type": "slow_query"})

            # Query state
            resp = self.client.get("/api/state")
            self.assertEqual(resp.status_code, 200)
            state = resp.json()
            self.assertTrue(state["incident"]["active"])
            self.assertEqual(state["incident"]["fault"]["service"], "db-primary")
            self.assertGreater(len(state["predictions"]["predictions"]), 0)
        finally:
            C.MOCK_SIM = orig_sim
            C.MOCK_PREDICTOR = orig_pred
            C.MOCK_CASCADE = orig_casc
            C.MOCK_RCA = orig_rca
            C.MOCK_RECOVERY = orig_rec
            self.client.post("/api/reset")


if __name__ == "__main__":
    unittest.main()
