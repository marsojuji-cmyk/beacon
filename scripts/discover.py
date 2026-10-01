#!/usr/bin/env python3
"""Beacon discovery — scan listing pages for new-program candidates.

Reads data/discovery_sources.json (curated listing/announcement pages),
fetches each with stdlib urllib, and extracts candidate program mentions via
conservative link-text heuristics.

Candidates are LEADS, not facts:
  - tier is always UNKNOWN
  - status is always "candidate"
  - nothing is ever auto-promoted into data/programs.json
  - duplicates (by URL, or by name against programs.json) are skipped

Writes data/discovery.json: {generated, sources_checked, candidates: [...]}.

stdlib only. Usage: python3 scripts/discover.py [--dry-run]
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "discovery_sources.json"
PROGRAMS = ROOT / "data" / "programs.json"
OUT = ROOT / "data" / "discovery.json"

UA = "BeaconRadar/2.0 (+https://marcusrichards.dev; funding-radar discovery; stdlib)"

# Link text that smells like a funding program (kept deliberately narrow).
PROGRAM_RE = re.compile(
    r"\b(grant|grants|funding|fund\b|program|initiative|bursary|"
    r"subsidy|voucher|rebate|tax credit|contribution)\b",
    re.I,
)
LINK_RE = re.compile(
    r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

MAX_NEW_PER_RUN = 10

# Tokens that carry no signal on their own — a lead needs at least two
# distinctive (long, non-generic) tokens, e.g. "Alberta Digital Traction".
GENERIC_TOKENS = {
    "funding", "fund", "funds", "grant", "grants", "program", "programs",
    "programme", "government", "govt", "view", "page", "pages", "basics",
    "start", "here", "who", "we", "our", "your", "support", "direct",
    "innovation", "apply", "applying", "learn", "more", "click", "read",
    "find", "finder", "list", "all", "new", "now", "sector", "sectors",
}


def distinctive_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z]{7,}", text)
            if t.lower() not in GENERIC_TOKENS]


def fetch(url: str, timeout: float = 25.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read(800_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return int(code), text
    except urllib.error.HTTPError as exc:
        return int(exc.code), ""
    except Exception:
        return 0, ""


def clean_text(raw_html: str) -> str:
    text = TAG_RE.sub(" ", raw_html)
    text = htmlmod.unescape(text)
    return WS_RE.sub(" ", text).strip()


def absolutize(base: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    return urllib.parse.urljoin(base, href)


def main() -> int:
    dry = "--dry-run" in sys.argv[1:]
    today = date.today().isoformat()

    try:
        sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
        programs = json.loads(PROGRAMS.read_text(encoding="utf-8"))["programs"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL: {exc}")
        return 1

    prev = {"candidates": []}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {"candidates": []}

    known_urls = {c.get("url") for c in prev.get("candidates", [])}
    known_urls |= {p.get("source_url") for p in programs}
    known_names = {p.get("name", "").lower() for p in programs}

    candidates = list(prev.get("candidates", []))
    checked = 0
    added = 0

    print(f"Beacon discovery — {len(sources)} sources · {today}"
          + (" · DRY-RUN" if dry else ""))

    for src in sources:
        name = src.get("name", "?")
        url = src.get("url", "")
        print(f"  [{name}] fetch {url[:70]}…")
        code, body = fetch(url)
        checked += 1
        if code != 200 or not body:
            print(f"    skip HTTP {code}")
            continue
        seen_this_page = 0
        for m in LINK_RE.finditer(body[:600_000]):
            if added >= MAX_NEW_PER_RUN:
                break
            href, inner = m.group(1), m.group(2)
            text = clean_text(inner)
            if not (8 <= len(text) <= 110):
                continue
            if not PROGRAM_RE.search(text):
                continue
            # Drop generic nav chrome ("Grant Funding", "View Funding page"):
            # a lead needs at least two distinctive tokens.
            if len(distinctive_tokens(text)) < 2:
                continue
            abs_url = absolutize(url, href)
            if not abs_url or abs_url in known_urls:
                continue
            if text.lower() in known_names:
                continue
            # Snippet: plain text around the link for human review.
            pos = body.find(m.group(0))
            snippet = clean_text(body[max(0, pos - 300): pos + 300])[:280]
            candidates.append({
                "name_guess": text,
                "url": abs_url,
                "discovery_source": name,
                "snippet": snippet,
                "discovered": today,
                "tier": "UNKNOWN",
                "status": "candidate",
            })
            known_urls.add(abs_url)
            added += 1
            seen_this_page += 1
        print(f"    HTTP 200 · {seen_this_page} new candidate(s)")

    doc = {
        "generated": today,
        "sources_checked": checked,
        "candidates": candidates,
        "note": ("Candidates are UNVERIFIED leads (tier UNKNOWN). "
                 "Nothing here is a tracked program until a human verifies "
                 "it against a primary source and adds it to programs.json."),
    }
    if dry:
        print(f"[dry-run] would write {OUT} ({len(candidates)} candidates, {added} new)")
    else:
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"Wrote {OUT}")

    print(f"RESULT: PASS · sources={checked} new_candidates={added} "
          f"total_candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
