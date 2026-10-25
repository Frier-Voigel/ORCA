"""System configuration and constants for Cascading Failure Predictor.

Shared file: Freeze in Phase 0. Changes require agreement between P1 and P2.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load optional .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Base paths
BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR
MOCKS_DIR = BASE_DIR / "mocks"
DATA_DIR = BASE_DIR / "data"
SIM_DIR = BASE_DIR / "sim"
GRAPH_PATH = SIM_DIR / "graph.yaml"

# 2.1 Service catalogue (exactly 12 services)
SERVICES: list[str] = [
    "api-gateway",
    "auth",
    "user-service",
    "order-service",
    "payment",
    "inventory",
    "db-primary",
    "db-replica",
    "cache",
    "message-queue",
    "notification",
    "search",
]

# 2.2 Fault types (exactly 5 fault types)
FAULT_TYPES: list[str] = [
    "memory_leak",
    "slow_query",
    "network_partition",
    "bad_deploy",
    "cpu_spike",
]

# 2.3 Strategy library (exactly 6 strategies)
STRATEGIES: list[str] = [
    "restart",
    "scale_out",
    "failover_to_replica",
    "circuit_breaker_isolate",
    "rollback_deploy",
    "shed_load",
]

# Simulation & Runtime parameters
DEFAULT_SEED: int = int(os.getenv("SEED", "42"))
SEED: int = DEFAULT_SEED
TICK_DURATION_S: float = float(os.getenv("TICK_DURATION_S", "5.0"))
TICK_SECONDS: int = int(TICK_DURATION_S)
POLL_INTERVAL_S: float = float(os.getenv("POLL_INTERVAL_S", "1.0"))
START_TS: int = 1_730_000_000
DEGRADED_AT: float = 0.30
FAILED_AT: float = 0.70


# Helper for parsing boolean environment flags
def _bool_env(var_name: str, default: bool = True) -> bool:
    val = os.getenv(var_name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Mock flags (Section 6: default to True until real implementations land)
MOCK_SIM: bool = _bool_env("MOCK_SIM", True)
MOCK_PREDICTOR: bool = _bool_env("MOCK_PREDICTOR", True)
MOCK_CASCADE: bool = _bool_env("MOCK_CASCADE", True)
MOCK_RCA: bool = _bool_env("MOCK_RCA", True)
MOCK_RECOVERY: bool = _bool_env("MOCK_RECOVERY", True)

# Recovery scoring weights (high for services saved; lower for time, cost, risk)
RECOVERY_WEIGHTS: dict[str, float] = {
    "services_saved": 0.50,
    "est_recovery_s": 0.20,
    "risk": 0.15,
    "cost": 0.15,
}

# API settings
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
