"""Recovery engine checks. Run: pytest   (or: python tests/test_recovery.py)"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recovery.engine import rank
from sim.simulator import Simulator

BEST = {  # (service, fault) -> strategy a sensible operator would pick
    ("order-service", "memory_leak"): "restart",
    ("order-service", "cpu_spike"): "restart",
    ("payment", "bad_deploy"): "rollback_deploy",
    ("db-primary", "slow_query"): "failover_to_replica",
    ("db-primary", "network_partition"): "failover_to_replica",
}


def _incident(service, fault):
    sim = Simulator()
    for _ in range(20):
        sim.tick()
    sim.inject_fault(service, fault)
    for _ in range(15):
        sim.tick()
    return sim


def test_best_strategy_per_fault_type():
    for (service, fault), expected in BEST.items():
        options = rank(_incident(service, fault), service)["options"]
        assert options[0]["strategy"] == expected, (service, fault, [o["strategy"] for o in options])
        assert [o["recommended"] for o in options] == [True] + [False] * (len(options) - 1)


def test_outcomes_differ_and_contract():
    mock = json.loads((C.MOCKS_DIR / "recovery.json").read_text(encoding="utf-8"))
    options = rank(_incident("db-primary", "slow_query"), "db-primary")["options"]
    assert set(options[0]) == set(mock["options"][0])
    assert len({(o["services_saved"], o["est_recovery_s"]) for o in options}) > 2
    assert all(0 <= o["score"] <= 1 for o in options)


def test_applicability():
    names = lambda svc, fault: {o["strategy"] for o in rank(_incident(svc, fault), svc)["options"]}
    assert "failover_to_replica" not in names("order-service", "memory_leak")  # no replica
    assert "rollback_deploy" not in names("db-primary", "slow_query")  # not a bad deploy
    assert "rollback_deploy" in names("payment", "bad_deploy")


def test_no_fault_no_options_and_live_sim_untouched():
    assert rank(Simulator())["options"] == []
    sim = _incident("db-primary", "slow_query")
    before = (sim.t, dict(sim.stress), list(sim.pending))
    start = time.perf_counter()
    rank(sim, "db-primary")
    assert time.perf_counter() - start < 2.0
    assert (sim.t, dict(sim.stress), list(sim.pending)) == before  # what-ifs ran on clones


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
