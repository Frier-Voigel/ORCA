"""Cascade checks. Run: pytest   (or: python tests/test_cascade.py)"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from analysis.cascade import forecast

GRAPH = json.loads((C.MOCKS_DIR / "graph.json").read_text(encoding="utf-8"))


def _preds(**probs):
    return {"ts": 1, "predictions": [
        {"service": s, "fail_prob": probs.get(s, 0.0), "horizon_s": 300, "top_signals": []} for s in C.SERVICES]}


def test_spreads_upstream_in_order():
    out = forecast(GRAPH, _preds(**{"db-primary": 1.0}))
    by = {(p["from"], p["to"]): p for p in out["paths"]}
    assert by[("db-primary", "order-service")]["prob"] > 0.7
    assert by[("order-service", "api-gateway")]["eta_s"] > by[("db-primary", "order-service")]["eta_s"]
    assert out["blast_radius"]["db-primary"] >= 3
    assert all(p["to"] != "db-primary" for p in out["paths"])  # nothing causes the root


def test_contract_and_ranges():
    mock = json.loads((C.MOCKS_DIR / "cascade.json").read_text(encoding="utf-8"))
    out = forecast(GRAPH, _preds(**{"db-primary": 0.9}))
    assert set(out) == set(mock) and set(out["paths"][0]) == set(mock["paths"][0])
    assert all(0 <= p["prob"] <= 1 and p["eta_s"] >= 0 for p in out["paths"])


def test_no_risk_no_paths_and_deterministic():
    assert forecast(GRAPH, _preds())["paths"] == []
    a, b = forecast(GRAPH, _preds(cache=0.6)), forecast(GRAPH, _preds(cache=0.6))
    assert a == b


def test_fast():
    start = time.perf_counter()
    forecast(GRAPH, _preds(**{"db-primary": 1.0}))
    assert time.perf_counter() - start < 0.5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
