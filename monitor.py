#!/usr/bin/env python3
"""Uptime-monitor: controleert sites en meldt statuswijzigingen via ntfy.sh."""
import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

BASE = Path(__file__).parent
CONFIG_PATH = BASE / "config.yaml"
STATE_PATH = BASE / "state.json"
USER_AGENT = "uptime-monitor/1.0 (+github-actions)"

DEFAULTS = {
    "timeout": 15,
    "slow_seconds": 3,
    "ssl_warn_days": 14,
    "failures_before_alert": 1,
    "ntfy_server": "https://ntfy.sh",
}


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    settings = {**DEFAULTS, **(cfg.get("settings") or {})}
    sites = cfg.get("sites") or []
    if not sites:
        raise SystemExit("config.yaml bevat geen sites")
    return settings, sites


def load_state(path=STATE_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sites": {}}


def save_state(state, path=STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


# --- checks ---------------------------------------------------------------

def ssl_days_left(host, port=443, timeout=10):
    """Dagen tot het certificaat verloopt (kan negatief zijn)."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    expires = ssl.cert_time_to_seconds(cert["notAfter"])
    return (expires - time.time()) / 86400


def check_site(site, s):
    """Geeft {check: (ok, detail)}. ok=None betekent: niet te bepalen, sla over."""
    url = site["url"]
    results = {}
    timeout = site.get("timeout", s["timeout"])
    page_ok = False
    text = ""

    start = time.monotonic()
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        elapsed = time.monotonic() - start
        text = r.text
        if r.status_code == 200:
            results["down"] = (True, "HTTP 200")
            page_ok = True
        else:
            results["down"] = (False, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        elapsed = None
        results["down"] = (False, f"geen antwoord: {type(e).__name__}")

    if page_ok:
        slow = site.get("slow_seconds", s["slow_seconds"])
        results["slow"] = (elapsed <= slow, f"{elapsed:.2f}s (grens {slow}s)")
        keyword = site.get("keyword")
        if keyword:
            found = keyword.lower() in text.lower()
            results["keyword"] = (found, f"trefwoord '{keyword}' {'gevonden' if found else 'NIET gevonden'}")
    else:
        results["slow"] = (None, "")
        results["keyword"] = (None, "")

    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.hostname:
        warn = site.get("ssl_warn_days", s["ssl_warn_days"])
        try:
            days = ssl_days_left(parsed.hostname, parsed.port or 443, timeout)
            results["ssl"] = (days >= warn, f"certificaat nog {days:.0f} dagen geldig (grens {warn})")
        except ssl.SSLCertVerificationError as e:
            results["ssl"] = (False, f"certificaat ongeldig of verlopen: {e.verify_message}")
        except (OSError, ssl.SSLError):
            results["ssl"] = (None, "")  # verbindingsprobleem: dat meldt 'down' al
    return results


# --- statuswijzigingen ----------------------------------------------------

def transition(prev, ok, detail, threshold, now):
    """Bepaalt nieuwe state voor één check en eventueel een event.

    prev: vorige state (of None bij eerste run). Geeft (new_state, event),
    event is None, 'problem' of 'recovery'.
    """
    prev = prev or {"status": "ok", "failures": 0}
    if ok:
        if prev["status"] == "problem":
            return {"status": "ok", "failures": 0, "since": now}, "recovery"
        return {"status": "ok", "failures": 0, **({"since": prev["since"]} if "since" in prev else {})}, None
    if prev["status"] == "problem":
        return prev, None  # ongewijzigd, zodat state.json niet steeds verandert
    failures = prev.get("failures", 0) + 1
    if failures >= threshold:
        return {"status": "problem", "failures": failures, "since": now}, "problem"
    return {**prev, "failures": failures}, None


LABELS = {"down": "Storing", "slow": "Traag", "ssl": "SSL-certificaat", "keyword": "Trefwoord"}


def build_message(site, check, event, detail):
    name = site.get("name", site["url"])
    label = LABELS[check]
    if event == "recovery":
        return {"title": f"Hersteld: {name} ({label})", "body": f"{name} is weer in orde.\n{detail}\n{site['url']}",
                "priority": "default", "tags": "white_check_mark"}
    hard = check in ("down", "keyword")
    return {"title": f"{'STORING' if hard else 'Waarschuwing'}: {name} ({label})",
            "body": f"{detail}\n{site['url']}",
            "priority": "urgent" if check == "down" else ("high" if hard else "default"),
            "tags": "rotating_light" if hard else "warning"}


def send_ntfy(server, topic, msg):
    r = requests.post(
        f"{server.rstrip('/')}/{topic}",
        data=msg["body"].encode("utf-8"),
        headers={"Title": msg["title"].encode("ascii", "replace").decode(),
                 "Priority": msg["priority"], "Tags": msg["tags"]},
        timeout=10,
    )
    r.raise_for_status()


def process(sites, settings, state, checker=check_site, notifier=None):
    """Draait alle checks en werkt state bij. Geeft aantal verstuurde meldingen."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = 0
    for site in sites:
        threshold = site.get("failures_before_alert", settings["failures_before_alert"])
        site_state = state["sites"].setdefault(site["url"], {})
        for check, (ok, detail) in checker(site, settings).items():
            if ok is None:
                continue
            new, event = transition(site_state.get(check), ok, detail, threshold, now)
            if event:
                msg = build_message(site, check, event, detail)
                if notifier is None:
                    print(f"[geen NTFY_TOPIC] zou melden: {msg['title']}", file=sys.stderr)
                    continue  # state niet bijwerken: volgende run opnieuw proberen
                try:
                    notifier(msg)
                    sent += 1
                except requests.RequestException as e:
                    print(f"Melding mislukt ({msg['title']}): {e}", file=sys.stderr)
                    continue
            site_state[check] = new
            print(f"{site.get('name', site['url'])} [{check}]: {'ok' if ok else 'PROBLEEM'} - {detail}")
    return sent


def main():
    settings, sites = load_config()
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    notifier = (lambda m: send_ntfy(settings["ntfy_server"], topic, m)) if topic else None
    if not topic:
        print("Waarschuwing: NTFY_TOPIC is niet ingesteld, er worden geen meldingen verstuurd.", file=sys.stderr)
    state = load_state()
    state.setdefault("sites", {})
    process(sites, settings, state, notifier=notifier)
    save_state(state)


if __name__ == "__main__":
    main()
