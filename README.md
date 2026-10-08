# Beacon

**Tracks funding programs for Calgary, Alberta and Canada builders, and labels every claim with how it was verified.**

[![agent](https://github.com/marsojuji-cmyk/beacon/actions/workflows/agent.yml/badge.svg)](https://github.com/marsojuji-cmyk/beacon/actions/workflows/agent.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](.github/workflows/agent.yml)

Most grant lists present scraped text as fact. Beacon shows its work instead.

Every program carries a **claim tier**:

- **VERIFIED** — confirmed against a primary source (the program's own site or announcement) in the current check cycle.
- **INFERRED** — drawn from secondary reporting (press, guides). Treated as a lead, not a fact.
- **GUESSED / UNKNOWN** — marked explicitly when the evidence doesn't support more.

## What it guarantees

- **A fetch failure never deletes or flips a program.** `scripts/reverify.py` keeps the old status, marks a tier concern and logs it. A 200 response with no status keyword keeps the current status.
- **Every status change carries evidence.** Changes are appended to `data/ledger.jsonl` with their evidence URL, and the dashboard shows a "last verified" stamp on every card.
- **Discovery never self-promotes.** New-program leads from `scripts/discover.py` are always tier UNKNOWN and are never written into `data/programs.json` automatically.
- **Unverified facts render as UNKNOWN.** Per-program evidence snapshots name a source, a check date and a tier for every fact.
- **Every run leaves a receipt.** `scripts/agent.py` writes `data/agent.json` with per-step results. A failed step is recorded, not fatal, and the run reports `RESULT: FAIL` naming the step.
- **Private data stays out.** `scripts/check.py` validates schema, tiers and pipeline privacy. Real application entries live in the gitignored `data/pipeline.json`.

## Quickstart

```bash
git clone https://github.com/marsojuji-cmyk/beacon && cd beacon
python3 scripts/match.py      # run funding & eligibility search
```

Standard-library Python only. No dependencies.

### Example search & output

Running `python3 scripts/match.py` scores builder criteria (`data/profile.yaml`) against all funding programs in `data/programs.json`:

```text
Beacon match — 13 programs · 2026-10-07
Verdicts: blocked=5, eligible-now=3, not-for-him=5
Shortlist:
  + ai-rin-2026: Ecosystem infrastructure — founder-facing via RINs; no incorporation bar.
  + elevateip-ab: Open and does not require incorporation for this profile.
  + ai-compute-fund: Open and does not require incorporation for this profile.
Unlock roadmap:
  → incorporate unlocks 5: ai-rnd-associates, irap-ai-assist, raii-prairies, ieg-sred, mitacs-accelerate
  → first-rnd-dollar unlocks 1: ieg-sred
Wrote data/shortlist.json
RESULT: PASS
```

### Interpreting the results

- **Verdicts:** Categorizes programs into **eligible-now** (apply today), **blocked** (prerequisites pending), and **not-for-him** (out of scope).
- **Shortlist:** Immediately actionable programs that meet all criteria without blocking hurdles.
- **Unlock roadmap:** Highlights concrete tactical milestones (incorporation or first R&D dollar) and the programs each unlock.

### Running the pipeline

```bash
python3 scripts/check.py      # validate the dataset (schema, tiers, pipeline privacy)
python3 scripts/reverify.py   # re-check sources, update ledger on real changes
python3 scripts/match.py      # score eligibility, write data/shortlist.json
python3 scripts/evidence.py   # build per-program evidence snapshots -> data/evidence.json
python3 scripts/embed.py      # rebuild docs/index.html + docs/variant-b.html from data
```

Open `docs/index.html` in a browser. That's the whole deployment.

## How it fails

| Condition | Behaviour |
|---|---|
| Source unreachable or non-200 | Status kept, tier concern logged, run continues |
| Page reachable but no status keyword | Status kept ("keep current") |
| A step in the agent loop fails | Recorded in `data/agent.json`. Remaining steps still run, and the result is `RESULT: FAIL` with the step named |
| New program spotted on a listing page | Queued in `data/discovery.json` as an UNKNOWN lead, with an alert to verify against a primary source |

## Evidence

From committed data, 2026-10-07:

- **`data/programs.json`:** 13 programs. 10 open, 2 paused, 1 closed. 12 INFERRED, 1 VERIFIED (Alberta Innovates Regional Innovation Networks renewal). By region: 6 Alberta, 6 Canada, 1 Calgary.
- **`data/shortlist.json`:** 3 eligible now, 5 blocked (unlock on incorporation), 5 not a fit.
- **`data/agent.json`:** the latest run, at 2026-10-07 19:19 UTC (13:19 MDT), finished with `ok: true`, all 8 steps rc 0. It checked 10 sources, found 0 flips and has 58 discovery candidates queued.
- `python3 scripts/check.py` passes locally (2026-10-07).

Most records are INFERRED from secondary sources. Verify before you apply; Beacon tells you exactly which claims need it.

## What it does

- **Radar**: 13 programs across Calgary / Alberta / Canada, filterable by region, status, and type.
- **Shortlist** — an eligibility engine (`scripts/match.py` + `data/profile.yaml`) scores programs against a builder profile and produces an unlock roadmap: what's eligible now, what's gated behind incorporation, what's gated behind first R&D spend.
- **Ledger** — a provenance-bearing history of every status change, with evidence links.

## The agent loop (Stage 2, 2026-09-30)

One command runs the whole radar cycle, in dependency order:

```bash
python3 scripts/agent.py              # full loop (see below)
python3 scripts/agent.py --dry-run    # reverify/discover/alerts print, don't write
python3 scripts/agent.py --limit 2    # smoke-test the loop on 2 programs
```

| Step | Script | What it does |
|---|---|---|
| 1 | `reverify.py --respect-cadence` | Re-checks only sources due this run (`check_cadence_days`: 7 open / 14 paused / 30 closed); flips and concerns → ledger |
| 2 | `match.py` | **Automatic re-scoring** of every program against `data/profile.yaml` → `shortlist.json` |
| 3 | `deadlines.py` | Recomputes urgency bands → `deadlines.json` |
| 4 | `evidence.py` | Rebuilds per-program evidence snapshots |
| 5 | `discover.py` | Scans `data/discovery_sources.json` listing pages for new-program **leads** → `data/discovery.json` (tier UNKNOWN, never auto-promoted) |
| 6 | `alerts.py` | Deadline crossings (≤30d, overdue), today's status flips, discovery digest → `data/alerts.json` + provenance-bearing ledger events |
| 7 | `embed.py` | Rebuilds `docs/index.html` + `docs/variant-b.html` |
| 8 | `check.py` | Validates the dataset |

Every run writes `data/agent.json` — the run receipt (timestamps, per-step results, counts). A failed step is recorded, not fatal; the loop finishes what it can and reports `RESULT: FAIL` naming the step.

**Scheduled:** `.github/workflows/agent.yml` runs `scripts/agent.py` daily at 13:17 UTC and commits `data/` + `docs/` back to main — the radar updates itself.

**Claim-tier discipline holds throughout:** discovery candidates are UNKNOWN leads; fetch failures never flip or delete; alerts are derived, not primary claims.

## Waves

- **Wave 1** (2026-09-30): deadline-urgency engine, stacking notes, client-side search, two page variants (cards + dense table).
- **Wave 2** (2026-09-30): application pipeline tracker — stages prospecting → preparing → applied → in-review → awarded/declined. Real entries live in the gitignored `data/pipeline.json`; the repo ships `data/pipeline.template.json` with clearly-labeled SAMPLE data. The page says which one it's showing.
- **Wave 3** (2026-09-30): per-program evidence snapshots (`data/evidence.json`, generated from `programs.json` + `ledger.jsonl`) — every fact carries a named source, check date, and claim tier; funder history comes only from recorded ledger events; anything unverified renders as UNKNOWN, never as a plausible fact. The `data/` directory is documented as a static JSON read API in `data/README.md`.

## Status

Live and self-updating: `.github/workflows/agent.yml` runs the loop daily at 13:17 UTC and commits `data/` and `docs/` back to main.

## License

MIT.
