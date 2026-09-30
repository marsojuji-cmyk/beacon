#!/usr/bin/env python3
"""Deadline urgency engine for Beacon.

Reads data/programs.json, computes days-until for programs with a real
deadline_date, and writes data/deadlines.json — the machine-readable feed
that digests, crons, and the Tuesday opportunity scans consume.

Urgency bands: overdue / imminent (<=30d) / upcoming (<=90d) / later / ongoing.
Rolling / continuous-intake programs carry deadline_date=null and are 'ongoing'.

stdlib only. Usage: python3 scripts/deadlines.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ROOT / "data" / "programs.json"
OUT = ROOT / "data" / "deadlines.json"


def urgency_for(days: int | None) -> str:
    if days is None:
        return "ongoing"
    if days < 0:
        return "overdue"
    if days <= 30:
        return "imminent"
    if days <= 90:
        return "upcoming"
    return "later"


def main() -> int:
    try:
        programs = json.loads(PROGRAMS.read_text(encoding="utf-8"))["programs"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL: {exc}")
        return 1

    today = date.today()
    items = []
    for p in programs:
        dd = p.get("deadline_date")
        days = None
        if dd:
            try:
                y, m, d = (int(x) for x in dd.split("-"))
                days = (date(y, m, d) - today).days
            except ValueError:
                days = None  # malformed date -> treat as ongoing, never invent
        items.append(
            {
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "deadline": p.get("deadline"),
                "deadline_date": dd,
                "days_until": days,
                "urgency": urgency_for(days),
                "tier": p.get("tier"),
            }
        )

    OUT.write_text(
        json.dumps(
            {"generated": today.isoformat(), "items": items},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Digest snippet: the lines a cron or scan would lift verbatim.
    flagged = [i for i in items if i["urgency"] in ("overdue", "imminent", "upcoming")]
    print(f"Wrote {OUT} ({len(items)} programs, {len(flagged)} flagged)")
    if flagged:
        print("--- digest ---")
        for i in sorted(flagged, key=lambda x: (x["days_until"] is None, x["days_until"])):
            when = f"{i['days_until']} days" if i["days_until"] is not None else "?"
            print(f"[{i['urgency'].upper()}] {i['name']} — {when} (deadline: {i['deadline']})")
    else:
        print("--- digest ---\nNo dated deadlines within 90 days.")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
