# CLAUDE.md: Cascading Failure Predictor

You are helping a team of two build this project. The humans do not hand-code: you write the code, they run it, test it, and review it. Read `plan.md` for the full plan and contracts. This file holds the rules you must follow every session.

## What we are building

An AI system that predicts cascading software failures in a simulated microservice system, identifies the root cause, forecasts how failure will spread, and recommends the best recovery strategy, all shown on a live dashboard.

Pipeline: **Simulator -> Predictor -> Cascade + Root cause -> Recovery engine -> API -> Dashboard.**

## Who owns what (do not cross these lines)

Ask the user which person they are (Person 1 or Person 2) at the start of a session if it is not clear.

**Person 1 (Engine) owns:** `sim/`, `analysis/cascade.py`, `recovery/`, `eval/`
**Person 2 (Intelligence + Face) owns:** `ml/`, `analysis/rca.py`, `api/`, `dashboard/`
**Shared (change only with both people's agreement):** `api/schemas.py`, `config.py`, `mocks/`, `plan.md`, `CLAUDE.md`

Rules:
- Never edit a folder owned by the other person. If you need a change there, stop and tell the user to ask their teammate.
- Never change a shared file silently. If a contract must change, say so clearly, explain why, and wait for the user to confirm both people agree.
- Do not rename or move files and folders that exist in the layout below.

## Repo layout

```
/
├── plan.md
├── CLAUDE.md
├── README.md
├── config.py               # service names, fault types, strategies, thresholds, seed (shared)
├── requirements.txt
├── mocks/                  # frozen sample JSON for parallel work (shared)
├── sim/                    # P1: graph, simulator, faults, strategy hooks
├── ml/                     # P2: features, predictor
├── analysis/
│   ├── cascade.py          # P1
│   └── rca.py              # P2
├── recovery/               # P1: strategy engine
├── api/                    # P2: FastAPI + schemas.py (shared)
├── dashboard/              # P2: React + Vite + Tailwind
├── eval/                   # P1: evaluation harness
├── docs/                   # slides, demo script
└── data/                   # generated scenarios (gitignored)
```

## Fixed decisions (do not reopen or "improve")

- **One Python process.** FastAPI runs simulator, model, and analysis in-process. No Docker, no microservices, no message brokers.
- **Polling, not WebSocket.** Dashboard polls `GET /api/state` every 1 second.
- **12 services, 5 fault types, 6 strategies.** Names live in `config.py`. Do not add or rename any.
  - Services: `api-gateway, auth, user-service, order-service, payment, inventory, db-primary, db-replica, cache, message-queue, notification, search`
  - Faults: `memory_leak, slow_query, network_partition, bad_deploy, cpu_spike`
  - Strategies: `restart, scale_out, failover_to_replica, circuit_breaker_isolate, rollback_deploy, shed_load`
- **Python 3.11.** Frontend: React + Vite + Tailwind + Recharts, with React Flow or Cytoscape.js for the graph.
- **Fixed random seed** (default 42) everywhere randomness is used, so demos are repeatable.
- **Tick length:** one tick is about 5 simulated seconds.
- **Out of scope:** GNN/LSTM, full RL, Drain3 (use regex templates), WebSocket, Docker, authentication, databases. Do not add them even if they seem better.

## Contracts

The exact JSON shapes are in `plan.md` Section 2. The pydantic models in `api/schemas.py` are the source of truth in code. Every module must produce and consume exactly these shapes. Key points:

- Graph edge `source -> target` means source **depends on** target. Failure spreads in the **reverse** direction (target fails, source suffers).
- `GET /api/state` is the combined payload the dashboard reads.
- The `Simulator` class must provide: `tick()`, `inject_fault()`, `apply_strategy()`, `clone()`, `reset()`, `ground_truth()`, `graph()` (see `plan.md` Section 2.7). `clone()` must deep-copy RNG state so strategy simulations are deterministic.

## Mock flags

Each module can be served from `mocks/` instead of real code: `MOCK_SIM`, `MOCK_PREDICTOR`, `MOCK_CASCADE`, `MOCK_RCA`, `MOCK_RECOVERY` (environment variables or `config.py` defaults). When you finish a real module, make sure its flag works both ways and the app still runs with the flag off. Never delete mock files.

## How to work

1. **One task at a time.** Do exactly the task the user names. Do not start the next one.
2. **Plan first for anything non-trivial:** give a short plan (a few bullets), then implement.
3. **Always ship a way to verify.** Every task ends with a test or a runnable script, plus the exact one-line command to run it. If you cannot test something, say so.
4. **Keep it simple.** Prefer the simplest implementation that meets the contract. Prefer the standard library and the packages already in `requirements.txt`. Ask before adding a new dependency, and add it to `requirements.txt` when approved.
5. **Stay in your lane.** Edit only files in the current person's folders. If a task seems to need a change elsewhere, stop and say what and why.
6. **Match the contracts exactly.** Field names, types, and ranges (for example probabilities in [0, 1]) are not negotiable.
7. **Don't break the app.** After a change, the API must still start and `/api/state` must still return a valid payload.
8. **When something fails,** read the full error, explain the cause in one or two sentences, fix it, and re-run the verification. Do not paper over errors with broad `try/except` or by weakening a test.
9. **Report briefly.** When done: what you built, the command to run it, and anything the user must decide. No long recaps.

## Code conventions

- Python: type hints, small functions, docstrings for public functions, `pathlib.Path` for all paths (never hard-code `/` or `\\` separators), `random.Random(seed)` / `numpy.random.default_rng(seed)` instead of global randomness.
- **Cross-platform is required.** The code must run on Windows, macOS, and Linux. No bash-only or PowerShell-only scripts in the core workflow; use Python scripts or `npm` scripts. Use UTF-8 explicitly when reading or writing text files.
- Config values (thresholds, weights, tick length, seed) live in `config.py`, not scattered through the code.
- Performance budgets: `predict()` under 100 ms per tick; cascade Monte Carlo (about 300 runs) well under one tick; recovery ranking (clone and fast-forward about 30 ticks per strategy) under a few seconds.
- Frontend: dark theme, large readable fonts (projector use), loading and empty states for every panel, no hard-coded data (read from `/api/state`, or from `mocks/state.json` when the API is down).
- Names are descriptive; no one-letter variables outside tiny loops.

## Commands (keep this section up to date as the project grows)

```
# setup
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cd dashboard && npm install && cd ..

# generate training scenarios (P1)
python -m sim.generate --n 200 --seed 42

# train predictor (P2)
python -m ml.train

# run backend
uvicorn api.main:app --reload --port 8000

# run dashboard
cd dashboard && npm run dev

# tests
pytest

# evaluation (P1)
python -m eval.run --n 30
```

If a command here no longer matches reality, fix this section as part of the task and tell the user.

## Git rules

- Person 1 works on branch `p1-engine`, Person 2 on `p2-intelligence`. Never commit directly to `main`.
- Suggest a commit after every working task, with a short clear message (`sim: add slow_query fault with ramp`).
- Merge to `main` only at agreed checkpoints, and only after the app starts and `pytest` passes.
- Do not commit `data/`, `.venv/`, `node_modules/`, `.env`, or model files larger than a few MB unless the user says so.

## Definition of done (for any task)

- It matches the contract in `plan.md` / `api/schemas.py`.
- A test or demo script exists and passes, and you gave the command.
- The app still starts, with the relevant mock flag both on and off.
- No files outside the owner's folders were changed (shared files only with explicit agreement).
- The user knows what to run and what to expect.

## When in doubt

If a request conflicts with `plan.md`, the contracts, or the fixed decisions above, do not guess. Say what the conflict is, offer the simplest option that respects the plan, and ask the user to choose.
