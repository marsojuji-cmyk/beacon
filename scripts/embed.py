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
OUT = ROOT / "docs" / "index.html"
PROGRAMS = ROOT / "data" / "programs.json"
SHORTLIST = ROOT / "data" / "shortlist.json"
LEDGER = ROOT / "data" / "ledger.jsonl"


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


def main() -> int:
    try:
        tpl = TEMPLATE.read_text(encoding="utf-8")
        programs = PROGRAMS.read_text(encoding="utf-8").strip()
        shortlist = SHORTLIST.read_text(encoding="utf-8").strip() if SHORTLIST.exists() else "{}"
        ledger = json.dumps(load_ledger(LEDGER), ensure_ascii=False, separators=(",", ":"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    if "/*__PROGRAMS_JSON__*/" not in tpl or "/*__SHORTLIST_JSON__*/" not in tpl or "/*__LEDGER_JSON__*/" not in tpl:
        print("FAIL: template missing embed markers")
        return 1

    html = (
        tpl.replace("/*__PROGRAMS_JSON__*/{}", programs)
        .replace("/*__SHORTLIST_JSON__*/{}", shortlist)
        .replace("/*__LEDGER_JSON__*/[]", ledger)
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({len(html)} bytes)")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
