# Beacon data API

Beacon's `data/` directory is a static JSON read API. Everything is plain
UTF-8 JSON, standard library friendly, generated or validated by the scripts
in `scripts/`. Fetch any file raw from GitHub or the live Pages site and parse
it — no auth, no rate limits beyond the host's.

## Endpoints

### `data/programs.json`
The program radar. One object per funding program.
```
{ "generated": "2026-09-30",
  "programs": [
    { "id": "ai-rnd-associates",          # stable key, referenced by other files
      "name": "...", "region": "Alberta", # region: Calgary | Alberta | Canada
      "type": "grant", "amount": "...", "status": "open",   # open | paused | closed
      "status_since": "2026 (continuous)",
      "eligibility": ["..."], "deadline": "Continuous intake",
      "deadline_date": null,              # ISO date when a hard deadline exists
      "requires_incorporation": true,
      "source_name": "Ayming Canada (secondary)",
      "source_url": "https://...",
      "checked": "2026-09-30",            # last verification date
      "tier": "INFERRED",                 # VERIFIED | INFERRED
      "stacking": [{"with": "ieg-sred", "note": "..."}],
      "stacking_tier": "INFERRED" } ] }
```

### `data/deadlines.json`
Deadline-urgency engine output (`scripts/deadlines.py`).
`urgency`: overdue | imminent | upcoming | ongoing | later. `days_until` is an
integer when a hard `deadline_date` exists, else null.

### `data/shortlist.json`
Eligibility engine output (`scripts/match.py` + `data/profile.yaml`):
`shortlist` (eligible now), `blocked` (one step away), `not_for_him`,
`unlock_roadmap`, and `counts`.

### `data/ledger.jsonl`
Append-only change ledger, one JSON object per line. A fetch failure never
flips a program — it writes a `concern` event and holds the old status.

### `data/evidence.json` — Wave 3
Per-program evidence snapshots (`scripts/evidence.py`, regenerated from
`programs.json` + `ledger.jsonl` — edit those, not this file).
```
{ "generated": "2026-09-30",
  "snapshots": [
    { "program_id": "ai-rnd-associates", "program_name": "...",
      "facts": [ { "fact": "Status: open (since 2026 (continuous))",
                   "source_name": "...", "source_url": "https://...",
                   "checked": "2026-09-30",
                   "tier": "VERIFIED" } ],   # VERIFIED | INFERRED | GUESSED | UNKNOWN
      "history": [ { "date": "2026-09-30", "event": "...",
                     "tier": "INFERRED", "evidence_url": "https://..." } ],
      "unknown": [ "Funder disbursement history — not yet verified" ] } ] }
```
RULE: anything without a named source + checked date + claim tier renders as
UNKNOWN with an explicit "not yet verified" label — never as a
plausible-looking fact.

### `data/pipeline.template.json` — Wave 2
Schema + SAMPLE entries for the application pipeline tracker. Stages:
`prospecting → preparing → applied → in-review → awarded | declined`.
Real data lives in `data/pipeline.json`, which is **gitignored and never
pushed** — the template's entries are all marked `"sample": true` /
`"tier": "SAMPLE"`. To go live: copy the template to `data/pipeline.json`,
replace the entries, rebuild (`scripts/embed.py`).

## Rebuilding

```bash
python3 scripts/check.py      # validate everything (schema + tiers + privacy)
python3 scripts/evidence.py   # regenerate evidence.json from programs + ledger
python3 scripts/embed.py      # rebuild docs/index.html + docs/variant-b.html
```
