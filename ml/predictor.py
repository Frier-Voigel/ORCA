"""Failure Predictor for microservices.

Predicts failure probability for each service within a future horizon (default 300s).
Provides top contributing signals for explainability.
Falls back to calibrated anomaly scoring so graph colors respond smoothly from tick 0.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import config as C
from api.schemas import PredictionItem, PredictionResponse
from ml.features import extract_features

MODEL_FILE = Path(__file__).resolve().parent / "model.json"
DEFAULT_HORIZON_S = 300.0

# Calibrated signal weights representing importance for failure prediction
DEFAULT_WEIGHTS = {
    "error_excess": 14.0,
    "error_rate_w5_slope": 8.0,
    "latency_excess": 0.8,
    "latency_p95_ms_w5_slope": 0.005,
    "cpu_excess": 10.0,
    "mem_excess": 12.0,
    "queue_excess": 0.15,
    "upstream_worst_stress": 5.5,
    "upstream_degraded_count": 2.5,
    "log_error_count": 1.5,
    "log_has_timeout": 2.0,
    "log_has_slow_query": 2.0,
    "log_has_connection_pool": 2.0,
    "bias": -3.5,
}

# Mapping internal feature names to human-readable signal names
SIGNAL_NAMES = {
    "error_excess": "error_rate",
    "error_rate_w5_slope": "error_rate_trend",
    "latency_excess": "latency_p95_ms",
    "latency_p95_ms_w5_slope": "latency_spike",
    "cpu_excess": "cpu_spike",
    "mem_excess": "memory_leak",
    "queue_excess": "queue_depth",
    "upstream_worst_stress": "upstream_degraded",
    "upstream_degraded_count": "upstream_cascading",
    "log_error_count": "error_logs",
    "log_has_timeout": "upstream_timeout",
    "log_has_slow_query": "slow_queries",
    "log_has_connection_pool": "connection_pool_exhaustion",
}


def _sigmoid(x: float) -> float:
    """Standard numerically-stable logistic sigmoid."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


def load_model_weights() -> dict[str, float]:
    """Loads trained weights if available, otherwise returns calibrated defaults."""
    if MODEL_FILE.exists():
        try:
            with open(MODEL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def predict(
    metrics_history: list[dict[str, Any]] | list[list[dict[str, Any]]],
    logs: list[dict[str, Any]] | None = None,
    graph: dict[str, Any] | None = None,
    current_ts: float | None = None,
    horizon_s: float = DEFAULT_HORIZON_S,
) -> dict[str, Any]:
    """Predicts failure probability and contributing signals for all 12 services.

    Args:
        metrics_history: Historical metrics ticks.
        logs: Recent log lines.
        graph: Dependency graph.
        current_ts: Current simulation timestamp.
        horizon_s: Forecast horizon in seconds (default 300s).

    Returns:
        Dict matching PredictionResponse contract in api/schemas.py.
    """
    if logs is None:
        logs = []
    if graph is None:
        graph = {"nodes": [{"id": s} for s in C.SERVICES], "edges": []}

    # Flatten metrics to locate current timestamp
    flat_metrics: list[dict[str, Any]] = []
    if metrics_history and isinstance(metrics_history[0], list):
        for tick in metrics_history:
            flat_metrics.extend(tick)
    else:
        flat_metrics = list(metrics_history)  # type: ignore

    if current_ts is None:
        current_ts = max((m.get("ts", 0) for m in flat_metrics), default=getattr(C, "START_TS", 1730000000))

    # Extract multi-dimensional features for each service
    feature_dict = extract_features(flat_metrics, logs, graph)
    weights = load_model_weights()
    bias = weights.get("bias", -3.2)

    predictions: list[dict[str, Any]] = []

    for srv in C.SERVICES:
        feats = feature_dict.get(srv, {})
        z = bias
        signal_contributions: list[tuple[str, float]] = []

        for feat_name, weight in weights.items():
            if feat_name == "bias":
                continue
            val = feats.get(feat_name, 0.0)
            contrib = val * weight
            z += contrib

            # Track positive signal contributors
            if contrib > 0.05:
                friendly_name = SIGNAL_NAMES.get(feat_name, feat_name)
                # If signal is upstream, identify the upstream service name if possible
                if feat_name == "upstream_worst_stress":
                    # Check which upstream service is worst
                    worst_up = None
                    worst_val = 0.0
                    for edge in graph.get("edges", []):
                        if edge.get("source") == srv:
                            up = edge.get("target")
                            # check up metric
                            for m in reversed(flat_metrics):
                                if m.get("service") == up:
                                    status = m.get("status", "healthy")
                                    err = m.get("error_rate", 0.0)
                                    score = 1.0 if status == "failed" else 0.5 if status == "degraded" else err * 3.0
                                    if score > worst_val:
                                        worst_val = score
                                        worst_up = up
                                    break
                    if worst_up:
                        friendly_name = f"upstream:{worst_up}"

                signal_contributions.append((friendly_name, contrib))

        # Sort signal contributions descending
        signal_contributions.sort(key=lambda x: x[1], reverse=True)
        top_signals = [sig for sig, _ in signal_contributions[:3]]

        # Ensure top_signals is never empty
        if not top_signals:
            top_signals = ["baseline_telemetry"]

        # Calculate calibrated probability
        prob = _sigmoid(z)

        # Baseline noise dampening: if system is completely healthy, keep fail_prob < 0.05
        latest_status = "healthy"
        for m in reversed(flat_metrics):
            if m.get("service") == srv:
                latest_status = m.get("status", "healthy")
                break

        if latest_status == "failed":
            prob = max(prob, 0.95)
        elif latest_status == "degraded":
            prob = max(prob, 0.65)
        elif z < -2.0:
            prob = min(prob, 0.05)

        predictions.append({
            "service": srv,
            "fail_prob": round(float(prob), 2),
            "horizon_s": float(horizon_s),
            "top_signals": top_signals,
        })

    # Sort predictions by fail_prob descending
    predictions.sort(key=lambda p: p["fail_prob"], reverse=True)

    return {
        "ts": current_ts,
        "predictions": predictions,
    }
