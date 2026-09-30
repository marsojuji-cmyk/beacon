# Beacon — a funding radar that shows its work

Beacon tracks funding programs for independent builders in Calgary, Alberta, and Canada — and labels every claim with how it was verified.

Most grant lists present scraped text as fact. Beacon doesn't. Every program carries a **claim tier**:

- **VERIFIED** — confirmed against a primary source (the program's own site or announcement) in the current check cycle.
- **INFERRED** — drawn from secondary reporting (press, guides). Treated as a lead, not a fact.
- **GUESSED / UNKNOWN** — marked explicitly when the evidence doesn't support more.

Tiers are re-checked, not assumed. `scripts/reverify.py` re-fetches sources on a schedule, applies a conservative change heuristic (a fetch failure never silently deletes or flips a program), and appends every status change to `data/ledger.jsonl` with its evidence URL. The dashboard shows "last verified" stamps on every card.

## What it does

- **Radar** — 13 programs across Calgary / Alberta / Canada, filterable by region, status, and type.
- **Shortlist** — an eligibility engine (`scripts/match.py` + `data/profile.yaml`) scores programs against a builder profile and produces an unlock roadmap: what's eligible now, what's gated behind incorporation, what's gated behind first R&D spend.
- **Ledger** — a provenance-bearing history of every status change, with evidence links.

## Run it

Standard-library Python only. No dependencies.

```bash
python3 scripts/check.py      # validate the dataset (schema, tiers, pipeline privacy)
python3 scripts/reverify.py   # re-check sources, update ledger on real changes
python3 scripts/match.py      # score eligibility, write data/shortlist.json
python3 scripts/evidence.py   # build per-program evidence snapshots -> data/evidence.json
python3 scripts/embed.py      # rebuild docs/index.html + docs/variant-b.html from data
```

Open `docs/index.html` in a browser. That's the whole deployment.

## Waves

- **Wave 1** (2026-09-30): deadline-urgency engine, stacking notes, client-side search, two page variants (cards + dense table).
- **Wave 2** (2026-09-30): application pipeline tracker — stages prospecting → preparing → applied → in-review → awarded/declined. Real entries live in the gitignored `data/pipeline.json`; the repo ships `data/pipeline.template.json` with clearly-labeled SAMPLE data. The page says which one it's showing.
- **Wave 3** (2026-09-30): per-program evidence snapshots (`data/evidence.json`, generated from `programs.json` + `ledger.jsonl`) — every fact carries a named source, check date, and claim tier; funder history comes only from recorded ledger events; anything unverified renders as UNKNOWN, never as a plausible fact. The `data/` directory is documented as a static JSON read API in `data/README.md`.

## Current state (2026-09-30)

13 programs: 10 open, 2 paused, 1 closed. 3 eligible for an unincorporated solo builder today; 5 unlock on incorporation; 5 aren't a fit. Most records are INFERRED from secondary sources — the one VERIFIED record is the Alberta Innovates Regional Innovation Networks renewal ($20.6M, Sep 2026). Verify before you apply; Beacon tells you exactly which claims need it.

## License

MIT.
