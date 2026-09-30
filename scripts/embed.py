#!/usr/bin/env python3
"""Embed programs + shortlist + ledger into docs/index.html from the template.

stdlib only. Usage: python3 scripts/embed.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "index.template.html"
VARIANT_B = ROOT / "docs" / "variant-b.template.html"
OUT = ROOT / "docs" / "index.html"
OUT_B = ROOT / "docs" / "variant-b.html"
PROGRAMS = ROOT / "data" / "programs.json"
SHORTLIST = ROOT / "data" / "shortlist.json"
LEDGER = ROOT / "data" / "ledger.jsonl"
DEADLINES = ROOT / "data" / "deadlines.json"


def load_ledger(path: Path) -> list:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def build(tpl_path: Path, out_path: Path, programs: str, shortlist: str, ledger: str, deadlines: str) -> int:
    tpl = tpl_path.read_text(encoding="utf-8")
    markers = ["/*__PROGRAMS_JSON__*/", "/*__SHORTLIST_JSON__*/", "/*__LEDGER_JSON__*/", "/*__DEADLINES_JSON__*/"]
    if any(m not in tpl for m in markers):
        print(f"FAIL: {tpl_path.name} missing embed markers")
        return 1
    html = (
        tpl.replace("/*__PROGRAMS_JSON__*/{}", programs)
        .replace("/*__SHORTLIST_JSON__*/{}", shortlist)
        .replace("/*__LEDGER_JSON__*/[]", ledger)
        .replace("/*__DEADLINES_JSON__*/{}", deadlines)
    )
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html)} bytes)")
    return 0


def main() -> int:
    try:
        programs = PROGRAMS.read_text(encoding="utf-8").strip()
        shortlist = SHORTLIST.read_text(encoding="utf-8").strip() if SHORTLIST.exists() else "{}"
        ledger = json.dumps(load_ledger(LEDGER), ensure_ascii=False, separators=(",", ":"))
        deadlines = DEADLINES.read_text(encoding="utf-8").strip() if DEADLINES.exists() else "{}"
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    rc = build(TEMPLATE, OUT, programs, shortlist, ledger, deadlines)
    if rc:
        return rc
    if VARIANT_B.exists():
        rc = build(VARIANT_B, OUT_B, programs, shortlist, ledger, deadlines)
        if rc:
            return rc

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
