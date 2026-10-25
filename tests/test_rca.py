"""Test suite for Root Cause Analysis (analysis/rca.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from analysis.rca import rank_root_causes
from api.schemas import RootCauseResponse
from sim.simulator import Simulator


class TestRCA(unittest.TestCase):
    """Verifies Root Cause Analysis against simulator ground truth."""

    def test_healthy_state_has_no_candidates(self):
        sim = Simulator(seed=123)
        history = []
        logs = []
        for _ in range(5):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        res = rank_root_causes(history, logs, sim.graph())
        validated = RootCauseResponse.model_validate(res)
        self.assertEqual(len(validated.candidates), 0, "Healthy system should have no root cause candidates")

    def test_root_cause_accuracy_db_primary(self):
        sim = Simulator(seed=42)
        # Run baseline
        history = []
        logs = []
        for _ in range(4):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        # Inject fault
        sim.inject_fault("db-primary", "slow_query")
        for _ in range(12):
            m, l = sim.tick()
            history.append(m)
            logs.extend(l)

        truth = sim.ground_truth()
        res = rank_root_causes(history, logs, sim.graph())
        validated = RootCauseResponse.model_validate(res)

        self.assertGreater(len(validated.candidates), 0, "RCA must return candidates when fault is active")
        top_candidate = validated.candidates[0]
        self.assertEqual(top_candidate.service, truth["root_cause"], f"Expected {truth['root_cause']}, got {top_candidate.service}")
        self.assertGreaterEqual(top_candidate.score, 0.70)
        self.assertTrue(len(top_candidate.explanation) > 0)

    def test_root_cause_accuracy_other_faults(self):
        test_cases = [
            ("payment", "memory_leak"),
            ("order-service", "bad_deploy"),
            ("api-gateway", "cpu_spike"),
        ]
        for srv, fault in test_cases:
            sim = Simulator(seed=99)
            history = []
            logs = []
            for _ in range(3):
                m, l = sim.tick()
                history.append(m)
                logs.extend(l)

            sim.inject_fault(srv, fault)
            for _ in range(10):
                m, l = sim.tick()
                history.append(m)
                logs.extend(l)

            res = rank_root_causes(history, logs, sim.graph())
            validated = RootCauseResponse.model_validate(res)
            self.assertGreater(len(validated.candidates), 0)
            candidate_services = [c.service for c in validated.candidates[:3]]
            self.assertIn(srv, candidate_services, f"True root cause {srv} must be in top 3 candidates: {candidate_services}")


if __name__ == "__main__":
    unittest.main()
