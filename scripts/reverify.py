#!/usr/bin/env python3
"""Beacon self-verification — stdlib urllib only.

Fetches each program's source_url, detects status flips via keyword heuristics
+ HTTP status, updates programs.json, appends events to data/ledger.jsonl.

Never drops a program on fetch failure: keeps old status, marks tier concern
(downgrades VERIFIED → INFERRED), logs a ledger event.

Usage:
  python3 scripts/reverify.py [--dry-run] [--timeout SEC] [--limit N]
                             [--respect-cadence]
  --respect-cadence skips programs checked more recently than their
  check_cadence_days (days). The agent loop always passes it.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "programs.json"
LEDGER = ROOT / "data" / "ledger.jsonl"

UA = "BeaconRadar/2.0 (+https://marcusrichards.dev; funding-radar reverify; stdlib)"
CLOSED_RE = re.compile(
    r"\b(applications?\s+closed|intake\s+closed|no\s+longer\s+accepting|"
    r"program\s+(has\s+)?ended|permanently\s+closed|awarded\s+for\s+\d{4}|"
    r"funding\s+round\s+complete|closed\s+to\s+new)\b",
    re.I,
)
PAUSED_RE = re.compile(
    r"\b(paused|halted|suspended|temporarily\s+closed|on\s+hold|"
    r"intake\s+(is\s+)?(paused|halted)|no\s+current\s+intake|"
    r"not\s+currently\s+accepting)\b",
    re.I,
)
OPEN_RE = re.compile(
    r"\b(now\s+open|accepting\s+applications|apply\s+now|"
    r"open\s+for\s+(applications|intake)|continuous\s+intake|"
    r"applications?\s+(are\s+)?open|currently\s+accepting|"
    r"rolling\s+(intake|applications)|call\s+for\s+proposals\s+open)\b",
    re.I,
)


def parse_args(argv: list[str]) -> dict:
    dry = "--dry-run" in argv
    respect_cadence = "--respect-cadence" in argv
    timeout = 20.0
    limit = None
    if "--timeout" in argv:
        timeout = float(argv[argv.index("--timeout") + 1])
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    return {"dry_run": dry, "timeout": timeout, "limit": limit,
            "respect_cadence": respect_cadence}


def is_primary(source_name: str) -> bool:
    return "primary" in (source_name or "").lower()


def _name_anchors(name: str) -> list[str]:
    """Distinctive tokens from a program name for proximity checks."""
    stop = {
        "the", "and", "for", "of", "a", "an", "to", "in", "on", "via", "or",
        "program", "fund", "initiative", "canada", "alberta", "calgary",
        "grant", "grants", "stack", "access", "assist", "digital", "industry",
        "regional", "innovation", "networks", "renewal", "company", "small",
        "business", "tech", "growth", "canadian", "compute",
    }
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9+&/-]{2,}", name)
    out = []
    for tok in raw:
        low = tok.lower().strip("-/")
        if low in stop or len(low) < 5:
            continue
        if low not in out:
            out.append(low)
    # Also keep multi-word distinctive phrases (2+ consecutive kept tokens from original).
    words = [t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9+&/-]*", name)]
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if a in stop or b in stop or len(a) < 4 or len(b) < 4:
            continue
        phrase = f"{a} {b}"
        if phrase not in out:
            out.append(phrase)
    return out[:8]


def _near_program(text: str, name: str, match: re.Match[str], window: int = 400) -> bool:
    """True if distinctive program-name evidence sits near the keyword match.

    Shared secondary pages often mention many programs; without proximity we
    false-flip (e.g. SR&ED on a page that says vouchers are paused).
    Requires two token hits, or one distinctive phrase / rare token (≥6 chars
    or containing digits/&).
    """
    anchors = _name_anchors(name)
    if not anchors:
        return False  # no distinctive anchor — refuse keyword flip
    lo = max(0, match.start() - window)
    hi = min(len(text), match.end() + window)
    vicinity = text[lo:hi].lower()
    hits = [a for a in anchors if a in vicinity]
    if len(hits) >= 2:
        return True
    if any((" " in a) or ("&" in a) or any(c.isdigit() for c in a) or len(a) >= 8 for a in hits):
        return True
    return False


def detect_status(http_code: int, body: str, current: str, name: str = "") -> tuple[str | None, str]:
    """Return (new_status or None if no signal, evidence note)."""
    if http_code in (404, 410, 451):
        return "closed", f"HTTP {http_code}"
    if http_code >= 500:
        return None, f"HTTP {http_code} (server error — no status change)"
    if http_code != 200:
        return None, f"HTTP {http_code} (non-success — no status change)"

    text = body[:200_000]
    # Prefer the most specific signal; closed > paused > open when both appear.
    # Keyword flips require program-name proximity to avoid shared-page noise.
    for label, cre in (("closed", CLOSED_RE), ("paused", PAUSED_RE), ("open", OPEN_RE)):
        m = cre.search(text)
        if not m:
            continue
        if name and not _near_program(text, name, m):
            continue
        return label, f"keyword:{label}"
    return None, "HTTP 200 (no status keyword — keep current)"

def fetch(url: str, timeout: float) -> tuple[int, str, str | None]:
    """Return (http_code, body_text, error_message)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read(500_000)
            charset = "utf-8"
            ctype = resp.headers.get_content_charset() if hasattr(resp.headers, "get_content_charset") else None
            if ctype:
                charset = ctype
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return int(code), text, None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(100_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return int(exc.code), body, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 — network surface is broad
        return 0, "", f"{type(exc).__name__}: {exc}"


def append_ledger(events: list[dict], dry_run: bool) -> None:
    if not events:
        return
    lines = "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)
    if dry_run:
        print(f"[dry-run] would append {len(events)} ledger event(s)")
        for e in events:
            print("  ", e)
        return
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(lines)


def main() -> int:
    opts = parse_args(sys.argv[1:])
    today = date.today().isoformat()

    try:
        doc = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load {DATA}: {exc}")
        return 1

    programs = doc.get("programs", [])
    if opts["limit"] is not None:
        programs = programs[: opts["limit"]]

    flips = 0
    concerns = 0
    verified = 0
    skipped = 0
    events: list[dict] = []
    dirty = False

    print(f"Beacon reverify — {len(programs)} programs · {today}"
          + (" · DRY-RUN" if opts["dry_run"] else "")
          + (" · respect-cadence" if opts["respect_cadence"] else ""))

    for p in programs:
        pid = p.get("id", "?")
        if opts["respect_cadence"]:
            cadence = p.get("check_cadence_days", 7)
            try:
                y, m, d = (int(x) for x in p.get("checked", "").split("-"))
                age = (date.today() - date(y, m, d)).days
            except ValueError:
                age = 10 ** 9  # unparseable checked date — always due
            if age < cadence:
                skipped += 1
                print(f"  [{pid}] skip — checked {age}d ago, cadence {cadence}d")
                continue
        url = p.get("source_url", "")
        old_status = p.get("status", "open")
        print(f"  [{pid}] fetch {url[:72]}…")

        code, body, err = fetch(url, opts["timeout"])
        if err and code == 0:
            # Hard failure — keep status, mark tier concern, log, continue.
            concerns += 1
            if p.get("tier") == "VERIFIED":
                p["tier"] = "INFERRED"
                dirty = True
            note = f"fetch_failed: {err}"
            print(f"    CONCERN {note} — keep status={old_status}")
            events.append({
                "date": today,
                "program_id": pid,
                "old_status": old_status,
                "new_status": old_status,
                "evidence_url": url,
                "tier": p.get("tier", "INFERRED"),
                "concern": note,
            })
            continue

        new_status, evidence = detect_status(code, body, old_status, p.get("name", ""))
        # Successful observable check this cycle.
        if code == 200 and not err:
            p["checked"] = today
            dirty = True
            if is_primary(p.get("source_name", "")):
                p["tier"] = "VERIFIED"
                verified += 1
            # Secondary sources stay INFERRED even on a clean fetch.
            print(f"    ok HTTP {code} · {evidence} · checked={today} tier={p.get('tier')}")
        else:
            # Partial signal (e.g. HTTP 404 with body) — still usable for flip.
            print(f"    signal HTTP {code} · {evidence}" + (f" · {err}" if err else ""))

        if new_status and new_status != old_status:
            flips += 1
            dirty = True
            p["status"] = new_status
            p["status_since"] = today
            p["checked"] = today
            print(f"    FLIP {old_status} → {new_status}")
            events.append({
                "date": today,
                "program_id": pid,
                "old_status": old_status,
                "new_status": new_status,
                "evidence_url": url,
                "tier": "VERIFIED" if is_primary(p.get("source_name", "")) else "INFERRED",
            })
        elif code not in (200,) and code != 0:
            # Non-200 that didn't flip — treat as concern, keep status.
            concerns += 1
            if p.get("tier") == "VERIFIED":
                p["tier"] = "INFERRED"
                dirty = True
            note = f"http_{code}: {evidence}"
            events.append({
                "date": today,
                "program_id": pid,
                "old_status": old_status,
                "new_status": old_status,
                "evidence_url": url,
                "tier": p.get("tier", "INFERRED"),
                "concern": note,
            })

    if dirty and not opts["dry_run"]:
        # Persist against the full document (limit only affects the fetch loop).
        full = json.loads(DATA.read_text(encoding="utf-8"))
        by_id = {p["id"]: p for p in programs}
        for i, p in enumerate(full["programs"]):
            if p["id"] in by_id:
                full["programs"][i] = by_id[p["id"]]
        full["generated"] = today
        DATA.write_text(json.dumps(full, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Wrote {DATA}")
    elif dirty and opts["dry_run"]:
        print("[dry-run] would write programs.json")

    append_ledger(events, opts["dry_run"])

    print(f"RESULT: flips={flips} concerns={concerns} primary_verified={verified} "
          f"skipped={skipped} events={len(events)}")
    # Always exit 0 if we completed the sweep — failures are recorded, not fatal.
    return 0


if __name__ == "__main__":
    sys.exit(main())
