"""Recovery engine: simulate every applicable strategy on a clone of the live simulator and rank them.

ponytail: reads the fault type from the simulator (a diagnosis oracle); a real system would infer it
from logs/RCA. Weights live in strategies.yaml so the UI can show them.
"""
from __future__ import annotations

import json
try:
    import yaml
except ImportError:
    yaml = None

import config as C
from sim.simulator import Simulator

STRATEGY_FILE = C.ROOT / "recovery" / "strategies.yaml"
HORIZON = 40  # ticks to fast-forward each what-if (200 simulated seconds)
SAMPLE_EVERY = 8


def load_catalogue() -> dict:
    if yaml is not None and STRATEGY_FILE.exists():
        with open(STRATEGY_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f)
    json_path = STRATEGY_FILE.with_suffix(".json")
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    if STRATEGY_FILE.exists():
        raise ModuleNotFoundError("PyYAML is required to parse .yaml files. Install pyyaml or provide .json.")
    raise FileNotFoundError(f"Neither {STRATEGY_FILE} nor {json_path} could be loaded")


def _applicable(spec: dict, sim: Simulator, target: str) -> bool:
    fault = sim.faults.get(target)
    if spec["applies_to"] != "any" and (not fault or fault["type"] not in spec["applies_to"]):
        return False
    return not (spec.get("requires_replica") and not sim.nodes[target].get("replica"))


def _simulate(sim: Simulator, strategy: str | None, target: str, horizon: int) -> dict:
    """Run a clone forward. Returns failed services at the end, health curve, stable time (s)."""
    run = sim.clone()
    if strategy:
        run.apply_strategy(strategy, target)
    health, failed_by_tick = [run.system_health()], []
    for _ in range(horizon):
        run.tick()
        health.append(run.system_health())
        failed_by_tick.append({s for s, st in run.status.items() if st == "failed"})
    stable = horizon  # first tick after which no service other than the target is failed
    while stable > 0 and not (failed_by_tick[stable - 1] - {target}):
        stable -= 1
    return {"failed": failed_by_tick[-1], "health": health, "stable_s": stable * C.TICK_SECONDS}


def rank(sim: Simulator, target: str | None = None, horizon: int = HORIZON) -> dict:
    """Recovery contract. target = root-cause service (from RCA); defaults to the first injected fault."""
    target = target or (sim.first_fault or {}).get("service")
    if not target or not sim.faults:
        return {"options": []}
    cat = load_catalogue()
    w = cat["weights"]
    base = _simulate(sim, None, target, horizon)
    horizon_s = horizon * C.TICK_SECONDS

    options = []
    for name, spec in cat["strategies"].items():
        if not _applicable(spec, sim, target):
            continue
        out = _simulate(sim, name, target, horizon)
        saved = max(0, len(base["failed"]) - len(out["failed"]))
        score = (
            w["services_saved"] * (saved / max(1, len(base["failed"])))
            + w["health"] * out["health"][-1]
            + w["speed"] * (1 - out["stable_s"] / horizon_s)
            + w["low_cost"] * (1 - spec["cost"])
            + w["low_risk"] * (1 - spec["risk"])
        )
        stable = "stable in ~%ds" % out["stable_s"] if out["stable_s"] < horizon_s else "not stable within %ds" % horizon_s
        options.append({
            "strategy": name, "target": target, "services_saved": saved,
            "est_recovery_s": out["stable_s"], "cost": spec["cost"], "risk": spec["risk"],
            "score": round(score, 2), "recommended": False,
            "rationale": f"{spec['description']}; saves {saved} of {len(base['failed'])} failing services, {stable}",
            "projected_health": [round(h, 2) for h in out["health"][::SAMPLE_EVERY]],
        })
    options.sort(key=lambda o: -o["score"])
    if options:
        options[0]["recommended"] = True
    return {"options": options}
