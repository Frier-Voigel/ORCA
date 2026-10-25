"""Eval harness check. Run: pytest   (or: python tests/test_eval.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.run import POLICIES, evaluate


def test_ai_beats_no_action():
    result = evaluate(8)
    s = result["summary"]
    assert set(s) == set(POLICIES) and len(result["scenarios"]) == 8
    assert s["ai_recommended"]["downtime_s"] < s["no_action"]["downtime_s"]
    assert s["ai_recommended"]["downtime_s"] <= s["naive_restart"]["downtime_s"]
    assert evaluate(8)["summary"] == s  # fixed seeds -> repeatable numbers


if __name__ == "__main__":
    test_ai_beats_no_action()
    print("ok test_ai_beats_no_action")
