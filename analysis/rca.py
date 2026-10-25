"""Root Cause Analysis (RCA) ranking.

Identifies the root cause of an incident by scoring:
1. Earliest anomaly time
2. Downstream anomalous services explained (cascade blast radius)
3. Upstream innocence (absence of failing upstream dependencies)
4. Local severity (error rate, latency, CPU, queue depth, error logs)

Produces output matching the RootCause contract in api/schemas.py.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import config as C


def _build_dependency_maps(graph: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Returns (upstream_deps, downstream_dependants).
    
    In the graph: edge source -> target means source depends on target.
    Therefore:
    - target is upstream dependency for source.
    - source is downstream dependant for target.
    """
    upstream_deps: dict[str, list[str]] = defaultdict(list)
    downstream_dependants: dict[str, list[str]] = defaultdict(list)

    for edge in graph.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            upstream_deps[src].append(tgt)
            downstream_dependants[tgt].append(src)

    return upstream_deps, downstream_dependants


def _get_reachable_downstream(
    start_service: str,
    downstream_dependants: dict[str, list[str]],
) -> set[str]:
    """Finds all downstream services reachable from start_service."""
    visited = set()
    queue = [start_service]
    while queue:
        curr = queue.pop(0)
        for dep in downstream_dependants.get(curr, []):
            if dep not in visited:
                visited.add(dep)
                queue.append(dep)
    return visited


def rank_root_causes(
    metrics_history: list[dict[str, Any]] | list[list[dict[str, Any]]],
    logs: list[dict[str, Any]] | None = None,
    graph: dict[str, Any] | None = None,
    current_ts: float | None = None,
) -> dict[str, Any]:
    """Ranks suspected root causes for any active incident.

    Args:
        metrics_history: Flat list of MetricTick dicts or list of tick-batches.
        logs: Recent log lines.
        graph: Dependency graph (nodes and edges).
        current_ts: Timestamp of current tick (defaults to max ts in metrics).

    Returns:
        Dict matching RootCauseResponse schema:
        {"ts": 1730000000, "candidates": [{"service": "...", "score": 0.91, "explanation": "..."}]}
    """
    if logs is None:
        logs = []
    if graph is None:
        graph = {"nodes": [{"id": s} for s in C.SERVICES], "edges": []}

    # Flatten metrics if nested by tick
    flat_metrics: list[dict[str, Any]] = []
    if metrics_history and isinstance(metrics_history[0], list):
        for tick_metrics in metrics_history:
            flat_metrics.extend(tick_metrics)
    else:
        flat_metrics = list(metrics_history)  # type: ignore

    if not flat_metrics:
        ts = current_ts or getattr(C, "START_TS", 1730000000)
        return {"ts": ts, "candidates": []}

    if current_ts is None:
        current_ts = max((m.get("ts", 0) for m in flat_metrics), default=getattr(C, "START_TS", 1730000000))

    # Group metrics by service sorted by timestamp
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in flat_metrics:
        by_service[m["service"]].append(m)

    for srv in by_service:
        by_service[srv].sort(key=lambda x: x.get("ts", 0))

    upstream_deps, downstream_dependants = _build_dependency_maps(graph)

    # 1. Detect anomaly onset per service
    onset_time: dict[str, float] = {}
    current_severity: dict[str, float] = {}
    anomalous_services: set[str] = set()

    for srv, records in by_service.items():
        latest = records[-1]
        err = latest.get("error_rate", 0.0)
        lat = latest.get("latency_p95_ms", 0.0)
        cpu = latest.get("cpu", 0.0)
        status = latest.get("status", "healthy")

        # Baseline latency estimate from first 3 healthy records
        baseline_lat = 50.0
        healthy_lats = [r.get("latency_p95_ms", 50.0) for r in records[:3] if r.get("status") == "healthy"]
        if healthy_lats:
            baseline_lat = sum(healthy_lats) / len(healthy_lats)

        # Calculate severity score [0, 1]
        sev = 0.0
        if status == "failed":
            sev = 1.0
        elif status == "degraded":
            sev = 0.6
        sev = max(sev, min(1.0, err * 5.0), min(1.0, max(0.0, cpu - 0.5) * 2.0))
        if lat > baseline_lat * 2.0:
            sev = max(sev, min(1.0, (lat - baseline_lat) / 1000.0))
        current_severity[srv] = sev

        # Find earliest anomaly timestamp
        for r in records:
            r_status = r.get("status", "healthy")
            r_err = r.get("error_rate", 0.0)
            r_lat = r.get("latency_p95_ms", 0.0)
            if r_status != "healthy" or r_err > 0.03 or (baseline_lat > 0 and r_lat > baseline_lat * 2.5):
                onset_time[srv] = r.get("ts", current_ts)
                anomalous_services.add(srv)
                break

    if not anomalous_services:
        # All healthy: return empty candidates
        return {"ts": current_ts, "candidates": []}

    earliest_ts = min(onset_time.values())
    max_onset_delta = max(1.0, (current_ts - earliest_ts))

    # 2. Analyze logs per service
    log_errors: dict[str, list[str]] = defaultdict(list)
    log_counts: dict[str, int] = defaultdict(int)

    for entry in logs:
        srv = entry.get("service")
        lvl = entry.get("level", "INFO")
        msg = entry.get("message", "")
        if srv:
            if lvl in ("ERROR", "WARN"):
                log_counts[srv] += (2 if lvl == "ERROR" else 1)
                if lvl == "ERROR" and len(log_errors[srv]) < 2:
                    log_errors[srv].append(msg)

    # 3. Score each anomalous candidate
    candidates: list[dict[str, Any]] = []

    for srv in anomalous_services:
        # A. Earliest anomaly factor (0.0 to 1.0; 1.0 = earliest)
        t_onset = onset_time[srv]
        earliest_score = max(0.0, 1.0 - ((t_onset - earliest_ts) / max_onset_delta))

        # B. Downstream anomalous services explained
        reachable = _get_reachable_downstream(srv, downstream_dependants)
        downstream_anomalous = reachable.intersection(anomalous_services)
        if anomalous_services - {srv}:
            explained_ratio = len(downstream_anomalous) / max(1, len(anomalous_services) - 1)
        else:
            explained_ratio = 1.0

        # C. Upstream innocence: if srv's dependencies failed BEFORE srv, srv is likely a victim
        upstream_suspects = 0
        for up in upstream_deps.get(srv, []):
            if up in anomalous_services and onset_time.get(up, float("inf")) < t_onset:
                upstream_suspects += 1
        upstream_innocence = 1.0 / (1.0 + upstream_suspects * 1.5)

        # D. Local severity and logs
        sev = current_severity.get(srv, 0.5)
        log_bonus = min(0.3, log_counts.get(srv, 0) * 0.05)

        # Combined composite score
        composite_score = (
            0.35 * earliest_score
            + 0.30 * explained_ratio
            + 0.20 * upstream_innocence
            + 0.15 * min(1.0, sev + log_bonus)
        )

        # Calibrate confidence score to [0.2, 0.98]
        final_score = round(min(0.98, max(0.20, composite_score * 0.95)), 2)

        # Compose plain-English templated explanation
        t_delta_s = int(current_ts - t_onset)
        time_desc = f"Earliest anomaly (t-{t_delta_s}s)" if t_onset == earliest_ts else f"Anomaly at t-{t_delta_s}s"
        
        downstream_desc = ""
        if downstream_anomalous:
            downstream_desc = f"{len(downstream_anomalous)} downstream services affected"
        else:
            downstream_desc = "leaf service anomaly"

        log_snippet = ""
        if log_errors.get(srv):
            clean_msg = log_errors[srv][0][:60]
            log_snippet = f'log errors: "{clean_msg}"'
        elif sev > 0.6:
            log_snippet = f"critical severity ({int(sev * 100)}%)"

        parts = [p for p in (time_desc, downstream_desc, log_snippet) if p]
        explanation = ", ".join(parts)

        candidates.append({
            "service": srv,
            "score": final_score,
            "explanation": explanation,
            "_raw_score": composite_score,
        })

    # Sort candidates by raw score descending
    candidates.sort(key=lambda c: c["_raw_score"], reverse=True)

    # Clean up internal sorting helper
    for c in candidates:
        del c["_raw_score"]

    return {
        "ts": current_ts,
        "candidates": candidates[:5],  # top-5 candidates
    }
