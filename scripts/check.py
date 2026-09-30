#!/usr/bin/env python3
"""Beacon radar checker — stdlib only.
Validates data/programs.json schema, reports status counts, and flags
entries whose `checked` date is older than STALE_DAYS (default 30).
Exit 0 = valid; exit 1 = schema errors. Stale entries are warnings, not errors.
Usage: python3 scripts/check.py [--stale-days N]
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "programs.json"

REQUIRED = {"id", "name", "region", "type", "amount", "status", "status_since",
            "eligibility", "deadline", "source_name", "source_url", "checked", "tier"}
REGIONS = {"Calgary", "Alberta", "Canada"}
STATUSES = {"open", "paused", "closed"}
TIERS = {"VERIFIED", "INFERRED"}


def main() -> int:
    stale_days = 30
    if "--stale-days" in sys.argv:
        stale_days = int(sys.argv[sys.argv.index("--stale-days") + 1])

    try:
        doc = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load {DATA}: {exc}")
        return 1

    programs = doc.get("programs", [])
    errors, warnings = [], []
    seen_ids = set()
    today = date.today()

    for i, p in enumerate(programs):
        tag = p.get("id", f"#{i}")
        missing = REQUIRED - set(p)
        if missing:
            errors.append(f"{tag}: missing fields {sorted(missing)}")
        if tag in seen_ids:
            errors.append(f"{tag}: duplicate id")
        seen_ids.add(tag)
        if p.get("region") not in REGIONS:
            errors.append(f"{tag}: bad region {p.get('region')!r}")
        if p.get("status") not in STATUSES:
            errors.append(f"{tag}: bad status {p.get('status')!r}")
        if p.get("tier") not in TIERS:
            errors.append(f"{tag}: bad tier {p.get('tier')!r}")
        try:
            checked = datetime.strptime(p["checked"], "%Y-%m-%d").date()
            age = (today - checked).days
            if age > stale_days:
                warnings.append(f"{tag}: checked {age}d ago (> {stale_days}d) — re-verify")
        except (KeyError, ValueError):
            errors.append(f"{tag}: bad checked date {p.get('checked')!r}")

    counts = {}
    for p in programs:
        counts[p.get("status")] = counts.get(p.get("status"), 0) + 1

    print(f"Beacon check — {len(programs)} programs, generated {doc.get('generated')}")
    print(f"Status: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS" + (" (with stale warnings)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
