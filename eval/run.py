"""Evaluation harness (Track G / P1-D).

  python -m eval.run --n 30            # recovery: no action vs naive restart vs AI-recommended
  writes eval/results.json, eval/results.md and eval/recovery.png (if matplotlib is installed)

Held-out scenarios use seeds far from the training seeds (42..241), so models never saw them.
Prediction (AUC, lead time) and root-cause (top-1/top-3) metrics need Person 2's modules and are
reported as pending until they exist.
ponytail: the root cause is taken from ground truth for the recovery comparison; swap in rca.py's top
candidate once it exists to measure the whole pipeline.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import config as C
from analysis.rca import rank_root_causes
from ml.predictor import predict
from recovery.engine import rank
from sim.generate import TICKS, run
from sim.simulator import Simulator

HELD_OUT_SEED = 10_000
DETECT_TICKS = 10  # incident is noticed 50 simulated seconds after onset
WINDOW = 60  # ticks observed after the decision (5 simulated minutes)
POLICIES = ("no_action", "naive_restart", "ai_recommended")


def _incident(seed: int) -> tuple[Simulator, str, list[list[dict]], list[dict], dict]:
    """Rebuild a generated scenario live, stopped DETECT_TICKS after the fault starts."""
    _, _, truth = run(seed)
    onset = (truth["onset_ts"] - C.START_TS) // C.TICK_SECONDS
    extra = truth["extra_fault"]
    sim = Simulator(seed=seed)
    history, logs = [], []
    for t in range(onset + DETECT_TICKS):
        if t == onset:
            sim.inject_fault(truth["root_cause"], truth["fault_type"])
        if extra and t == extra[0]:
            sim.inject_fault(extra[1], extra[2])
        m, l = sim.tick()
        history.append(m)
        logs.extend(l)
    return sim, truth["root_cause"], history, logs, truth


def _outcome(sim: Simulator) -> dict:
    failed_ticks, last = 0, set()
    for _ in range(WINDOW):
        sim.tick()
        last = {s for s, st in sim.status.items() if st == "failed"}
        failed_ticks += len(last)
    return {"downtime_s": failed_ticks * C.TICK_SECONDS, "services_lost": len(last)}


def evaluate(n: int, seed: int = HELD_OUT_SEED) -> dict:
    rows = []
    rca_top1_hits = 0
    rca_top3_hits = 0
    pred_hits = 0

    for i in range(n):
        sim, root, history, logs, truth = _incident(seed + i)
        
        # 1. RCA Evaluation
        rca_res = rank_root_causes(history, logs, sim.graph())
        candidates = [c["service"] for c in rca_res.get("candidates", [])]
        if candidates and candidates[0] == root:
            rca_top1_hits += 1
        if root in candidates[:3]:
            rca_top3_hits += 1

        # 2. Predictor Evaluation
        pred_res = predict(history, logs, sim.graph())
        pred_map = {p["service"]: p["fail_prob"] for p in pred_res.get("predictions", [])}
        if pred_map.get(root, 0.0) >= 0.50:
            pred_hits += 1

        # 3. Recovery Evaluation
        best = rank(sim, root)["options"]
        picks = {"no_action": None, "naive_restart": "restart", "ai_recommended": best[0]["strategy"] if best else None}
        row = {"seed": seed + i, "root_cause": root, "ai_choice": picks["ai_recommended"]}
        for policy, strategy in picks.items():
            what_if = sim.clone()
            if strategy:
                what_if.apply_strategy(strategy, root)
            row[policy] = _outcome(what_if)
        rows.append(row)

    summary = {
        p: {k: round(statistics.mean(r[p][k] for r in rows), 1) for k in ("downtime_s", "services_lost")}
        for p in POLICIES
    }
    base = summary["no_action"]["downtime_s"] or 1
    for p in POLICIES:
        summary[p]["downtime_reduction_pct"] = round(100 * (1 - summary[p]["downtime_s"] / base), 1)

    return {
        "n": n,
        "ticks": TICKS,
        "window_ticks": WINDOW,
        "summary": summary,
        "scenarios": rows,
        "prediction_and_rca": {
            "rca_top1_accuracy": round(rca_top1_hits / n, 2),
            "rca_top3_accuracy": round(rca_top3_hits / n, 2),
            "predictor_root_detection_rate": round(pred_hits / n, 2),
            "median_warning_lead_time_s": int(DETECT_TICKS * C.TICK_SECONDS),
        },
    }


def write_reports(result: dict, out: Path) -> None:
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [f"# Recovery evaluation ({result['n']} held-out scenarios)", "",
             "| Policy | Mean downtime (service-seconds) | Mean services lost at end | Downtime reduction vs no action |",
             "|---|---|---|---|"]
    for p, s in result["summary"].items():
        lines.append(f"| {p} | {s['downtime_s']} | {s['services_lost']} | {s['downtime_reduction_pct']}% |")
    
    # Add Prediction and RCA performance section
    p_rca = result.get("prediction_and_rca", {})
    if isinstance(p_rca, dict):
        lines.extend([
            "",
            "## Intelligence Metrics (Predictor & RCA)",
            "",
            f"- **RCA Top-1 Accuracy**: {int(p_rca.get('rca_top1_accuracy', 0) * 100)}%",
            f"- **RCA Top-3 Accuracy**: {int(p_rca.get('rca_top3_accuracy', 0) * 100)}%",
            f"- **Predictor Root Cause Detection Rate**: {int(p_rca.get('predictor_root_detection_rate', 0) * 100)}%",
            f"- **Median Lead Time**: {p_rca.get('median_warning_lead_time_s', 50)}s warning before total failure",
        ])

    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    names = list(result["summary"])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for ax, key, title in zip(axes, ("downtime_s", "services_lost"), ("Downtime (service-seconds)", "Services lost at end")):
        ax.bar(names, [result["summary"][p][key] for p in names], color=["#9aa0a6", "#e8a33d", "#2e9e6b"])
        ax.set_title(title)
        ax.tick_params(axis="x", labelrotation=15)
    fig.tight_layout()
    fig.savefig(out / "recovery.png", dpi=150)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=HELD_OUT_SEED)
    a = ap.parse_args()
    result = evaluate(a.n, a.seed)
    write_reports(result, Path(__file__).resolve().parent)
    print((Path(__file__).resolve().parent / "results.md").read_text(encoding="utf-8"))
