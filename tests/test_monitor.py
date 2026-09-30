import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import monitor

SETTINGS = dict(monitor.DEFAULTS)
SITE = {"name": "Test", "url": "https://example.test", "keyword": "x"}


def run(results_seq, threshold=1, state=None):
    """Draait process() over meerdere rondes; geeft (berichten, state)."""
    state = state if state is not None else {"sites": {}}
    sent = []
    settings = {**SETTINGS, "failures_before_alert": threshold}
    for results in results_seq:
        monitor.process([SITE], settings, state, checker=lambda s, st: results, notifier=sent.append)
    return sent, state


UP = {"down": (True, "HTTP 200")}
DOWN = {"down": (False, "HTTP 500")}


def test_eerste_run_ok_geeft_geen_melding():
    sent, _ = run([UP])
    assert sent == []


def test_eerste_run_down_meldt():
    sent, _ = run([DOWN])
    assert len(sent) == 1 and sent[0]["title"].startswith("STORING")


def test_down_meldt_maar_een_keer():
    sent, _ = run([UP, DOWN, DOWN, DOWN])
    assert len(sent) == 1


def test_herstel_wordt_gemeld():
    sent, _ = run([UP, DOWN, DOWN, UP, UP])
    assert [m["title"].split(":")[0] for m in sent] == ["STORING", "Hersteld"]


def test_drempel_twee_negeert_een_hikje():
    sent, _ = run([UP, DOWN, UP], threshold=2)
    assert sent == []


def test_drempel_twee_meldt_na_twee_fouten():
    sent, _ = run([UP, DOWN, DOWN], threshold=2)
    assert len(sent) == 1


def test_onbepaald_resultaat_wijzigt_niets():
    sent, state = run([DOWN, {"down": (None, "")}])
    assert len(sent) == 1
    assert state["sites"][SITE["url"]]["down"]["status"] == "problem"


def test_mislukte_melding_wordt_opnieuw_geprobeerd():
    import requests

    state = {"sites": {}}
    settings = {**SETTINGS}

    def kapot(_):
        raise requests.ConnectionError("ntfy onbereikbaar")

    monitor.process([SITE], settings, state, checker=lambda s, st: DOWN, notifier=kapot)
    assert "down" not in state["sites"][SITE["url"]]
    sent = []
    monitor.process([SITE], settings, state, checker=lambda s, st: DOWN, notifier=sent.append)
    assert len(sent) == 1


def test_waarschuwing_heeft_lage_prioriteit():
    sent, _ = run([{"slow": (False, "5s")}])
    assert sent[0]["title"].startswith("Waarschuwing") and sent[0]["priority"] == "default"


def test_checks_zijn_onafhankelijk():
    sent, _ = run([{"down": (True, ""), "ssl": (False, "3 dagen")}, {"down": (True, ""), "ssl": (False, "2 dagen")}])
    assert len(sent) == 1 and "SSL" in sent[0]["title"]


def test_state_blijft_stabiel_bij_wisselende_details():
    import copy

    _, state = run([{"down": (True, "a"), "slow": (True, "0.5s")}])
    eerste = copy.deepcopy(state)
    _, state = run([{"down": (True, "b"), "slow": (True, "0.9s")}], state=state)
    assert state == eerste
    _, state = run([DOWN], state=state)
    probleem = copy.deepcopy(state)
    _, state = run([{"down": (False, "HTTP 502")}, DOWN], state=state)
    assert state == probleem
