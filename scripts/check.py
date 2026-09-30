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
EVIDENCE_PATH = ROOT / "data" / "evidence.json"
PIPELINE_TEMPLATE = ROOT / "data" / "pipeline.template.json"

REQUIRED = {"id", "name", "region", "type", "amount", "status", "status_since",
            "eligibility", "deadline", "source_name", "source_url", "checked", "tier"}
REGIONS = {"Calgary", "Alberta", "Canada"}
STATUSES = {"open", "paused", "closed"}
TIERS = {"VERIFIED", "INFERRED"}
EVIDENCE_TIERS = {"VERIFIED", "INFERRED", "GUESSED", "UNKNOWN"}
PIPELINE_STAGES = {"prospecting", "preparing", "applied", "in-review", "awarded", "declined"}


def check_evidence(program_ids: set, errors: list, warnings: list) -> None:
    """Validate data/evidence.json — every fact needs a named source, a checked
    date, and a claim tier; program ids must match programs.json."""
    if not EVIDENCE_PATH.exists():
        errors.append("evidence.json missing — run scripts/evidence.py")
        return
    try:
        doc = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"evidence.json unreadable: {exc}")
        return
    for i, s in enumerate(doc.get("snapshots", [])):
        tag = s.get("program_id", f"snapshot#{i}")
        if tag not in program_ids:
            errors.append(f"evidence {tag}: unknown program id")
        for f in s.get("facts", []):
            for field in ("fact", "source_name", "source_url", "checked", "tier"):
                if not f.get(field):
                    errors.append(f"evidence {tag}: fact missing {field}: {str(f.get('fact'))[:60]!r}")
            if f.get("tier") not in EVIDENCE_TIERS:
                errors.append(f"evidence {tag}: bad fact tier {f.get('tier')!r}")
        for h in s.get("history", []):
            if not h.get("date") or not h.get("event"):
                errors.append(f"evidence {tag}: history event missing date/event")
        if not s.get("unknown"):
            warnings.append(f"evidence {tag}: no UNKNOWN list — every dossier should name what is unverified")


def check_pipeline_template(program_ids: set, errors: list) -> None:
    """Validate data/pipeline.template.json — schema reference for the private
    pipeline.json. Entries must be marked sample and stages must be valid."""
    if not PIPELINE_TEMPLATE.exists():
        errors.append("pipeline.template.json missing")
        return
    try:
        doc = json.loads(PIPELINE_TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"pipeline.template.json unreadable: {exc}")
        return
    if not doc.get("sample"):
        errors.append("pipeline.template.json: top-level sample flag missing")
    stages = set(doc.get("stages", []))
    if stages != PIPELINE_STAGES:
        errors.append(f"pipeline.template.json: stages {sorted(stages)} != {sorted(PIPELINE_STAGES)}")
    for a in doc.get("applications", []):
        tag = a.get("id", "?")
        for field in ("id", "program_id", "stage", "entered_stage"):
            if not a.get(field):
                errors.append(f"pipeline {tag}: missing {field}")
        if a.get("stage") not in PIPELINE_STAGES:
            errors.append(f"pipeline {tag}: bad stage {a.get('stage')!r}")
        if a.get("program_id") not in program_ids:
            errors.append(f"pipeline {tag}: unknown program_id {a.get('program_id')!r}")
        if not a.get("sample"):
            errors.append(f"pipeline {tag}: template entry not marked sample")
    # Private data must never be committed.
    if (ROOT / "data" / "pipeline.json").exists():
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
        if "data/pipeline.json" not in gi:
            errors.append("data/pipeline.json exists but is not gitignored — private data leak risk")


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

    check_evidence(seen_ids, errors, warnings)
    check_pipeline_template(seen_ids, errors)

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
