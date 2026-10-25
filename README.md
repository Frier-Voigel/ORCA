# Cascading Failure Predictor

An AI system that predicts cascading software failures in microservice architectures, identifies their root causes, forecasts failure propagation paths, and recommends the optimal recovery strategy before the entire system crashes.

---

## Setup & Quickstart (3 Commands)

```bash
# 1. Activate environment and install dependencies
source .venv/bin/activate && pip install -r requirements.txt

# 2. Run test verification (all 25+ tests)
python -m unittest discover -s tests -v

# 3. Launch live application (API + Dashboard)
uvicorn api.main:app --reload --port 8000
```

Open your browser to: **`http://localhost:8000`** to view the live telemetry dashboard.

---

## 2-to-3 Minute Demo Script

1. **Baseline Health**:
   - Open `http://localhost:8000`.
   - Observe the 12 microservices in the dependency graph glowing green (System Health: 100%, 0 incident alerts).
2. **Inject Fault**:
   - In the controls bar, select **`db-primary`** and fault type **`slow_query`**.
   - Click **`Inject Fault`**.
3. **Failure Prediction & Cascade**:
   - Notice failure probability on `db-primary` spike to 95%.
   - Within 2-3 ticks, the predictor flags downstream dependants (`order-service`, `payment`, `api-gateway`).
   - Red dashed animated cascade vectors highlight the propagation path across the graph.
4. **Root Cause Analysis (RCA)**:
   - The RCA card identifies **`db-primary`** as the top suspect (confidence ~91%), explaining the earliest anomaly onset, downstream blast radius, and slow query logs.
5. **Recovery Strategy Evaluation**:
   - Under *Automated Recovery Strategy Evaluation*, compare side-by-side options.
   - Observe **`failover_to_replica`** highlighted with the **RECOMMENDED** badge (highest score: 0.87, saves 6 dependants, 45s recovery).
   - Click **`Apply Recommended Fix`**.
6. **Recovery & SLA Restoration**:
   - System health restores to 100%, graph turns green, and cascade vectors clear.

---

## Running Individual Modules

- **Train Predictor**:
  ```bash
  python -m ml.train
  ```
- **Run Full Pipeline Evaluation (Recovery, RCA, and Prediction)**:
  ```bash
  python -m eval.run --n 30
  ```
- **Run Test Suite**:
  ```bash
  python -m unittest discover -s tests -v
  ```
# ORCA
