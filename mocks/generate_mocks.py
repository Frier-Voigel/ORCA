"""Script to generate consistent, validated mock JSON files for Phase 0."""

from __future__ import annotations

import json
from pathlib import Path

from api.schemas import (
    CascadeForecast,
    CascadePath,
    Graph,
    IncidentState,
    FaultInfo,
    LogLine,
    MetricTick,
    Node,
    Edge,
    PredictionItem,
    PredictionResponse,
    RecoveryOption,
    RecoveryResponse,
    RootCauseCandidate,
    RootCauseResponse,
    StateHistory,
    SystemState,
)
import config

MOCKS_DIR = Path(__file__).resolve().parent
TIMESTAMP = 1730000000


def generate():
    MOCKS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Graph (12 services)
    nodes = [
        Node(id="api-gateway", type="gateway", criticality=1.0),
        Node(id="auth", type="service", criticality=0.8),
        Node(id="user-service", type="service", criticality=0.7),
        Node(id="order-service", type="service", criticality=0.9),
        Node(id="payment", type="service", criticality=0.9),
        Node(id="inventory", type="service", criticality=0.8),
        Node(id="db-primary", type="database", criticality=0.95),
        Node(id="db-replica", type="database", criticality=0.7),
        Node(id="cache", type="cache", criticality=0.6),
        Node(id="message-queue", type="queue", criticality=0.75),
        Node(id="notification", type="service", criticality=0.4),
        Node(id="search", type="service", criticality=0.5),
    ]

    edges = [
        Edge(source="api-gateway", target="auth", weight=0.85, kind="hard"),
        Edge(source="api-gateway", target="user-service", weight=0.75, kind="soft"),
        Edge(source="api-gateway", target="order-service", weight=0.90, kind="hard"),
        Edge(source="api-gateway", target="search", weight=0.50, kind="soft"),
        Edge(source="auth", target="db-primary", weight=0.80, kind="hard"),
        Edge(source="auth", target="cache", weight=0.60, kind="soft"),
        Edge(source="user-service", target="auth", weight=0.70, kind="hard"),
        Edge(source="user-service", target="db-primary", weight=0.75, kind="hard"),
        Edge(source="user-service", target="cache", weight=0.50, kind="soft"),
        Edge(source="order-service", target="payment", weight=0.90, kind="hard"),
        Edge(source="order-service", target="inventory", weight=0.85, kind="hard"),
        Edge(source="order-service", target="db-primary", weight=0.80, kind="hard"),
        Edge(source="order-service", target="message-queue", weight=0.65, kind="soft"),
        Edge(source="payment", target="db-primary", weight=0.90, kind="hard"),
        Edge(source="inventory", target="db-primary", weight=0.85, kind="hard"),
        Edge(source="inventory", target="cache", weight=0.40, kind="soft"),
        Edge(source="search", target="db-replica", weight=0.70, kind="soft"),
        Edge(source="search", target="cache", weight=0.60, kind="soft"),
        Edge(source="notification", target="message-queue", weight=0.80, kind="hard"),
        Edge(source="db-replica", target="db-primary", weight=0.75, kind="soft"),
    ]

    graph = Graph(nodes=nodes, edges=edges)

    # 2. Metrics tick (all 12 services at TIMESTAMP)
    metrics = [
        MetricTick(ts=TIMESTAMP, service="db-primary", latency_p95_ms=3200.0, error_rate=0.18, cpu=0.88, mem=0.72, queue_depth=45, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="order-service", latency_p95_ms=1450.0, error_rate=0.12, cpu=0.78, mem=0.68, queue_depth=24, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="payment", latency_p95_ms=850.0, error_rate=0.08, cpu=0.74, mem=0.65, queue_depth=18, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="api-gateway", latency_p95_ms=380.0, error_rate=0.06, cpu=0.68, mem=0.59, queue_depth=15, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="inventory", latency_p95_ms=620.0, error_rate=0.05, cpu=0.65, mem=0.58, queue_depth=10, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="auth", latency_p95_ms=480.0, error_rate=0.04, cpu=0.62, mem=0.55, queue_depth=8, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="user-service", latency_p95_ms=510.0, error_rate=0.04, cpu=0.60, mem=0.52, queue_depth=6, status="degraded"),
        MetricTick(ts=TIMESTAMP, service="db-replica", latency_p95_ms=35.0, error_rate=0.001, cpu=0.32, mem=0.45, queue_depth=2, status="healthy"),
        MetricTick(ts=TIMESTAMP, service="cache", latency_p95_ms=4.0, error_rate=0.000, cpu=0.28, mem=0.61, queue_depth=1, status="healthy"),
        MetricTick(ts=TIMESTAMP, service="message-queue", latency_p95_ms=18.0, error_rate=0.002, cpu=0.35, mem=0.40, queue_depth=5, status="healthy"),
        MetricTick(ts=TIMESTAMP, service="notification", latency_p95_ms=42.0, error_rate=0.001, cpu=0.22, mem=0.38, queue_depth=3, status="healthy"),
        MetricTick(ts=TIMESTAMP, service="search", latency_p95_ms=65.0, error_rate=0.001, cpu=0.30, mem=0.42, queue_depth=2, status="healthy"),
    ]

    # 3. Logs (last ~15 representative log lines at TIMESTAMP across services)
    logs = [
        LogLine(ts=TIMESTAMP - 45, service="db-primary", level="WARN", message="Connection pool saturation reached 92% of max limit (100)"),
        LogLine(ts=TIMESTAMP - 30, service="db-primary", level="ERROR", message="slow query detected: SELECT * FROM orders JOIN transactions WHERE created_at > ... elapsed 3200ms"),
        LogLine(ts=TIMESTAMP - 25, service="payment", level="ERROR", message="timeout calling db-primary after 3000ms"),
        LogLine(ts=TIMESTAMP - 20, service="order-service", level="WARN", message="retrying query to db-primary (attempt 2 of 3)"),
        LogLine(ts=TIMESTAMP - 18, service="order-service", level="ERROR", message="downstream dependency payment degraded, error rate exceeded threshold 5%"),
        LogLine(ts=TIMESTAMP - 15, service="inventory", level="WARN", message="db-primary latency spike: 620ms on stock reservation"),
        LogLine(ts=TIMESTAMP - 12, service="auth", level="WARN", message="slow response from db-primary session lookup: 480ms"),
        LogLine(ts=TIMESTAMP - 10, service="user-service", level="WARN", message="auth token validation latency elevated to 510ms"),
        LogLine(ts=TIMESTAMP - 8, service="api-gateway", level="WARN", message="upstream order-service response time p95 reached 1450ms"),
        LogLine(ts=TIMESTAMP - 5, service="api-gateway", level="ERROR", message="HTTP 504 Gateway Timeout on /checkout/complete"),
        LogLine(ts=TIMESTAMP - 4, service="message-queue", level="INFO", message="queue depths normal, 5 unacknowledged messages"),
        LogLine(ts=TIMESTAMP - 3, service="db-replica", level="INFO", message="replication lag 12ms behind db-primary"),
        LogLine(ts=TIMESTAMP - 2, service="cache", level="INFO", message="cache hit ratio 94.2%, memory utilization normal"),
        LogLine(ts=TIMESTAMP - 1, service="search", level="INFO", message="index query latency p95: 65ms"),
        LogLine(ts=TIMESTAMP, service="notification", level="INFO", message="processed 140 email/SMS delivery notifications"),
    ]

    # 4. Failure predictions (all 12 services sorted by fail_prob)
    predictions = PredictionResponse(
        ts=TIMESTAMP,
        predictions=[
            PredictionItem(service="db-primary", fail_prob=0.95, horizon_s=180.0, top_signals=["latency_p95_ms", "cpu", "queue_depth"]),
            PredictionItem(service="order-service", fail_prob=0.82, horizon_s=300.0, top_signals=["error_rate", "upstream:db-primary", "latency_p95_ms"]),
            PredictionItem(service="payment", fail_prob=0.78, horizon_s=240.0, top_signals=["latency_p95_ms", "upstream:db-primary", "error_rate"]),
            PredictionItem(service="inventory", fail_prob=0.65, horizon_s=360.0, top_signals=["latency_p95_ms", "upstream:db-primary"]),
            PredictionItem(service="api-gateway", fail_prob=0.58, horizon_s=420.0, top_signals=["downstream:order-service", "error_rate"]),
            PredictionItem(service="auth", fail_prob=0.42, horizon_s=480.0, top_signals=["latency_p95_ms", "upstream:db-primary"]),
            PredictionItem(service="user-service", fail_prob=0.38, horizon_s=540.0, top_signals=["upstream:auth", "latency_p95_ms"]),
            PredictionItem(service="message-queue", fail_prob=0.15, horizon_s=600.0, top_signals=["queue_depth"]),
            PredictionItem(service="search", fail_prob=0.12, horizon_s=600.0, top_signals=["latency_p95_ms"]),
            PredictionItem(service="db-replica", fail_prob=0.08, horizon_s=600.0, top_signals=["replication_lag"]),
            PredictionItem(service="cache", fail_prob=0.05, horizon_s=600.0, top_signals=["mem"]),
            PredictionItem(service="notification", fail_prob=0.04, horizon_s=600.0, top_signals=["queue_depth"]),
        ],
    )

    # 5. Cascade forecast
    cascade = CascadeForecast(
        ts=TIMESTAMP,
        paths=[
            CascadePath(from_node="db-primary", to_node="order-service", prob=0.85, eta_s=40.0),
            CascadePath(from_node="db-primary", to_node="payment", prob=0.80, eta_s=35.0),
            CascadePath(from_node="db-primary", to_node="inventory", prob=0.68, eta_s=60.0),
            CascadePath(from_node="db-primary", to_node="auth", prob=0.55, eta_s=75.0),
            CascadePath(from_node="order-service", to_node="api-gateway", prob=0.60, eta_s=95.0),
            CascadePath(from_node="payment", to_node="order-service", prob=0.72, eta_s=50.0),
            CascadePath(from_node="auth", to_node="user-service", prob=0.45, eta_s=110.0),
        ],
        blast_radius={
            "db-primary": 7,
            "order-service": 3,
            "payment": 2,
            "inventory": 2,
            "auth": 2,
            "api-gateway": 1,
            "user-service": 1,
            "db-replica": 0,
            "cache": 0,
            "message-queue": 1,
            "notification": 0,
            "search": 0,
        },
    )

    # 6. Root cause ranking
    root_cause = RootCauseResponse(
        ts=TIMESTAMP,
        candidates=[
            RootCauseCandidate(
                service="db-primary",
                score=0.91,
                explanation="Earliest anomaly (t-4m), 6 downstream services affected, slow query errors in logs",
            ),
            RootCauseCandidate(
                service="payment",
                score=0.48,
                explanation="Latency degradation and timeouts, but strongly correlated with upstream db-primary failure",
            ),
            RootCauseCandidate(
                service="order-service",
                score=0.35,
                explanation="Cascading error rate increase caused by slow queries in db-primary and timeouts in payment",
            ),
        ],
    )

    # 7. Recovery options
    recovery = RecoveryResponse(
        options=[
            RecoveryOption(
                strategy="failover_to_replica",
                target="db-primary",
                services_saved=6,
                est_recovery_s=45.0,
                cost=0.4,
                risk=0.2,
                score=0.87,
                recommended=True,
                rationale="Reroutes reads to the replica, keeping 6 dependants alive",
                projected_health=[0.4, 0.5, 0.7, 0.9],
            ),
            RecoveryOption(
                strategy="shed_load",
                target="api-gateway",
                services_saved=4,
                est_recovery_s=20.0,
                cost=0.3,
                risk=0.3,
                score=0.68,
                recommended=False,
                rationale="Drops non-essential traffic to reduce load on db-primary while stabilizing core transactions",
                projected_health=[0.4, 0.55, 0.65, 0.75],
            ),
            RecoveryOption(
                strategy="circuit_breaker_isolate",
                target="order-service",
                services_saved=3,
                est_recovery_s=30.0,
                cost=0.5,
                risk=0.4,
                score=0.55,
                recommended=False,
                rationale="Isolates failing payment and db calls to prevent gateway worker starvation",
                projected_health=[0.4, 0.48, 0.58, 0.65],
            ),
            RecoveryOption(
                strategy="restart",
                target="db-primary",
                services_saved=2,
                est_recovery_s=90.0,
                cost=0.6,
                risk=0.7,
                score=0.38,
                recommended=False,
                rationale="Full restart clears hung queries but drops active connections during reboot",
                projected_health=[0.2, 0.25, 0.6, 0.8],
            ),
        ]
    )

    # 8. Rolling history for all 12 services
    history = StateHistory(
        fail_prob={
            "db-primary": [0.10, 0.25, 0.55, 0.85, 0.95],
            "order-service": [0.05, 0.12, 0.30, 0.60, 0.82],
            "payment": [0.04, 0.10, 0.28, 0.55, 0.78],
            "inventory": [0.02, 0.05, 0.15, 0.40, 0.65],
            "api-gateway": [0.01, 0.04, 0.12, 0.32, 0.58],
            "auth": [0.02, 0.04, 0.10, 0.25, 0.42],
            "user-service": [0.01, 0.03, 0.08, 0.20, 0.38],
            "message-queue": [0.01, 0.02, 0.03, 0.08, 0.15],
            "search": [0.01, 0.02, 0.02, 0.05, 0.12],
            "db-replica": [0.01, 0.01, 0.02, 0.04, 0.08],
            "cache": [0.01, 0.01, 0.01, 0.02, 0.05],
            "notification": [0.01, 0.01, 0.01, 0.02, 0.04],
        }
    )

    # 9. Combined state embedding all mocks
    state = SystemState(
        ts=TIMESTAMP,
        tick=128,
        running=True,
        incident=IncidentState(
            active=True,
            fault=FaultInfo(service="db-primary", type="slow_query"),
        ),
        system_health=0.62,
        graph=graph,
        metrics=metrics,
        logs=logs,
        predictions=predictions,
        cascade=cascade,
        root_cause=root_cause,
        recovery=recovery,
        history=history,
    )

    # Write files
    def write_json(filename: str, data: dict | list):
        path = MOCKS_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"Wrote {path.name}")

    # Write individual mock files
    write_json("graph.json", graph.model_dump(by_alias=True))
    write_json("metrics.json", [m.model_dump(by_alias=True) for m in metrics])
    write_json("logs.json", [line.model_dump(by_alias=True) for line in logs])

    # Write logs.jsonl
    logs_jsonl_path = MOCKS_DIR / "logs.jsonl"
    with open(logs_jsonl_path, "w", encoding="utf-8") as f:
        for line in logs:
            f.write(json.dumps(line.model_dump(by_alias=True)) + "\n")
    print(f"Wrote {logs_jsonl_path.name}")

    write_json("predictions.json", predictions.model_dump(by_alias=True))
    write_json("cascade.json", cascade.model_dump(by_alias=True))
    write_json("root_cause.json", root_cause.model_dump(by_alias=True))
    write_json("recovery.json", recovery.model_dump(by_alias=True))
    write_json("state.json", state.model_dump(by_alias=True))

    print("\nAll mock files successfully generated and validated against schemas!")


if __name__ == "__main__":
    generate()
