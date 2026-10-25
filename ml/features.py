"""Feature extraction for microservice failure prediction.

Extracts:
1. Rolling-window metric features (1, 5, 15 ticks): mean, max, slope
2. Log features: WARN/ERROR counts, error templates
3. Graph features: upstream/downstream neighbor health and degraded count
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

import config as C

# Regex patterns for identifying incident log types
LOG_TEMPLATES = {
    "timeout": re.compile(r"timeout|timed out|deadline exceeded", re.IGNORECASE),
    "slow_query": re.compile(r"slow query|query exceeded|execution time", re.IGNORECASE),
    "connection_pool": re.compile(r"connection pool|pool exhausted|max connections", re.IGNORECASE),
    "memory_error": re.compile(r"memory leak|out of memory|oom|heap", re.IGNORECASE),
    "http_error": re.compile(r"50[0-4]|gateway timeout|bad gateway", re.IGNORECASE),
    "retry_storm": re.compile(r"retry|retrying|backoff", re.IGNORECASE),
}

METRIC_FIELDS = ("error_rate", "latency_p95_ms", "cpu", "mem", "queue_depth")
WINDOWS = (1, 5, 15)


def _slope(values: list[float]) -> float:
    """Computes linear trend slope over a series."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    numer = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    return numer / denom if denom > 0 else 0.0


def extract_features_for_service(
    service: str,
    history: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    graph: dict[str, Any],
    all_latest_metrics: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Extracts a flat feature dictionary for a single service."""
    feats: dict[str, float] = {}

    # Extract time series of metric values for this service (oldest to newest)
    srv_history = [m for m in history if m.get("service") == service]
    srv_history.sort(key=lambda m: m.get("ts", 0))

    # 1. Rolling window metric features
    for field in METRIC_FIELDS:
        all_vals = [float(m.get(field, 0.0)) for m in srv_history]

        for w in WINDOWS:
            w_vals = all_vals[-w:] if len(all_vals) >= w else all_vals
            if not w_vals:
                w_vals = [0.0]

            feats[f"{field}_w{w}_mean"] = sum(w_vals) / len(w_vals)
            feats[f"{field}_w{w}_max"] = max(w_vals)
            feats[f"{field}_w{w}_slope"] = _slope(w_vals)

    # Anomaly excess metrics (non-zero only when exceeding normal operational thresholds)
    latest_cpu = float(srv_history[-1].get("cpu", 0.0)) if srv_history else 0.0
    latest_mem = float(srv_history[-1].get("mem", 0.0)) if srv_history else 0.0
    latest_err = float(srv_history[-1].get("error_rate", 0.0)) if srv_history else 0.0
    latest_lat = float(srv_history[-1].get("latency_p95_ms", 0.0)) if srv_history else 0.0
    latest_queue = float(srv_history[-1].get("queue_depth", 0.0)) if srv_history else 0.0

    feats["cpu_excess"] = max(0.0, latest_cpu - 0.65)
    feats["mem_excess"] = max(0.0, latest_mem - 0.70)
    feats["error_excess"] = max(0.0, latest_err - 0.02)
    feats["latency_excess"] = max(0.0, (latest_lat - 150.0) / 100.0) if latest_lat > 150.0 else 0.0
    feats["queue_excess"] = max(0.0, latest_queue - 25.0)

    # 2. Log features
    srv_logs = [l for l in logs if l.get("service") == service]
    warn_count = sum(1 for l in srv_logs if l.get("level") == "WARN")
    error_count = sum(1 for l in srv_logs if l.get("level") == "ERROR")
    feats["log_warn_count"] = float(warn_count)
    feats["log_error_count"] = float(error_count)

    for template_name, regex in LOG_TEMPLATES.items():
        matched = any(regex.search(l.get("message", "")) for l in srv_logs)
        feats[f"log_has_{template_name}"] = 1.0 if matched else 0.0

    # 3. Graph features
    upstream_deps: list[str] = []
    downstream_dependants: list[str] = []

    for edge in graph.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")
        if src == service and tgt:
            upstream_deps.append(tgt)
        elif tgt == service and src:
            downstream_dependants.append(src)

    # Health of upstream dependencies (what service depends on)
    up_stresses: list[float] = []
    degraded_upstreams: int = 0
    for up in upstream_deps:
        up_metric = all_latest_metrics.get(up, {})
        status = up_metric.get("status", "healthy")
        err = up_metric.get("error_rate", 0.0)
        cpu = up_metric.get("cpu", 0.0)
        stress = (1.0 if status == "failed" else 0.6 if status == "degraded" else 0.0)
        stress = max(stress, err * 3.0, (cpu - 0.5) * 2.0 if cpu > 0.5 else 0.0)
        up_stresses.append(min(1.0, stress))
        if status in ("degraded", "failed") or err > 0.03:
            degraded_upstreams += 1

    feats["upstream_count"] = float(len(upstream_deps))
    feats["upstream_worst_stress"] = max(up_stresses) if up_stresses else 0.0
    feats["upstream_mean_stress"] = (sum(up_stresses) / len(up_stresses)) if up_stresses else 0.0
    feats["upstream_degraded_count"] = float(degraded_upstreams)

    # Health of downstream dependants (services that depend on this service)
    down_stresses: list[float] = []
    for down in downstream_dependants:
        down_metric = all_latest_metrics.get(down, {})
        status = down_metric.get("status", "healthy")
        err = down_metric.get("error_rate", 0.0)
        stress = (1.0 if status == "failed" else 0.6 if status == "degraded" else 0.0)
        stress = max(stress, err * 3.0)
        down_stresses.append(min(1.0, stress))

    feats["downstream_count"] = float(len(downstream_dependants))
    feats["downstream_worst_stress"] = max(down_stresses) if down_stresses else 0.0
    feats["downstream_mean_stress"] = (sum(down_stresses) / len(down_stresses)) if down_stresses else 0.0

    return feats


def extract_features(
    history: list[dict[str, Any]] | list[list[dict[str, Any]]],
    logs: list[dict[str, Any]] | None = None,
    graph: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]]:
    """Extracts features for all 12 services in config.SERVICES."""
    if logs is None:
        logs = []
    if graph is None:
        graph = {"nodes": [{"id": s} for s in C.SERVICES], "edges": []}

    # Flatten history if needed
    flat_history: list[dict[str, Any]] = []
    if history and isinstance(history[0], list):
        for tick in history:
            flat_history.extend(tick)
    else:
        flat_history = list(history)  # type: ignore

    # Get latest metrics per service
    all_latest: dict[str, dict[str, Any]] = {}
    for m in flat_history:
        srv = m.get("service")
        if srv:
            all_latest[srv] = m

    return {
        srv: extract_features_for_service(srv, flat_history, logs, graph, all_latest)
        for srv in C.SERVICES
    }
