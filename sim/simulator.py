"""Microservice failure simulator (plan.md Section 2.7).

Model: every service has a stress in [0, 1]. Stress comes from its own injected fault (ramped)
or from dependencies' stress, delayed by edge weight, gated by a per-run coin flip per edge,
then smoothed. Metrics/logs/status are derived from stress.
ponytail: no queueing model; stress is a scalar. Upgrade to per-resource state if realism matters.
"""
from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

import config as C

MAXD = 8  # longest propagation delay in ticks
SMOOTH = 0.4  # stress moves 40% of the way to its target each tick
FAULT_RAMP = {"memory_leak": 40, "slow_query": 6, "network_partition": 2, "bad_deploy": 1, "cpu_spike": 3}
# extra metric pressure a fault puts on its own service: lat, err, cpu, mem, q multipliers
FAULT_SIG = {
    "memory_leak": {"mem": 0.45, "lat": 0.3},
    "slow_query": {"lat": 1.0, "q": 0.6},
    "network_partition": {"err": 0.6, "lat": 0.5},
    "bad_deploy": {"err": 0.8},
    "cpu_spike": {"cpu": 0.55, "lat": 0.4},
}
FAULT_LOGS = {  # (min own severity, level, template)
    "memory_leak": [(0.1, "WARN", "heap usage at {mem}% and rising"), (0.7, "ERROR", "OutOfMemoryError: Java heap space")],
    "slow_query": [(0.1, "WARN", "connection pool wait time {lat}ms"), (0.3, "ERROR", "query exceeded 2000ms: slow query on orders table")],
    "network_partition": [(0.3, "ERROR", "connection refused: network unreachable"), (0.3, "WARN", "packet loss detected on interface eth0")],
    "bad_deploy": [(0.3, "ERROR", "unhandled exception in handler v2.4.1: NullPointerException"), (0.3, "ERROR", "HTTP 500 after release v2.4.1")],
    "cpu_spike": [(0.1, "WARN", "CPU throttling detected ({cpu}%)"), (0.5, "ERROR", "request queue saturated, dropping requests")],
}
SCALE_OWN = {"cpu_spike": 0.6, "memory_leak": 0.8}  # scale_out only helps load-type faults
ISOLATED_FLOOR = 0.35  # dependants of a circuit-broken service lose features (degraded)
STRATEGY_DELAY = {  # ticks until a strategy takes effect
    "restart": 4, "scale_out": 3, "failover_to_replica": 3,
    "circuit_breaker_isolate": 1, "rollback_deploy": 3, "shed_load": 1,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class Simulator:
    def __init__(self, seed: int = C.SEED, graph_path=C.GRAPH_PATH):
        self.seed = seed
        gp = Path(graph_path)
        if yaml is not None and gp.exists():
            with open(gp, encoding="utf-8") as f:
                spec = yaml.safe_load(f)
        else:
            json_gp = gp.with_suffix(".json")
            if json_gp.exists():
                with open(json_gp, encoding="utf-8") as f:
                    spec = json.load(f)
            elif gp.exists():
                raise ModuleNotFoundError("PyYAML is required to parse .yaml files. Install pyyaml or provide .json.")
            else:
                raise FileNotFoundError(f"Graph file not found: {gp}")
        self.nodes: dict = spec["nodes"]
        self.edges = [
            {"source": s, "target": t, "weight": w, "kind": k} for s, t, w, k in spec["edges"]
        ]
        self.reset()

    # ---- lifecycle -------------------------------------------------------------------
    def reset(self) -> None:
        self.rng = random.Random(self.seed)
        self.t = 0
        self.stress = {s: 0.0 for s in self.nodes}
        self.hist = {s: [0.0] * MAXD for s in self.nodes}
        self.status = {s: "healthy" for s in self.nodes}
        self.faults: dict[str, dict] = {}
        self.own_mult = {s: 1.0 for s in self.nodes}
        self.out_mult = {s: 1.0 for s in self.nodes}
        self.isolated: set[str] = set()
        self.pending: list[tuple[int, str, str]] = []
        self.first_degraded: dict[str, int] = {}
        self.first_failed: dict[str, int] = {}
        self.first_fault: dict | None = None
        self.deps: dict[str, list[dict]] = {s: [] for s in self.nodes}
        for e in self.edges:
            e["delay"] = min(MAXD, max(1, round(2.5 / e["weight"])))
            e["gate"] = self.rng.random() < (0.85 if e["kind"] == "hard" else 0.5)
            self.deps[e["source"]].append(e)

    def clone(self) -> "Simulator":
        """Independent deep copy including RNG state (strategy what-ifs stay deterministic)."""
        return copy.deepcopy(self)

    # ---- inputs ----------------------------------------------------------------------
    def inject_fault(self, service: str, fault_type: str) -> None:
        if service not in self.nodes:
            raise ValueError(f"unknown service {service!r}")
        if fault_type not in C.FAULT_TYPES:
            raise ValueError(f"unknown fault type {fault_type!r}")
        self.faults[service] = {"type": fault_type, "onset": self.t}
        if self.first_fault is None:
            self.first_fault = {"service": service, "type": fault_type, "tick": self.t}

    def apply_strategy(self, strategy: str, target: str) -> None:
        if strategy not in C.STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        if target not in self.nodes:
            raise ValueError(f"unknown service {target!r}")
        self.pending.append((self.t + STRATEGY_DELAY[strategy], strategy, target))

    def _do(self, strategy: str, tgt: str) -> None:
        fault = self.faults.get(tgt)
        ftype = fault["type"] if fault else None
        if strategy == "restart":
            if ftype in ("memory_leak", "cpu_spike"):
                del self.faults[tgt]  # clears leaked/runaway state
            else:
                self.own_mult[tgt] *= 0.9  # the cause survives a restart
        elif strategy == "scale_out":
            self.own_mult[tgt] *= SCALE_OWN.get(ftype, 1.0)
            self.out_mult[tgt] *= 0.85
        elif strategy == "failover_to_replica":
            if self.nodes[tgt].get("replica"):  # dependants stop leaning on the target
                self.out_mult[tgt] *= 0.1
        elif strategy == "circuit_breaker_isolate":
            self.out_mult[tgt] *= 0.25
            self.isolated.add(tgt)
        elif strategy == "rollback_deploy":
            if ftype == "bad_deploy":
                del self.faults[tgt]
        elif strategy == "shed_load":
            self.own_mult[tgt] *= 0.85
            self.out_mult[tgt] *= 0.9

    # ---- stepping --------------------------------------------------------------------
    def _own(self, s: str) -> float:
        f = self.faults.get(s)
        if not f:
            return 0.0
        ramp = FAULT_RAMP[f["type"]]
        return _clamp((self.t - f["onset"] + 1) / ramp) * self.own_mult[s]

    def tick(self) -> tuple[list[dict], list[dict]]:
        """Advance one tick (5 simulated seconds). Returns (metrics rows, log lines)."""
        due = [p for p in self.pending if p[0] <= self.t]
        self.pending = [p for p in self.pending if p[0] > self.t]
        for _, strategy, tgt in due:
            self._do(strategy, tgt)

        ts = C.START_TS + self.t * C.TICK_SECONDS
        load = 1 + 0.2 * math.sin(2 * math.pi * self.t / 360)  # daily-ish wave
        new, laggards = {}, {}
        for s in self.nodes:
            prop, blamed = 0.0, []
            for e in self.deps[s]:
                iso = e["kind"] == "hard" and e["target"] in self.isolated
                if not e["gate"] and not iso:
                    continue
                lagged = self.hist[e["target"]][-e["delay"]]
                amp = 1.0 if e["kind"] == "hard" else 0.7
                p = min(1.0, e["weight"] * amp * self.out_mult[e["target"]] * lagged) if e["gate"] else 0.0
                if iso:
                    p = max(p, ISOLATED_FLOOR)
                prop = max(prop, p)
                if lagged >= 0.3:
                    blamed.append(e["target"])
            target = max(self._own(s), prop)
            new[s] = self.stress[s] + SMOOTH * (target - self.stress[s])
            laggards[s] = blamed

        metrics, logs = [], []
        for s, st in new.items():
            self.stress[s] = st
            self.hist[s].append(st)
            self.hist[s].pop(0)
            status = "failed" if st >= C.FAILED_AT else "degraded" if st >= C.DEGRADED_AT else "healthy"
            self.status[s] = status
            if status != "healthy":
                self.first_degraded.setdefault(s, ts)
            if status == "failed":
                self.first_failed.setdefault(s, ts)
            row = self._metrics(s, st, ts, load, status)
            metrics.append(row)
            logs.extend(self._logs(s, st, ts, row, laggards[s]))
        self.t += 1
        return metrics, logs

    def _metrics(self, s: str, st: float, ts: int, load: float, status: str) -> dict:
        n, g, own = self.nodes[s], self.rng.gauss, self._own(s)
        sig = FAULT_SIG[self.faults[s]["type"]] if s in self.faults else {}
        lat = n["lat"] * load * (1 + 8 * st**1.5 + 6 * sig.get("lat", 0) * own) * g(1, 0.05)
        err = 0.002 + 0.6 * st**1.2 + 0.4 * sig.get("err", 0) * own + abs(g(0, 0.001))
        cpu = (n["cpu"] * load + 0.5 * st + sig.get("cpu", 0) * own) * g(1, 0.03)
        mem = n["mem"] + 0.2 * st + sig.get("mem", 0) * own + g(0, 0.005)
        queue = n["q"] * load * (1 + 30 * st**2) * (1 + 4 * sig.get("q", 0) * own) * g(1, 0.08)
        return {
            "ts": ts, "service": s, "latency_p95_ms": round(max(1.0, lat), 1),
            "error_rate": round(_clamp(err), 4), "cpu": round(_clamp(cpu), 3),
            "mem": round(_clamp(mem), 3), "queue_depth": max(0, round(queue)), "status": status,
        }

    def _logs(self, s: str, st: float, ts: int, row: dict, blamed: list[str]) -> list[dict]:
        def line(level: str, msg: str) -> dict:
            return {"ts": ts, "service": s, "level": level, "message": msg}

        out, r = [], self.rng.random
        own = self._own(s)
        if s in self.faults:
            for min_sev, level, tmpl in FAULT_LOGS[self.faults[s]["type"]]:
                if own >= min_sev and r() < 0.6:
                    out.append(line(level, tmpl.format(
                        mem=round(row["mem"] * 100), lat=round(row["latency_p95_ms"]), cpu=round(row["cpu"] * 100))))
        for dep in blamed:
            if r() < 0.5:
                if st >= C.DEGRADED_AT:
                    out.append(line("ERROR", f"timeout calling {dep} after 3000ms"))
                    if r() < 0.5:  # retry storm
                        out.append(line("WARN", f"retrying request to {dep} (attempt {self.rng.randint(2, 3)}/3)"))
                else:
                    out.append(line("WARN", f"slow response from {dep} ({self.rng.randint(800, 2500)}ms)"))
        if not out and st < 0.15 and r() < 0.08:
            msg = f"request completed in {round(row['latency_p95_ms'])}ms (200)" if r() < 0.7 else "health check ok"
            out.append(line("INFO", msg))
        return out

    # ---- outputs ---------------------------------------------------------------------
    def system_health(self) -> float:
        """Criticality-weighted share of healthy capacity, 1.0 = all good."""
        tot = sum(n["criticality"] for n in self.nodes.values())
        return round(sum(n["criticality"] * (1 - self.stress[s]) for s, n in self.nodes.items()) / tot, 4)

    def ground_truth(self) -> dict:
        f = self.first_fault
        return {
            "root_cause": f["service"] if f else None,
            "fault_type": f["type"] if f else None,
            "onset_ts": C.START_TS + f["tick"] * C.TICK_SECONDS if f else None,
            "affected_services": sorted(self.first_degraded),
            "failure_times": dict(self.first_failed),
        }

    def graph(self) -> dict:
        return {
            "nodes": [{"id": s, "type": n["type"], "criticality": n["criticality"]} for s, n in self.nodes.items()],
            "edges": [{k: e[k] for k in ("source", "target", "weight", "kind")} for e in self.edges],
        }
