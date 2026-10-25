"""Cascade forecast: independent-cascade Monte Carlo over the reversed dependency graph.

If X fails, each service that depends on X (edge D -> X) fails with prob weight * kind_factor,
after a hop delay. Seeds fail with their predicted fail_prob. Output matches the Cascade contract.
ponytail: one Bernoulli trial per edge per run; no load redistribution. Upgrade if accuracy demands.
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict

import config as C

RUNS = 300
BLAST_RUNS = 100  # per-node runs for blast radius
MIN_SEED_PROB = 0.05
MIN_PATH_PROB = 0.05
KIND_FACTOR = {"hard": 1.0, "soft": 0.7}  # same amplification the simulator uses


def _hop_s(weight: float) -> int:
    """Seconds for failure to cross an edge (simulator delay + smoothing lag)."""
    return (min(8, max(1, round(2.5 / weight))) + 2) * C.TICK_SECONDS


def _dependants(graph: dict) -> dict[str, list[tuple[str, float, int]]]:
    """target -> [(dependant, spread prob, hop seconds)]"""
    out = defaultdict(list)
    for e in graph["edges"]:
        out[e["target"]].append((e["source"], e["weight"] * KIND_FACTOR[e["kind"]], _hop_s(e["weight"])))
    return out


def _cascade(dependants, seeds: dict[str, float], rng: random.Random, edge_hits=None) -> dict[str, float]:
    """One run. Returns {service: failure time in s}. Records successful edge trials in edge_hits."""
    heap = [(0.0, s) for s, p in seeds.items() if rng.random() < p]
    heapq.heapify(heap)
    failed: dict[str, float] = {}
    while heap:
        t, svc = heapq.heappop(heap)
        if svc in failed:
            continue
        failed[svc] = t
        for dep, p, hop in dependants.get(svc, ()):
            if rng.random() < p:
                if edge_hits is not None:
                    edge_hits[(svc, dep)].append(t + hop)
                if dep not in failed:
                    heapq.heappush(heap, (t + hop, dep))
    return failed


def forecast(graph: dict, predictions: dict, runs: int = RUNS, seed: int = C.SEED) -> dict:
    """graph: Graph contract. predictions: Failure-prediction contract. Returns Cascade contract."""
    rng = random.Random(seed)
    dependants = _dependants(graph)
    seeds = {p["service"]: p["fail_prob"] for p in predictions["predictions"] if p["fail_prob"] >= MIN_SEED_PROB}

    hits: dict[tuple[str, str], list[float]] = defaultdict(list)
    for _ in range(runs):
        _cascade(dependants, seeds, rng, hits)
    paths = [
        {"from": a, "to": b, "prob": round(len(times) / runs, 2), "eta_s": round(sum(times) / len(times))}
        for (a, b), times in hits.items() if len(times) / runs >= MIN_PATH_PROB
    ]
    paths.sort(key=lambda p: (p["eta_s"], -p["prob"]))

    blast = {}
    for svc in graph["nodes"]:
        sid = svc["id"]
        total = sum(len(_cascade(dependants, {sid: 1.0}, rng)) - 1 for _ in range(BLAST_RUNS))
        if round(total / BLAST_RUNS):
            blast[sid] = round(total / BLAST_RUNS)
    return {"ts": predictions["ts"], "paths": paths, "blast_radius": blast}
