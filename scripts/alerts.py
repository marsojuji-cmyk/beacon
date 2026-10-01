#!/usr/bin/env python3
"""Beacon alerts — deadline threshold crossings and status-flip surfacing.

Reads data/programs.json, data/deadlines.json, data/alerts.json (previous run)
and data/ledger.jsonl. Computes the current alert conditions:

  - deadline_imminent: program newly within 30 days of a real deadline_date
  - deadline_overdue: program newly past its deadline_date
  - status_flip:    a ledger flip event dated today not yet surfaced
  - discovery:      new UNKNOWN candidates since the last run (digest)

New alerts are appended to data/ledger.jsonl as provenance-bearing events
(kind="alert") and written to data/alerts.json. Conditions that clear get
resolved=dated rather than deleted — the ledger discipline.

stdlib only. Usage: python3 scripts/alerts.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ROOT / "data" / "programs.json"
DEADLINES = ROOT / "data" / "deadlines.json"
ALERTS = ROOT / "data" / "alerts.json"
DISCOVERY = ROOT / "data" / "discovery.json"
LEDGER = ROOT / "data" / "ledger.jsonl"

FLIP_ALERT_TTL_DAYS = 14
DISCOVERY_ALERT_TTL_DAYS = 7


def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def alert_id(kind: str, program_id: str, extra: str = "") -> str:
    base = f"{kind}:{program_id}"
    return f"{base}:{extra}" if extra else base


def main() -> int:
    dry = "--dry-run" in sys.argv[1:]
    today = date.today().isoformat()

    try:
        programs = {p["id"]: p for p in
                    json.loads(PROGRAMS.read_text(encoding="utf-8"))["programs"]}
        deadlines = {i["id"]: i for i in
                     json.loads(DEADLINES.read_text(encoding="utf-8"))["items"]}
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL: {exc}")
        return 1

    prev = {"active": [], "resolved": []}
    if ALERTS.exists():
        try:
            prev = json.loads(ALERTS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    active = {a["id"]: a for a in prev.get("active", [])}
    resolved = list(prev.get("resolved", []))
    ledger_events: list[dict] = []
    raised = 0

    def raise_alert(aid: str, kind: str, pid: str, message: str, tier: str,
                    evidence_url: str) -> None:
        nonlocal raised
        if aid in active:
            return
        active[aid] = {
            "id": aid, "kind": kind, "program_id": pid,
            "message": message, "raised": today, "tier": tier,
            "resolved": None,
        }
        raised += 1
        p = programs.get(pid, {})
        ledger_events.append({
            "date": today,
            "program_id": pid,
            "old_status": p.get("status"),
            "new_status": p.get("status"),
            "evidence_url": evidence_url or p.get("source_url", ""),
            "tier": tier,
            "kind": "alert",
            "alert_kind": kind,
            "message": message,
        })

    def resolve(aid: str) -> None:
        a = active.pop(aid, None)
        if a:
            a["resolved"] = today
            resolved.append(a)

    print(f"Beacon alerts — {len(programs)} programs · {today}"
          + (" · DRY-RUN" if dry else ""))

    # 1. Deadline threshold crossings (only for real dated deadlines).
    for pid, d in deadlines.items():
        p = programs.get(pid)
        if not p or p.get("status") != "open":
            # Closed/paused programs clear any deadline alert.
            resolve(alert_id("deadline_imminent", pid))
            resolve(alert_id("deadline_overdue", pid))
            continue
        days = d.get("days_until")
        dd = d.get("deadline_date")
        if days is None or not dd:
            continue
        if days < 0:
            resolve(alert_id("deadline_imminent", pid))
            raise_alert(
                alert_id("deadline_overdue", pid), "deadline_overdue", pid,
                f"Deadline passed ({d.get('deadline')}) — verify whether intake "
                f"reopened or the program closed.",
                p.get("tier", "INFERRED"), p.get("source_url", ""))
        elif days <= 30:
            resolve(alert_id("deadline_overdue", pid))
            raise_alert(
                alert_id("deadline_imminent", pid), "deadline_imminent", pid,
                f"Deadline in {days} days ({d.get('deadline')}) — start the "
                f"application now if eligible.",
                p.get("tier", "INFERRED"), p.get("source_url", ""))
        else:
            resolve(alert_id("deadline_imminent", pid))
            resolve(alert_id("deadline_overdue", pid))

    # 2. Status flips surfaced from today's ledger events.
    for e in load_ledger(LEDGER):
        if e.get("date") != today or e.get("kind") == "alert":
            continue
        old, new = e.get("old_status"), e.get("new_status")
        if not old or old == new:
            continue
        pid = e.get("program_id", "?")
        p = programs.get(pid, {})
        raise_alert(
            alert_id("status_flip", pid, f"{old}-{new}-{today}"),
            "status_flip", pid,
            f"Status changed {old} → {new} (evidence: {e.get('evidence_url', '')[:80]}).",
            e.get("tier", "INFERRED"), e.get("evidence_url", ""))

    # 3. Discovery digest — one alert per run while fresh candidates exist.
    new_cands = []
    if DISCOVERY.exists():
        try:
            doc = json.loads(DISCOVERY.read_text(encoding="utf-8"))
            new_cands = [c for c in doc.get("candidates", [])
                         if c.get("discovered") == today]
        except (OSError, json.JSONDecodeError):
            pass
    if new_cands:
        raise_alert(
            alert_id("discovery", "queue", today), "discovery", "queue",
            f"{len(new_cands)} new UNVERIFIED candidate(s) in the discovery "
            f"queue — verify against a primary source before tracking.",
            "UNKNOWN", "")
    # Expire informational alerts past their TTL.
    for aid, a in list(active.items()):
        try:
            y, m, d = (int(x) for x in a["raised"].split("-"))
            age = (date.today() - date(y, m, d)).days
        except ValueError:
            age = 0
        ttl = (FLIP_ALERT_TTL_DAYS if a["kind"] == "status_flip"
               else DISCOVERY_ALERT_TTL_DAYS if a["kind"] == "discovery"
               else None)
        if ttl is not None and age >= ttl:
            resolve(aid)

    doc = {
        "generated": today,
        "active": sorted(active.values(), key=lambda a: a["raised"]),
        "resolved": sorted(resolved, key=lambda a: a.get("resolved") or "",
                           reverse=True)[:50],
        "note": ("Alerts are derived, not primary claims. Deadline alerts fire "
                 "only on real deadline_date values; flips come from ledger "
                 "events; discovery items stay UNKNOWN until verified."),
    }
    if dry:
        print(f"[dry-run] would write {ALERTS} "
              f"({len(active)} active, {raised} raised, "
              f"{len(ledger_events)} ledger events)")
    else:
        ALERTS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        if ledger_events:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for e in ledger_events:
                    fh.write(json.dumps(e, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        print(f"Wrote {ALERTS}")

    kinds: dict[str, int] = {}
    for a in active.values():
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    print(f"RESULT: PASS · raised={raised} active={len(active)} {kinds}")
    if raised:
        for a in active.values():
            if a["raised"] == today:
                print(f"  NEW [{a['kind']}] {a['program_id']}: {a['message'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
