import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import monitor

SETTINGS = dict(monitor.DEFAULTS)
SITE = {"name": "Test", "url": "https://example.test", "keyword": "x"}


def run(results_seq, threshold=1, state=None):
    """Runs process() over several rounds; returns (messages, state)."""
    state = state if state is not None else {"sites": {}}
    sent = []
    settings = {**SETTINGS, "failures_before_alert": threshold}
    for results in results_seq:
        monitor.process([SITE], settings, state, checker=lambda s, st: results, notifier=sent.append)
    return sent, state


UP = {"down": (True, "HTTP 200")}
DOWN = {"down": (False, "HTTP 500")}


def test_first_run_ok_sends_nothing():
    sent, _ = run([UP])
    assert sent == []


def test_first_run_down_notifies():
    sent, _ = run([DOWN])
    assert len(sent) == 1 and sent[0]["title"].startswith("DOWN")


def test_down_notifies_only_once():
    sent, _ = run([UP, DOWN, DOWN, DOWN])
    assert len(sent) == 1


def test_recovery_is_notified():
    sent, _ = run([UP, DOWN, DOWN, UP, UP])
    assert [m["title"].split(":")[0] for m in sent] == ["DOWN", "Recovered"]


def test_threshold_two_ignores_a_hiccup():
    sent, _ = run([UP, DOWN, UP], threshold=2)
    assert sent == []


def test_threshold_two_notifies_after_two_failures():
    sent, _ = run([UP, DOWN, DOWN], threshold=2)
    assert len(sent) == 1


def test_undetermined_result_changes_nothing():
    sent, state = run([DOWN, {"down": (None, "")}])
    assert len(sent) == 1
    assert state["sites"][SITE["url"]]["down"]["status"] == "problem"


def test_failed_notification_is_retried():
    import requests

    state = {"sites": {}}
    settings = {**SETTINGS}

    def broken(_):
        raise requests.ConnectionError("ntfy unreachable")

    monitor.process([SITE], settings, state, checker=lambda s, st: DOWN, notifier=broken)
    assert "down" not in state["sites"][SITE["url"]]
    sent = []
    monitor.process([SITE], settings, state, checker=lambda s, st: DOWN, notifier=sent.append)
    assert len(sent) == 1


def test_warning_has_low_priority():
    sent, _ = run([{"slow": (False, "5s")}])
    assert sent[0]["title"].startswith("Warning") and sent[0]["priority"] == "default"


def test_checks_are_independent():
    sent, _ = run([{"down": (True, ""), "ssl": (False, "3 days")}, {"down": (True, ""), "ssl": (False, "2 days")}])
    assert len(sent) == 1 and "SSL" in sent[0]["title"]


def test_state_stays_stable_with_changing_details():
    import copy

    _, state = run([{"down": (True, "a"), "slow": (True, "0.5s")}])
    first = copy.deepcopy(state)
    _, state = run([{"down": (True, "b"), "slow": (True, "0.9s")}], state=state)
    assert state == first
    _, state = run([DOWN], state=state)
    problem = copy.deepcopy(state)
    _, state = run([{"down": (False, "HTTP 502")}, DOWN], state=state)
    assert state == problem


# --- history ---

def test_history_counts_per_day():
    h = {"sites": {}}
    for up in (True, True, False):
        monitor.process([SITE], SETTINGS, {"sites": {}}, checker=lambda s, st, u=up: {"down": (u, "")},
                        notifier=lambda m: None, history=h, now="2026-10-02T10:00:00Z")
    assert h["sites"][SITE["url"]]["2026-10-02"] == [3, 2]


def test_history_skips_undetermined():
    h = {"sites": {}}
    monitor.record_history(h, "u", None, "2026-10-02")
    assert h["sites"] == {}


def test_history_keeps_max_days():
    h = {"sites": {}}
    for d in range(1, 31):
        monitor.record_history(h, "u", True, f"2026-09-{d:02d}", keep_days=7)
    assert sorted(h["sites"]["u"]) == [f"2026-09-{d:02d}" for d in range(24, 31)]
