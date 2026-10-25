"""Test suite for Failure Predictor (ml/predictor.py)."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as C
from api.schemas import PredictionResponse
from ml.predictor import predict
from sim.simulator import Simulator


class TestPredictor(unittest.TestCase):
    """Verifies failure prediction contract, latency budget, and sensitivity."""

    def test_healthy_system_low_failure_probability(self):
        sim = Simulator(seed=42)
        history = []
        logs = []
        for _ in range(5):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        res = predict(history, logs, sim.graph())
        validated = PredictionResponse.model_validate(res)

        self.assertEqual(len(validated.predictions), 12, "Must predict for all 12 services")
        for p in validated.predictions:
            self.assertLessEqual(p.fail_prob, 0.25, f"{p.service} fail_prob too high in healthy system: {p.fail_prob}")
            self.assertGreater(len(p.top_signals), 0)

    def test_fault_injection_elevates_probability(self):
        sim = Simulator(seed=42)
        history = []
        logs = []
        for _ in range(3):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        sim.inject_fault("db-primary", "slow_query")
        for _ in range(12):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        res = predict(history, logs, sim.graph())
        validated = PredictionResponse.model_validate(res)

        pred_map = {p.service: p for p in validated.predictions}
        # db-primary should have high probability
        self.assertGreaterEqual(pred_map["db-primary"].fail_prob, 0.70)
        # downstream order-service or payment should also be elevated
        downstream_elevated = (
            pred_map["order-service"].fail_prob >= 0.50
            or pred_map["payment"].fail_prob >= 0.50
        )
        self.assertTrue(downstream_elevated, "Downstream dependants should show elevated risk")

    def test_prediction_latency_budget(self):
        sim = Simulator(seed=42)
        history = []
        logs = []
        for _ in range(15):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        start = time.perf_counter()
        res = predict(history, logs, sim.graph())
        duration_ms = (time.perf_counter() - start) * 1000.0

        print(f"Predictor latency: {duration_ms:.2f} ms")
        self.assertLess(duration_ms, 100.0, f"Predictor took {duration_ms:.2f} ms, budget is 100 ms")


if __name__ == "__main__":
    unittest.main()
