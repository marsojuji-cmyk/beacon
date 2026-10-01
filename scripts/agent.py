#!/usr/bin/env python3
"""Beacon Agent — the autonomous loop.

One command runs the whole radar cycle, in dependency order:

  1. reverify  (--respect-cadence)  re-check sources due this run, log flips
  2. match                          automatic opportunity re-scoring
  3. deadlines                      recompute urgency bands
  4. evidence                       rebuild per-program evidence snapshots
  5. discover                       scan listing pages for new candidates
  6. alerts                         deadline crossings, flip surfacing
  7. embed                          rebuild the dashboard HTML
  8. check                          validate the dataset (schema, tiers)

Writes data/agent.json — the run receipt: timestamps, per-step results,
programs checked vs skipped (cadence), flips, alerts raised, candidates found.

A step that fails is recorded, not fatal: the loop finishes every step it
can and reports RESULT: FAIL naming the failed steps. Network failures inside
reverify/discover are already handled per-program (concern events, never
silent drops).

stdlib only. Usage:
  python3 scripts/agent.py [--dry-run] [--limit N] [--timeout SEC]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_JSON = ROOT / "data" / "agent.json"
PROGRAMS = ROOT / "data" / "programs.json"

STEPS: list[tuple[str, list[str]]] = [
    ("reverify", ["python3", "scripts/reverify.py", "--respect-cadence"]),
    ("match", ["python3", "scripts/match.py"]),
    ("deadlines", ["python3", "scripts/deadlines.py"]),
    ("evidence", ["python3", "scripts/evidence.py"]),
    ("discover", ["python3", "scripts/discover.py"]),
    ("alerts", ["python3", "scripts/alerts.py"]),
    ("embed", ["python3", "scripts/embed.py"]),
    ("check", ["python3", "scripts/check.py"]),
]


def parse_args(argv: list[str]) -> dict:
    opts: dict = {"dry_run": False, "limit": None, "timeout": None}
    if "--dry-run" in argv:
        opts["dry_run"] = True
    if "--limit" in argv:
        opts["limit"] = argv[argv.index("--limit") + 1]
    if "--timeout" in argv:
        opts["timeout"] = argv[argv.index("--timeout") + 1]
    return opts


def main() -> int:
    opts = parse_args(sys.argv[1:])
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")

    print(f"Beacon Agent run {run_id}"
          + (" · DRY-RUN" if opts["dry_run"] else ""))
    print(f"Root: {ROOT}")

    step_results: list[dict] = []
    failed: list[str] = []

    for name, cmd in STEPS:
        cmd = list(cmd)
        if name in ("reverify", "discover", "alerts") and opts["dry_run"]:
            cmd.append("--dry-run")
        if name == "reverify":
            if opts["limit"]:
                cmd += ["--limit", str(opts["limit"])]
            if opts["timeout"]:
                cmd += ["--timeout", str(opts["timeout"])]
        print(f"\n=== [{name}] {' '.join(cmd)} ===")
        try:
            proc = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=1200
            )
            rc = proc.returncode
            tail = (proc.stdout or "").strip().splitlines()[-4:]
            note = " | ".join(t for t in tail if t)[:300]
            if proc.stderr.strip():
                note = (note + " STDERR: " + proc.stderr.strip().splitlines()[-1])[:300]
        except subprocess.TimeoutExpired:
            rc, note = 1, "timeout after 1200s"
        except Exception as exc:  # noqa: BLE001
            rc, note = 1, f"harness error: {exc}"
        step_results.append({"step": name, "rc": rc, "note": note})
        status = "ok" if rc == 0 else f"FAILED rc={rc}"
        print(f"[{name}] {status}")

    finished = datetime.now(timezone.utc)

    # Summarize the sweep from the data the steps produced.
    summary: dict = {"programs_total": 0, "checked": 0, "flips": 0,
                     "alerts_active": 0, "discovery_candidates": 0}
    try:
        programs = json.loads(PROGRAMS.read_text(encoding="utf-8"))["programs"]
        summary["programs_total"] = len(programs)
        # Local date: the pipeline scripts stamp with date.today().
        today_local = datetime.now().date().isoformat()
        summary["checked"] = sum(1 for p in programs
                                 if p.get("checked") == today_local)
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    alerts_p = ROOT / "data" / "alerts.json"
    if alerts_p.exists():
        try:
            summary["alerts_active"] = len(
                json.loads(alerts_p.read_text(encoding="utf-8")).get("active", []))
        except (OSError, json.JSONDecodeError):
            pass
    disc_p = ROOT / "data" / "discovery.json"
    if disc_p.exists():
        try:
            summary["discovery_candidates"] = len(
                json.loads(disc_p.read_text(encoding="utf-8")).get("candidates", []))
        except (OSError, json.JSONDecodeError):
            pass

    ok = not failed and all(s["rc"] == 0 for s in step_results)
    for s in step_results:
        if s["rc"] != 0:
            failed.append(s["step"])

    doc = {
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "ok": ok,
        "failed_steps": failed,
        "steps": step_results,
        "summary": summary,
        "schedule": "daily via .github/workflows/agent.yml (13:17 UTC); "
                    "manual: python3 scripts/agent.py",
        "note": ("Autonomous loop receipt. reverify respects per-program "
                 "check_cadence_days; flips and alert crossings are appended "
                 "to data/ledger.jsonl with evidence."),
    }
    if not opts["dry_run"]:
        AGENT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        print(f"\nWrote {AGENT_JSON}")
    else:
        print("\n[dry-run] agent.json not written")

    print(f"\nAgent run {run_id}: "
          f"programs={summary['programs_total']} "
          f"checked_today={summary['checked']} "
          f"alerts_active={summary['alerts_active']} "
          f"candidates={summary['discovery_candidates']}")
    if failed:
        print(f"RESULT: FAIL · failed steps: {', '.join(failed)}")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
