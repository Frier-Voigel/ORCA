"""Simulator checks. Run: pytest   (or without pytest: python tests/test_sim.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from sim.generate import run
from sim.simulator import Simulator


def _run_cascade(strategy=None, ticks=70):
    sim = Simulator()
    for _ in range(20):
        sim.tick()
    sim.inject_fault("db-primary", "slow_query")
    if strategy:
        sim.apply_strategy(*strategy)
    for _ in range(ticks):
        sim.tick()
    return sim


def test_cascade_reaches_gateway():
    truth = _run_cascade().ground_truth()
    assert truth["root_cause"] == "db-primary" and truth["fault_type"] == "slow_query"
    for svc in ("order-service", "payment", "api-gateway"):
        assert svc in truth["failure_times"], svc
    ft = truth["failure_times"]
    assert ft["db-primary"] < ft["order-service"] < ft["api-gateway"]  # spreads upstream, in order


def test_healthy_system_stays_healthy():
    sim = Simulator()
    for _ in range(100):
        sim.tick()
    assert sim.system_health() > 0.95 and not sim.ground_truth()["affected_services"]


def test_deterministic_and_clone():
    a, b = _run_cascade(), _run_cascade()
    assert a.stress == b.stress
    c = a.clone()
    for _ in range(10):
        a.tick(), c.tick()
    assert a.stress == c.stress  # clone replays identically
    c.apply_strategy("failover_to_replica", "db-primary")
    for _ in range(40):
        c.tick()
    assert a.stress != c.stress  # ...and is independent


def test_strategies_differ():
    base = _run_cascade().system_health()
    failover = _run_cascade(("failover_to_replica", "db-primary")).system_health()
    restart = _run_cascade(("restart", "db-primary")).system_health()  # restart can't fix slow_query
    assert failover > base + 0.2 and failover > restart


def test_matching_fix_recovers():
    sim = Simulator()
    sim.inject_fault("payment", "bad_deploy")
    sim.apply_strategy("rollback_deploy", "payment")
    for _ in range(40):
        sim.tick()
    assert sim.status["payment"] == "healthy"


def test_contract_shapes():
    sim = Simulator()
    metrics, logs = sim.tick()
    assert len(metrics) == len(C.SERVICES)
    assert set(metrics[0]) == {"ts", "service", "latency_p95_ms", "error_rate", "cpu", "mem", "queue_depth", "status"}
    g = sim.graph()
    assert len(g["nodes"]) == 12 and all(0 <= e["weight"] <= 1 for e in g["edges"])
    for fault in C.FAULT_TYPES:  # every fault type runs and is labelled
        _, _, truth = run(1, fault=("order-service", fault), onset=10)
        assert truth["root_cause"] == "order-service" and truth["fault_type"] == fault


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
