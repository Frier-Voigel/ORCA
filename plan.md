# Cascading Failure Predictor: Build Plan (Team of 2)

> **Problem:** Build an AI system that predicts cascading software failures, identifies their root causes, and recommends the best recovery strategy before the whole system crashes. It analyses simulated logs and service dependencies, traces how failure spreads, and compares recovery strategies on a live dashboard.

**Team:** Person 1 (Engine) and Person 2 (Intelligence + Face). Code is written by an AI coding tool; humans specify, run, test, and review.

---

## 0. How this plan works

- Work is split by **folder ownership**, so each person works alone on their own branch and merges at fixed checkpoints.
- Both people code against the **frozen contracts in Section 2**, never against each other's code. Until a real module exists, use the JSON in `/mocks/`.
- Every module is switchable between mock and real with an environment flag (Section 6), so the app always runs.
- Timings are given as **phases with a percentage of total time**. For an 8-hour build, multiply by 8h. For a 3-hour build, multiply by 3h. Put the real clock times in the table in Section 9 once you know the deadline.

### Ownership

| Area | Folder / file | Owner |
|---|---|---|
| Graph, simulator, fault injection, ground truth, strategy hooks, `clone()` | `sim/` | **P1** |
| Cascade prediction (Monte Carlo) | `analysis/cascade.py` | **P1** |
| Recovery strategy engine | `recovery/` | **P1** |
| Evaluation harness, charts | `eval/` | **P1** |
| Failure predictor (features + model) | `ml/` | **P2** |
| Root cause ranking | `analysis/rca.py` | **P2** |
| FastAPI backend, combined state, control endpoints | `api/` | **P2** |
| Dashboard | `dashboard/` | **P2** |
| Contracts, config, mocks | `api/schemas.py`, `config.py`, `mocks/` | **Shared** (change only by agreement) |
| Slides, demo script, README | `docs/`, `README.md` | **Split**: P1 slides + eval numbers, P2 demo script + README |

---

## 1. Decisions (already made, do not reopen)

- **One Python process.** FastAPI runs the simulator, model, and analysis in-process. No Docker, no microservices.
- **Polling, not WebSocket.** The dashboard polls `GET /api/state` every 1 second.
- **Simulation speed:** 1 tick is about 5 simulated seconds, so a full cascade plays out in 1 to 2 real minutes.
- **12 services, 5 fault types, 6 strategies.** Do not add more.
- **One combined endpoint** `/api/state` first. Split it later only if needed.
- **Fixed random seed** (default `42`) for repeatable demos.
- **Cross-platform:** must run on Windows, macOS, and Linux. Use `pathlib`, no shell-specific scripts, pinned `requirements.txt`, and `package.json`.
- **Python 3.11.** Frontend: React + Vite + Tailwind + Recharts, plus React Flow or Cytoscape.js for the graph. Fallback if the dashboard slips: Streamlit.

---

## 2. Shared contracts (freeze in the first 30 minutes)

### 2.1 Service catalogue

`api-gateway, auth, user-service, order-service, payment, inventory, db-primary, db-replica, cache, message-queue, notification, search`

### 2.2 Fault types

`memory_leak, slow_query, network_partition, bad_deploy, cpu_spike`

### 2.3 Strategy library

`restart, scale_out, failover_to_replica, circuit_breaker_isolate, rollback_deploy, shed_load`

### 2.4 Data shapes

**Graph**
```json
{
  "nodes": [{"id": "db-primary", "type": "database", "criticality": 0.9}],
  "edges": [{"source": "order-service", "target": "db-primary", "weight": 0.8, "kind": "hard"}]
}
```
An edge means `source` **depends on** `target`. `weight` in [0,1] is how strongly a failure of the target hurts the source. `kind` is `hard` or `soft`.

**Metrics tick** (one row per service per tick)
```json
{"ts": 1730000000, "service": "payment", "latency_p95_ms": 240, "error_rate": 0.03,
 "cpu": 0.71, "mem": 0.64, "queue_depth": 12, "status": "degraded"}
```
`status` is `healthy | degraded | failed`.

**Log line**
```json
{"ts": 1730000000, "service": "payment", "level": "ERROR", "message": "timeout calling db-primary after 3000ms"}
```

**Failure prediction**
```json
{"ts": 1730000000, "predictions": [
  {"service": "order-service", "fail_prob": 0.82, "horizon_s": 300, "top_signals": ["error_rate", "upstream:db-primary"]}
]}
```

**Cascade forecast**
```json
{"ts": 1730000000, "paths": [
  {"from": "db-primary", "to": "order-service", "prob": 0.85, "eta_s": 40},
  {"from": "order-service", "to": "api-gateway", "prob": 0.6, "eta_s": 95}
], "blast_radius": {"db-primary": 7}}
```

**Root cause**
```json
{"ts": 1730000000, "candidates": [
  {"service": "db-primary", "score": 0.91, "explanation": "Earliest anomaly (t-4m), 6 downstream services affected, slow query errors in logs"}
]}
```

**Recovery options**
```json
{"options": [
  {"strategy": "failover_to_replica", "target": "db-primary", "services_saved": 6,
   "est_recovery_s": 45, "cost": 0.4, "risk": 0.2, "score": 0.87, "recommended": true,
   "rationale": "Reroutes reads to the replica, keeping 6 dependants alive",
   "projected_health": [0.4, 0.5, 0.7, 0.9]}
]}
```

### 2.5 Combined state (the main endpoint)

`GET /api/state` returns everything the dashboard needs in one payload:

```json
{
  "ts": 1730000000,
  "tick": 128,
  "running": true,
  "incident": {"active": true, "fault": {"service": "db-primary", "type": "slow_query"}},
  "system_health": 0.62,
  "graph": { "nodes": [], "edges": [] },
  "metrics": [ /* latest metrics tick per service */ ],
  "logs": [ /* last ~50 log lines */ ],
  "predictions": { },
  "cascade": { },
  "root_cause": { },
  "recovery": { },
  "history": { "fail_prob": { "order-service": [0.1, 0.2, 0.4] } }
}
```

### 2.6 Control endpoints

- `POST /api/inject-fault` body `{"service": "db-primary", "type": "slow_query"}`
- `POST /api/apply-strategy` body `{"strategy": "failover_to_replica", "target": "db-primary"}`
- `POST /api/reset`
- `POST /api/control` body `{"action": "play" | "pause", "speed": 1}`
- `GET /health`

### 2.7 Simulator interface (P1 must provide, P2 and recovery code rely on it)

```python
class Simulator:
    def __init__(self, seed: int = 42, graph_path: str = "sim/graph.yaml"): ...
    def tick(self) -> tuple[list[dict], list[dict]]:   # (metrics rows, log lines)
    def inject_fault(self, service: str, fault_type: str) -> None: ...
    def apply_strategy(self, strategy: str, target: str) -> None: ...
    def clone(self) -> "Simulator":                    # deep copy incl. RNG state
    def reset(self) -> None: ...
    def ground_truth(self) -> dict:                    # root_cause, fault_type, onset_ts, affected_services, failure_times
    def graph(self) -> dict:                           # matches Graph contract
```

### 2.8 Mock files (committed in the first hour)

`mocks/graph.json, metrics.parquet (or metrics.json), logs.jsonl, predictions.json, cascade.json, root_cause.json, recovery.json, state.json`

---

## 3. Person 1: Engine

### P1-A. Graph + Simulator (critical path, do this first)

1. Build the dependency graph with `networkx` from `sim/graph.yaml` (12 services). Export `mocks/graph.json`.
2. Baseline metrics generator: healthy patterns plus noise per service.
3. Log generator: templated INFO/WARN/ERROR lines. Error templates tied to fault types (for example `slow_query` produces "query exceeded 2000ms").
4. Fault injector for all 5 fault types, with onset and ramp (gradual for `memory_leak`, abrupt for `bad_deploy`).
5. Propagation engine: a degraded node degrades its dependants after a delay scaled by edge weight, with some probability. Include retry storms and timeouts as visible symptoms.
6. Ground truth for every run.
7. **Batch mode:** one command generates 150 to 200 labelled scenarios into `data/scenarios/`.
8. **Live mode:** `Simulator.tick()` per Section 2.7.
9. Strategy hooks (second pass): `restart`, `scale_out`, `failover_to_replica`, `circuit_breaker_isolate`, `rollback_deploy`, `shed_load`, plus `clone()`.

**Ship `mocks/` and the first 50 scenarios fast. P2 is waiting on them.**

**Done when:** one command generates 150+ labelled scenarios, and live mode can inject a fault and show a cascade over 2 to 5 simulated minutes.

### P1-B. Cascade prediction (`analysis/cascade.py`)

1. Weighted probabilistic propagation over the reversed dependency direction (if X fails, who depends on X).
2. Independent-cascade Monte Carlo, about 300 runs, seeded.
3. Output per-path `prob`, `eta_s`, and `blast_radius` per node, matching the Cascade contract.
4. Seed from current high-risk nodes using `fail_prob` (use `mocks/predictions.json` until P2's model exists).

**Done when:** output matches the contract and runs in well under one tick.

### P1-C. Recovery engine (`recovery/`) — the winning feature

1. `recovery/strategies.yaml`: for each strategy, what it fixes, side effects, time, cost, applicability.
2. Applicability rules (for example `rollback_deploy` only for `bad_deploy`; `failover_to_replica` only if a replica exists).
3. For each applicable strategy: `clone()` the simulator, apply it, fast-forward about 30 ticks, record services saved, services still failing, time to recover, user-facing error rate, and a short projected-health series.
4. Weighted scoring (services saved high; recovery time, cost, risk lower). Weights live in config and are shown in the UI.
5. Return the ranked list per the Recovery contract, with a one-line `rationale` each and one `recommended: true`.
6. Stretch: a small bandit policy that learns the weights.

**Done when:** for each of the 5 fault types the engine picks a sensible best strategy, and outcomes visibly differ between strategies.

### P1-D. Evaluation (`eval/run.py`)

Run 30 held-out scenarios through the full pipeline and report:
- Prediction: precision, recall, AUC, **median lead time** (minutes of warning).
- Root cause: top-1 and top-3 accuracy.
- Recovery: downtime and services lost, **with AI vs. without AI** (no action, and naive restart).

Produce 2 or 3 clean charts or tables for the slides.

---

## 4. Person 2: Intelligence + Face

### P2-A. Backend API (`api/`) — start here

1. `api/schemas.py`: pydantic models for every contract in Section 2.
2. **Day-one stubs:** every endpoint returns the matching file from `/mocks/`. This unblocks the dashboard immediately.
3. `GET /api/state` combined payload (Section 2.5), plus the control endpoints (Section 2.6).
4. Background loop: tick the simulator, run predictor, cascade, RCA, recovery, and keep the latest state in memory. Keep a rolling history of `fail_prob`.
5. Per-module mock flags (Section 6) so each real module can be swapped in independently.
6. CORS enabled, `/docs` as the shared reference.
7. Optional: persist a run log for replay mode, with a fixed seed.

**Done when:** the dashboard works end to end against the API with all mock flags set to `false`.

### P2-B. Dashboard (`dashboard/`)

Build against `mocks/state.json` first, then point at the API.

1. Layout: top status bar (system health, active incident), main graph, side panels, bottom strategy comparison.
2. **Dependency graph:** nodes coloured green to red by `fail_prob`, animated edges for cascade paths, click a node for details.
3. **Log panel:** streaming logs with level colouring and small sparklines for the selected service.
4. **Failure probability timeline:** line chart of the top-N services.
5. **Root cause card:** top candidate, score, explanation, and runner-ups.
6. **Strategy comparison view (key feature):** side-by-side cards with projected recovery time, services saved, cost, risk, a mini projected-health chart, and the recommended one highlighted. Show the scoring weights.
7. **Controls:** inject-fault dropdown and button, apply-strategy button, reset, play/pause/speed.
8. Polling hook (1s) with error handling and loading/empty states.
9. Polish: dark theme, large fonts, readable at projector resolution.

**Done when:** a non-technical viewer can follow the incident from the screen alone.

### P2-C. Failure predictor (`ml/`)

1. Rolling-window features (1, 5, 15 ticks): mean, max, and slope of error rate, p95 latency, CPU, memory, queue depth.
2. Log features: WARN/ERROR counts per window and share of new message templates (regex templates, not Drain3).
3. Graph features: worst and mean health of upstream and downstream neighbours, number of degraded dependencies.
4. Isolation Forest anomaly score as a feature and as a **fallback** so graph colours move even before the model is trained.
5. LightGBM, label = "service fails within the horizon". **Split train/test by scenario, not by row.**
6. Calibrate probabilities (isotonic or Platt).
7. `predict(window)` returns the Failure prediction contract with top contributing signals (feature importances or SHAP). Must run in under 100 ms per tick.

**Done when:** test AUC and PR are reported, median lead time is measured, and `predict()` is fast enough for live use.

### P2-D. Root cause ranking (`analysis/rca.py`)

1. Weighted scorer: earliest anomaly time, number of downstream anomalous services explained, own severity, absence of anomalous upstream causes.
2. Templated plain-English explanation per candidate.
3. Measure top-1 and top-3 accuracy against simulator ground truth.
4. Stretch: PageRank-style score on the reversed graph, or an LLM summary from the top log lines (about 15 minutes with an API key).

---

## 5. Phases and timeline

Percentages are of total available time.

| Phase | Time | P1 | P2 |
|---|---|---|---|
| **0. Contracts + skeleton** | 0 to 8% | Together: repo, `CLAUDE.md`, `schemas.py`, `config.py`, mocks, merge to `main` | same |
| **1. Parallel build** | 8 to 40% | Simulator (graph, baseline, logs, faults, propagation), batch scenarios | API stubs and `/api/state`, dashboard graph + logs + timeline on mocks |
| **Checkpoint 1** | at 40% | Real simulator live in the API; fault button triggers a visible cascade | Dashboard points at real API; anomaly baseline colours the graph |
| **2. Parallel build** | 40 to 72% | Strategy hooks + `clone()`, cascade, recovery engine | Predictor trained and calibrated, then RCA; strategy comparison view and controls |
| **Checkpoint 2** | at 72% | Full loop: inject, predict, cascade, root cause, compare, apply, recover. Log every bug, split the fixes | same |
| **3. Polish + evidence** | 72 to 90% | Evaluation harness on 30 held-out scenarios, charts, slides | UI polish, replay mode, bug fixes from checkpoint 2, README |
| **4. Freeze + rehearse** | 90 to 100% | No new features. Run the 2-minute demo twice, record a backup video | same |

---

## 6. Mock flags (so merging never breaks the app)

Set in `.env` (or `config.py` defaults). Each flag, when `true`, serves the matching mock file instead of the real module.

```
MOCK_SIM=true
MOCK_PREDICTOR=true
MOCK_CASCADE=true
MOCK_RCA=true
MOCK_RECOVERY=true
```

As each real module lands, its owner flips its flag to `false` on their branch, verifies the app still runs, then merges.

---

## 7. Working and merging rules

- **One branch each:** `p1-engine`, `p2-intelligence`. Commit after every working step.
- **Merge to `main` only at:** end of phase 0, checkpoint 1, checkpoint 2, and the feature freeze. Both pull `main` right after.
- **Never edit the other person's folder.** Need a change there? Ask them, or agree on a contract change and edit the shared file together.
- **Shared files** (`api/schemas.py`, `config.py`, `mocks/`) change only by agreement, in a small PR the other person approves.
- **If a merge conflicts,** give the conflict to the AI and ask it to resolve it while keeping both sides' intent, then re-run the tests.
- **If a track is 20% of the time behind,** swap in the simpler option: rule-based predictor, deterministic cascade, or Streamlit for the dashboard.

---

## 8. Scope control

**Must have:** simulator and graph, failure predictor, root cause ranking, dashboard with graph, fault injection.

**Should have:** cascade propagation, strategy comparison with scoring, evaluation numbers.

**Nice to have:** LLM-written incident summary, replay mode, PageRank RCA, bandit-based recovery, alerting integration.

**Cut:** GNN or LSTM, full RL, Drain3, WebSocket, Docker.

---

## 9. Demo script (2 to 3 minutes)

1. Healthy system on the dashboard.
2. Inject `slow_query` on `db-primary`.
3. Dashboard predicts the cascade (`order-service`, `payment`, then `api-gateway`).
4. Root cause card names `db-primary` with an explanation.
5. Compare 3 recovery options and apply the recommended one.
6. System recovers; show the numbers (AI vs. no action).

**Backup plan:** a recorded video of the demo, plus a fixed-seed **replay mode** in case the live demo fails.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Simulated data is too easy, so the model looks unrealistically good | Add noise, overlapping symptoms, and multiple simultaneous faults; evaluate on unseen fault and service combinations |
| P2 blocked waiting for simulator data | P2 starts with API stubs and the dashboard on mocks; P1 ships mocks and 50 scenarios first |
| Integration breaks at the end | Contracts and mocks from minute 0; mock flags; merge at checkpoints, not only at the end |
| AI-written code that nobody understands breaks late | One task at a time, a test per task, commit often, both of you run the full loop at each checkpoint |
| Live demo fails | Replay mode with fixed seed, and a recorded video |
| Scope creep | Stretch items only after checkpoint 2 |

---

## 11. Checklist

**Shared**
- [x] Repo created, both people added
- [x] `CLAUDE.md` and `plan.md` committed
- [x] `api/schemas.py`, `config.py`, `mocks/` committed and frozen

**Person 1**
- [x] Simulator with 5 fault types, propagation, ground truth
- [x] 150+ labelled scenarios generated
- [x] Live `tick()`, `inject_fault()`, `reset()`
- [x] Strategy hooks and `clone()`
- [x] Cascade Monte Carlo
- [x] Recovery engine with scoring and ranking
- [x] Evaluation harness and charts

**Person 2**
- [x] API stubs, then real `/api/state` and control endpoints
- [x] Dashboard: graph, logs, timeline, root cause card
- [x] Dashboard: strategy comparison and controls
- [x] Predictor trained, calibrated, lead time measured
- [x] Root cause ranker with top-1 and top-3 accuracy
- [x] README with setup in 3 commands, demo script

**Together**
- [x] Checkpoint 1 passed
- [x] Checkpoint 2 passed (full loop verified)
- [ ] Slides & backup video recording
