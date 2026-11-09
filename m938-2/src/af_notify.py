#!/usr/bin/env python3
"""One call to raise an AF alert: a GitHub Issue labelled `af-alert`.

Watchdogs are silent log writers; that means a first sale or an expired session
could go unnoticed. Every watchdog routes its notable events through here so the
event lands where K actually looks — the brain repo's issue list — with no email
and no human in the loop.

Idempotent per slug (af_alert.py updates the existing open issue).
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALERT = "/workspace/project/AX_MASTER_BRAIN/tools/af_alert.py"
LOG = "/workspace/.af-notify.log"


def _log(msg: str) -> None:
    import time
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(slug: str, title: str, body: str, label: str = "af-alert") -> bool:
    """Open/update the af-alert issue for this slug. Returns True on success."""
    if not os.path.exists(ALERT):
        _log("af_alert.py missing at %s" % ALERT)
        return False
    env = dict(os.environ)
    for p in (HERE, os.path.join(HERE, "..", "project", "AX_MASTER_BRAIN", "tools")):
        env["PYTHONPATH"] = p + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run([sys.executable or "python3", ALERT, "--slug", slug, "--title", title,
                            "--body", body, "--label", label],
                           capture_output=True, text=True, timeout=60, env=env)
    except Exception as e:  # noqa: BLE001
        _log("alert %s failed: %s" % (slug, e))
        return False
    out = (r.stdout or "").strip()
    _log("alert %s -> %s" % (slug, out or r.stderr.strip()[:160]))
    return r.returncode == 0 and ("opened issue" in out or "updated issue" in out)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("usage: af_notify.py <slug> <title> <body>")
    ok = alert(sys.argv[1], sys.argv[2], sys.argv[3])
    print("ok" if ok else "failed")
    sys.exit(0 if ok else 1)
