"""FastAPI backend application for Cascading Failure Predictor.

Combines Simulator, Failure Predictor, Cascade Monte Carlo, RCA, and Recovery Engine.
Provides GET /api/state and control endpoints.
Supports per-module mock flags (MOCK_SIM, MOCK_PREDICTOR, MOCK_CASCADE, MOCK_RCA, MOCK_RECOVERY).
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import config as C
from analysis.cascade import forecast
from analysis.rca import rank_root_causes
from api.schemas import (
    ApplyStrategyRequest,
    ControlRequest,
    HealthResponse,
    InjectFaultRequest,
    ResetResponse,
    SystemState,
)
from ml.predictor import predict
from recovery.engine import rank
from sim.simulator import Simulator

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

# Helper to load frozen mock JSON files
def _load_mock(name: str) -> dict[str, Any]:
    path = C.MOCKS_DIR / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class SimulationManager:
    """Manages simulation state, background ticking, and module integration."""

    def __init__(self):
        self.running: bool = True
        self.speed: float = 1.0
        self.tick_count: int = 0
        self.history_len: int = 30
        self.active_fault: dict[str, str] | None = None
        self.rolling_metrics: list[dict[str, Any]] = []
        self.rolling_logs: list[dict[str, Any]] = []
        self.fail_prob_history: dict[str, list[float]] = {s: [0.02] for s in C.SERVICES}
        self.sim: Simulator = Simulator(seed=C.SEED)
        self.latest_state: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self.reset()

    def reset(self):
        """Resets the simulator and history."""
        self.sim = Simulator(seed=C.SEED)
        self.tick_count = 0
        self.active_fault = None
        self.rolling_metrics = []
        self.rolling_logs = []
        self.fail_prob_history = {s: [0.02] for s in C.SERVICES}

        # Initialize with baseline ticks
        for _ in range(5):
            m, l = self.sim.tick()
            self.rolling_metrics.extend(m)
            self.rolling_logs.extend(l)
            self.tick_count += 1

        self.update_state()

    def inject_fault(self, service: str, fault_type: str):
        """Injects a fault into the live simulation or mock state."""
        if service not in C.SERVICES:
            raise ValueError(f"Unknown service: {service}")
        if fault_type not in C.FAULT_TYPES:
            raise ValueError(f"Unknown fault type: {fault_type}")

        self.active_fault = {"service": service, "type": fault_type}
        if not C.MOCK_SIM:
            self.sim.inject_fault(service, fault_type)
        self.update_state()

    def apply_strategy(self, strategy: str, target: str):
        """Applies a recovery strategy to a target service."""
        if strategy not in C.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}")
        if target not in C.SERVICES:
            raise ValueError(f"Unknown target service: {target}")

        if not C.MOCK_SIM:
            self.sim.apply_strategy(strategy, target)
        # Clear active fault if appropriate strategy applied
        if self.active_fault and self.active_fault["service"] == target:
            self.active_fault = None
        self.update_state()

    def step(self):
        """Advances the simulation by one tick."""
        if C.MOCK_SIM:
            self.tick_count += 1
            return

        m, l = self.sim.tick()
        self.tick_count += 1
        self.rolling_metrics.extend(m)
        self.rolling_logs.extend(l)

        # Keep rolling buffer size bounded
        max_metrics = len(C.SERVICES) * self.history_len
        if len(self.rolling_metrics) > max_metrics:
            self.rolling_metrics = self.rolling_metrics[-max_metrics:]
        if len(self.rolling_logs) > 60:
            self.rolling_logs = self.rolling_logs[-60:]

        self.update_state()

    def update_state(self):
        """Recomputes predictions, cascade, RCA, recovery, and combines state."""
        # 1. Base simulator metrics and graph
        if C.MOCK_SIM:
            mock_state = _load_mock("state.json")
            mock_state["tick"] = self.tick_count
            mock_state["running"] = self.running
            if self.active_fault:
                mock_state["incident"] = {"active": True, "fault": self.active_fault}
            else:
                mock_state["incident"] = {"active": False, "fault": None}
            self.latest_state = mock_state
            return

        graph = self.sim.graph()
        latest_metrics = self.rolling_metrics[-len(C.SERVICES):] if self.rolling_metrics else []
        current_ts = latest_metrics[0].get("ts", C.START_TS) if latest_metrics else C.START_TS

        # 2. Failure Predictions
        if C.MOCK_PREDICTOR:
            predictions = _load_mock("predictions.json")
        else:
            predictions = predict(self.rolling_metrics, self.rolling_logs, graph, current_ts)

        # Update rolling probability history
        for p in predictions.get("predictions", []):
            srv = p["service"]
            prob = p["fail_prob"]
            if srv not in self.fail_prob_history:
                self.fail_prob_history[srv] = []
            self.fail_prob_history[srv].append(prob)
            if len(self.fail_prob_history[srv]) > self.history_len:
                self.fail_prob_history[srv] = self.fail_prob_history[srv][-self.history_len:]

        # 3. Cascade Forecast
        if C.MOCK_CASCADE:
            cascade = _load_mock("cascade.json")
        else:
            cascade = forecast(graph, predictions, runs=250, seed=C.SEED)

        # 4. Root Cause Analysis
        if C.MOCK_RCA:
            root_cause = _load_mock("root_cause.json")
        else:
            root_cause = rank_root_causes(self.rolling_metrics, self.rolling_logs, graph, current_ts)

        # 5. Recovery Options
        top_suspect = None
        if root_cause.get("candidates"):
            top_suspect = root_cause["candidates"][0]["service"]
        elif self.active_fault:
            top_suspect = self.active_fault["service"]

        if C.MOCK_RECOVERY:
            recovery = _load_mock("recovery.json")
        else:
            if top_suspect or self.sim.stress:
                recovery = rank(self.sim, target=top_suspect)
            else:
                recovery = {"options": []}

        # Calculate overall system health [0, 1]
        if latest_metrics:
            health_values = [
                0.0 if m.get("status") == "failed" else 0.5 if m.get("status") == "degraded" else 1.0
                for m in latest_metrics
            ]
            system_health = round(sum(health_values) / len(health_values), 2)
        else:
            system_health = 1.0

        is_active = (
            self.active_fault is not None
            or system_health < 0.95
            or any(m.get("status") != "healthy" for m in latest_metrics)
        )

        self.latest_state = {
            "ts": current_ts,
            "tick": self.tick_count,
            "running": self.running,
            "incident": {
                "active": is_active,
                "fault": self.active_fault,
            },
            "system_health": system_health,
            "graph": graph,
            "metrics": latest_metrics,
            "logs": self.rolling_logs[-40:],
            "predictions": predictions,
            "cascade": cascade,
            "root_cause": root_cause,
            "recovery": recovery,
            "history": {
                "fail_prob": dict(self.fail_prob_history),
            },
        }


sim_manager = SimulationManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background simulation loop runner."""
    async def background_loop():
        logger.info("Starting simulation background loop...")
        while True:
            try:
                if sim_manager.running:
                    async with sim_manager._lock:
                        sim_manager.step()
                sleep_s = max(0.1, 1.0 / max(0.1, sim_manager.speed))
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    task = asyncio.create_task(background_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Cascading Failure Predictor API",
    version="1.0.0",
    description="Live AI system predicting microservice cascades, root causes, and recovery strategies.",
    lifespan=lifespan,
)

# Enable CORS for external dashboard or development servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/api/state", response_model=SystemState)
def get_state():
    """Combined state endpoint polled by dashboard every 1s."""
    state = sim_manager.latest_state
    if not state:
        return _load_mock("state.json")
    return state


@app.post("/api/inject-fault")
async def inject_fault(req: InjectFaultRequest):
    """Inject a fault into a service."""
    async with sim_manager._lock:
        try:
            sim_manager.inject_fault(req.service, req.type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"status": "injected", "service": req.service, "type": req.type}


@app.post("/api/apply-strategy")
async def apply_strategy(req: ApplyStrategyRequest):
    """Apply a recovery strategy to a target service."""
    async with sim_manager._lock:
        try:
            sim_manager.apply_strategy(req.strategy, req.target)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"status": "applied", "strategy": req.strategy, "target": req.target}


@app.post("/api/control")
async def control(req: ControlRequest):
    """Controls simulation play/pause state and speed."""
    async with sim_manager._lock:
        sim_manager.running = (req.action == "play")
        sim_manager.speed = float(req.speed)
        sim_manager.update_state()
    return {"status": "updated", "running": sim_manager.running, "speed": sim_manager.speed}


@app.post("/api/reset", response_model=ResetResponse)
async def reset():
    """Resets the simulation to the initial healthy state."""
    async with sim_manager._lock:
        sim_manager.reset()
    return ResetResponse(status="reset")


# Serve the live dashboard UI on the root path
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the live interactive dashboard UI."""
    if DASHBOARD_FILE.exists():
        return FileResponse(DASHBOARD_FILE)
    return HTMLResponse("<h1>Cascading Failure Predictor</h1><p>Dashboard file loading...</p>")
