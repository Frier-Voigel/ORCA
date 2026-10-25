"""Batch scenario generator + mock files.

  python -m sim.generate --n 200 --seed 42   # data/scenarios/scenario_0000/...
  python -m sim.generate --mocks             # mocks/graph.json, metrics.json, logs.jsonl, cascade.json, recovery.json
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

import config as C
from sim.simulator import Simulator

TICKS = 120  # 10 simulated minutes
NO_DB = [s for s in C.SERVICES if not s.startswith("db-") and s not in ("cache", "message-queue")]
ELIGIBLE = {  # where each fault type makes sense
    "slow_query": ["db-primary", "db-replica", "inventory", "search"],
    "bad_deploy": NO_DB,
}


def run(seed: int, ticks: int = TICKS, fault: tuple[str, str] | None = None, onset: int | None = None):
    """Run one scenario. Returns (metrics rows, log lines, ground truth)."""
    rng = random.Random(seed)
    if fault is None:
        ftype = rng.choice(C.FAULT_TYPES)
        fault = (rng.choice(ELIGIBLE.get(ftype, C.SERVICES)), ftype)
    onset = rng.randint(20, 40) if onset is None else onset
    sim = Simulator(seed=seed)
    second = None
    if rng.random() < 0.15:  # overlapping noise: a mild unrelated fault later
        other = rng.choice([s for s in C.SERVICES if s != fault[0]])
        second = (rng.randint(onset + 10, onset + 40), other, rng.choice(["cpu_spike", "memory_leak"]))
    metrics, logs = [], []
    for t in range(ticks):
        if t == onset:
            sim.inject_fault(*fault)
        if second and t == second[0]:
            sim.inject_fault(second[1], second[2])
        m, lg = sim.tick()
        metrics += m
        logs += lg
    truth = sim.ground_truth() | {"seed": seed, "ticks": ticks, "extra_fault": second}
    return metrics, logs, truth


def write_scenarios(n: int, seed: int, out: Path) -> None:
    for i in range(n):
        metrics, logs, truth = run(seed + i)
        d = out / f"scenario_{i:04d}"
        d.mkdir(parents=True, exist_ok=True)
        if pd is not None:
            pd.DataFrame(metrics).to_csv(d / "metrics.csv", index=False)
        elif metrics:
            import csv
            with open(d / "metrics.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(metrics[0].keys()))
                writer.writeheader()
                writer.writerows(metrics)
        (d / "logs.jsonl").write_text("\n".join(json.dumps(x) for x in logs), encoding="utf-8")
        (d / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"wrote {n} scenarios to {out}")


def write_mocks() -> None:
    C.MOCKS_DIR.mkdir(exist_ok=True)
    metrics, logs, truth = run(C.SEED, ticks=80, fault=("db-primary", "slow_query"), onset=20)
    dump = lambda name, obj: (C.MOCKS_DIR / name).write_text(json.dumps(obj, indent=2), encoding="utf-8")
    dump("graph.json", Simulator().graph())
    dump("metrics.json", metrics)
    (C.MOCKS_DIR / "logs.jsonl").write_text("\n".join(json.dumps(x) for x in logs), encoding="utf-8")
    dump("ground_truth.json", truth)
    ts = C.START_TS + 30 * C.TICK_SECONDS
    dump("cascade.json", {"ts": ts, "paths": [
        {"from": "db-primary", "to": "order-service", "prob": 0.85, "eta_s": 40},
        {"from": "db-primary", "to": "payment", "prob": 0.8, "eta_s": 45},
        {"from": "db-primary", "to": "inventory", "prob": 0.8, "eta_s": 45},
        {"from": "order-service", "to": "api-gateway", "prob": 0.6, "eta_s": 95},
    ], "blast_radius": {"db-primary": 5, "order-service": 1, "payment": 1, "inventory": 1}})
    dump("recovery.json", {"options": [
        {"strategy": "failover_to_replica", "target": "db-primary", "services_saved": 4, "est_recovery_s": 45,
         "cost": 0.4, "risk": 0.2, "score": 0.87, "recommended": True,
         "rationale": "Reroutes dependants to the replica, keeping 4 services alive",
         "projected_health": [0.45, 0.5, 0.7, 0.9]},
        {"strategy": "circuit_breaker_isolate", "target": "db-primary", "services_saved": 2, "est_recovery_s": 20,
         "cost": 0.2, "risk": 0.3, "score": 0.61, "recommended": False,
         "rationale": "Cuts the failing dependency fast but leaves features degraded",
         "projected_health": [0.45, 0.55, 0.6, 0.6]},
        {"strategy": "restart", "target": "db-primary", "services_saved": 1, "est_recovery_s": 120,
         "cost": 0.5, "risk": 0.6, "score": 0.32, "recommended": False,
         "rationale": "Restart does not fix a slow query and causes downtime",
         "projected_health": [0.45, 0.3, 0.4, 0.5]},
    ]})
    print(f"wrote mocks to {C.MOCKS_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--out", type=Path, default=C.DATA_DIR / "scenarios")
    ap.add_argument("--mocks", action="store_true", help="write mocks/ instead of scenarios")
    a = ap.parse_args()
    write_mocks() if a.mocks else write_scenarios(a.n, a.seed, a.out)
