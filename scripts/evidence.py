#!/usr/bin/env python3
"""Build per-program evidence snapshots — stdlib only.

Reads data/programs.json (facts + sources + tiers) and data/ledger.jsonl
(status-change history) and writes data/evidence.json: one snapshot per
program with verified facts, recorded history, and an explicit UNKNOWN list
for anything not yet verified. Never invents facts — every fact carries its
named source, checked date, and claim tier.

Usage: python3 scripts/evidence.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ROOT / "data" / "programs.json"
LEDGER = ROOT / "data" / "ledger.jsonl"
OUT = ROOT / "data" / "evidence.json"

# Items we do NOT have evidence for yet — rendered as UNKNOWN, never as facts.
ALWAYS_UNKNOWN = [
    "Funder disbursement history — not yet verified",
    "Prior award cycles and amounts — not yet verified",
    "Funder contact history — not yet verified",
]


def load_ledger(path: Path) -> dict:
    by_program: dict = {}
    if not path.exists():
        return by_program
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        pid = e.get("program_id")
        if not pid:
            continue
        if e.get("concern"):
            event = f"Re-check concern: {e['concern']} (status held at {e.get('old_status')})"
        elif e.get("old_status") != e.get("new_status"):
            event = f"Status changed: {e.get('old_status')} → {e.get('new_status')}"
        else:
            event = f"Re-checked, status unchanged ({e.get('old_status')})"
        by_program.setdefault(pid, []).append({
            "date": e.get("date"),
            "event": event,
            "tier": e.get("tier", "UNKNOWN"),
            "evidence_url": e.get("evidence_url"),
        })
    return by_program


def snapshot(p: dict, history: list) -> dict:
    src = {"source_name": p.get("source_name"), "source_url": p.get("source_url"),
           "checked": p.get("checked"), "tier": p.get("tier")}
    facts = [
        {"fact": f"Status: {p.get('status')} (since {p.get('status_since', '—')})", **src},
        {"fact": f"Deadline: {p.get('deadline', '—')}", **src},
        {"fact": f"Amount: {p.get('amount', '—')}", **src},
    ]
    elig = p.get("eligibility") or []
    if elig:
        facts.append({"fact": f"Eligibility ({len(elig)} criteria listed)", **src})
    unknown = list(ALWAYS_UNKNOWN)
    if not history:
        unknown.insert(0, "Status-change history — not yet verified (no reverify events recorded)")
    return {
        "program_id": p.get("id"),
        "program_name": p.get("name"),
        "facts": facts,
        "history": history,
        "unknown": unknown,
    }


def main() -> int:
    try:
        doc = json.loads(PROGRAMS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load {PROGRAMS}: {exc}")
        return 1
    ledger = load_ledger(LEDGER)
    snapshots = [snapshot(p, ledger.get(p.get("id"), [])) for p in doc.get("programs", [])]
    out = {"generated": str(date.today()), "snapshots": snapshots}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_facts = sum(len(s["facts"]) for s in snapshots)
    n_hist = sum(len(s["history"]) for s in snapshots)
    print(f"Wrote {OUT}: {len(snapshots)} snapshots, {n_facts} facts, {n_hist} history events")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
