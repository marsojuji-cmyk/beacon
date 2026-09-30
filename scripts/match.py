#!/usr/bin/env python3
"""Beacon eligibility engine — stdlib only.

Reads data/profile.yaml + data/programs.json, scores each program as:
  eligible-now | blocked (with single unblock step) | not-for-him

Writes data/shortlist.json: shortlist + unlock roadmap
  (incorporate → unlocks X; first R&D dollar → unlocks SR&ED stack).

Usage: python3 scripts/match.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ROOT / "data" / "programs.json"
PROFILE = ROOT / "data" / "profile.yaml"
OUT = ROOT / "data" / "shortlist.json"


def parse_simple_yaml(text: str) -> dict:
    """Minimal YAML subset: key: value, key: [list], key: > folded block."""
    data: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == ">" or rest == "|":
            block: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                if lines[i].strip() == "" and block:
                    block.append("")
                else:
                    block.append(lines[i][2:] if lines[i].startswith("  ") else lines[i])
                i += 1
            data[key] = " ".join(s.strip() for s in block if s.strip())
            continue
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            data[key] = [x.strip() for x in inner.split(",")] if inner else []
            i += 1
            continue
        if rest.lower() in ("true", "false"):
            data[key] = rest.lower() == "true"
            i += 1
            continue
        if re.fullmatch(r"-?\d+", rest):
            data[key] = int(rest)
            i += 1
            continue
        if (rest.startswith('"') and rest.endswith('"')) or (rest.startswith("'") and rest.endswith("'")):
            data[key] = rest[1:-1]
            i += 1
            continue
        data[key] = rest
        i += 1
    return data


def _elig_blob(p: dict) -> str:
    return " ".join(p.get("eligibility") or []).lower() + " " + (p.get("name") or "").lower()


def score(p: dict, profile: dict) -> dict:
    """Return {id, name, verdict, unblock, reason, status, requires_incorporation}."""
    pid = p["id"]
    name = p["name"]
    status = p.get("status", "open")
    needs_corp = bool(p.get("requires_incorporation"))
    blob = _elig_blob(p)
    incorp = bool(profile.get("incorporated"))
    rnd_spend = bool(profile.get("rnd_spend"))
    rnd_payroll = bool(profile.get("rnd_payroll"))
    stage = str(profile.get("stage", "")).lower()

    base = {
        "id": pid,
        "name": name,
        "status": status,
        "requires_incorporation": needs_corp,
        "region": p.get("region"),
        "type": p.get("type"),
        "amount": p.get("amount"),
        "tier": p.get("tier"),
        "checked": p.get("checked"),
        "source_url": p.get("source_url"),
    }

    # Hard outs — not for this profile regardless of incorporation.
    if status == "closed":
        return {**base, "verdict": "not-for-him", "unblock": None,
                "reason": "Cycle closed / award already made — watch next intake."}
    if p.get("type") == "signal" or "scaleup" in blob or "too large for sme" in blob:
        return {**base, "verdict": "not-for-him", "unblock": None,
                "reason": "Growth/scaleup capital — not pre-revenue founder territory."}
    if "defence" in blob or "dual-use" in blob or "di assist" in name.lower():
        return {**base, "verdict": "not-for-him", "unblock": None,
                "reason": "Defence / dual-use lane — outside current builder profile."}
    if status == "paused":
        return {**base, "verdict": "not-for-him", "unblock": None,
                "reason": "Intake halted — no application path until the pause lifts."}

    # Tax-credit / R&D-spend stack: needs corp + first eligible R&D dollar.
    if pid == "ieg-sred" or ("sr&ed" in blob and "corporation" in blob):
        if not incorp:
            return {**base, "verdict": "blocked", "unblock": "incorporate",
                    "reason": "Alberta corp + eligible R&D spend required; incorporate first."}
        if not rnd_spend:
            return {**base, "verdict": "blocked", "unblock": "first-rnd-dollar",
                    "reason": "Incorporated but no eligible R&D spend yet — first R&D dollar unlocks the stack."}
        return {**base, "verdict": "eligible-now", "unblock": None,
                "reason": "Corp + R&D spend present — claim path open (record-keeping required)."}

    # Programs that explicitly need a dedicated R&D hire / payroll.
    if "dedicated r&d" in blob or "r&d associate" in blob:
        if not incorp:
            return {**base, "verdict": "blocked", "unblock": "incorporate",
                    "reason": "Requires incorporated SME; then an R&D Associate hire."}
        if not rnd_payroll:
            return {**base, "verdict": "blocked", "unblock": "rnd-associate-hire",
                    "reason": "Incorporated but needs a dedicated R&D Associate on payroll."}
        return {**base, "verdict": "eligible-now", "unblock": None,
                "reason": "Incorp + R&D Associate path satisfied."}

    # Mitacs: incorp + incubator hosting.
    if "mitacs" in pid or "mitacs" in name.lower():
        if not incorp:
            return {**base, "verdict": "blocked", "unblock": "incorporate",
                    "reason": "Needs incorporated startup hosted in a Mitacs-approved incubator."}
        return {**base, "verdict": "blocked", "unblock": "mitacs-incubator-host",
                "reason": "Incorporate alone is not enough — need Mitacs-approved incubator hosting."}

    # Generic incorporation gate.
    if needs_corp and not incorp:
        return {**base, "verdict": "blocked", "unblock": "incorporate",
                "reason": "Open, but requires a Canadian/Alberta incorporated company."}

    # Ecosystem / watch items that don't need incorp — eligible as an observer/applicant path.
    if p.get("type") == "ecosystem":
        return {**base, "verdict": "eligible-now", "unblock": None,
                "reason": "Ecosystem infrastructure — founder-facing via RINs; no incorporation bar."}

    # Open, no incorp required, fits stage.
    if not needs_corp and status == "open":
        if stage == "pre-revenue" and "commercial traction" in blob:
            return {**base, "verdict": "not-for-him", "unblock": None,
                    "reason": "Wants commercial traction — pre-revenue profile does not fit."}
        return {**base, "verdict": "eligible-now", "unblock": None,
                "reason": "Open and does not require incorporation for this profile."}

    # Incorporated-required but profile is incorporated.
    if needs_corp and incorp and status == "open":
        return {**base, "verdict": "eligible-now", "unblock": None,
                "reason": "Open and incorporation requirement met."}

    return {**base, "verdict": "not-for-him", "unblock": None,
            "reason": "No clean match path under current profile."}


def unlock_roadmap(scored: list[dict], profile: dict) -> list[dict]:
    """Build the unlock roadmap from blocked items + known next gates."""
    by_unblock: dict[str, list[str]] = {}
    for s in scored:
        if s["verdict"] != "blocked" or not s.get("unblock"):
            continue
        by_unblock.setdefault(s["unblock"], []).append(s["id"])

    labels = {
        "incorporate": "Incorporate (Alberta/Canada for-profit) → unlocks these open programs",
        "first-rnd-dollar": "First eligible R&D dollar → unlocks SR&ED / IEG stack",
        "rnd-associate-hire": "Hire a dedicated R&D Associate → unlocks Industry R&D Associates",
        "mitacs-incubator-host": "Land Mitacs-approved incubator hosting → unlocks Mitacs Accelerate",
    }
    # Prospective gate: once incorporated, SR&ED still needs a first R&D dollar.
    # Surface it even when the current block is 'incorporate', so the roadmap
    # always shows the two-step path the brief names.
    if not profile.get("rnd_spend"):
        sred_ids = [s["id"] for s in scored if s["id"] == "ieg-sred" or "sr&ed" in (s.get("name") or "").lower()]
        if sred_ids and "first-rnd-dollar" not in by_unblock:
            by_unblock["first-rnd-dollar"] = sred_ids

    order = ["incorporate", "first-rnd-dollar", "rnd-associate-hire", "mitacs-incubator-host"]
    road = []
    for key in order:
        if key not in by_unblock:
            continue
        road.append({
            "step": key,
            "label": labels.get(key, key),
            "unlocks": by_unblock[key],
            "count": len(by_unblock[key]),
        })
    for key, ids in by_unblock.items():
        if key in order:
            continue
        road.append({"step": key, "label": key, "unlocks": ids, "count": len(ids)})
    return road


def main() -> int:
    try:
        doc = json.loads(PROGRAMS.read_text(encoding="utf-8"))
        profile = parse_simple_yaml(PROFILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    scored = [score(p, profile) for p in doc.get("programs", [])]
    counts = {}
    for s in scored:
        counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1

    shortlist = [s for s in scored if s["verdict"] == "eligible-now"]
    blocked = [s for s in scored if s["verdict"] == "blocked"]
    out = {
        "generated": date.today().isoformat(),
        "profile": {
            "identity": profile.get("identity"),
            "location": profile.get("location"),
            "sector": profile.get("sector"),
            "stage": profile.get("stage"),
            "incorporated": profile.get("incorporated"),
            "rnd_spend": profile.get("rnd_spend"),
            "rnd_payroll": profile.get("rnd_payroll"),
        },
        "counts": counts,
        "shortlist": shortlist,
        "blocked": blocked,
        "not_for_him": [s for s in scored if s["verdict"] == "not-for-him"],
        "unlock_roadmap": unlock_roadmap(scored, profile),
        "all": scored,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Beacon match — {len(scored)} programs · {out['generated']}")
    print("Verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("Shortlist:")
    for s in shortlist:
        print(f"  + {s['id']}: {s['reason']}")
    print("Unlock roadmap:")
    for step in out["unlock_roadmap"]:
        print(f"  → {step['step']} unlocks {step['count']}: {', '.join(step['unlocks'])}")
    print(f"Wrote {OUT}")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
