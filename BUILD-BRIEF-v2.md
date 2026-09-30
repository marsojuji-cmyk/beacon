# Beacon v2 — Cursor build brief (staged 2026-09-30)

## What exists (v1, in ~/workspace/beacon)
- `data/programs.json` — 13 programs (Calgary/Alberta/Canada), each with: id, name, region, type, amount, status (open|paused|closed), status_since, eligibility[], deadline, source_name, source_url, checked (YYYY-MM-DD), tier (VERIFIED|INFERRED), requires_incorporation.
- `scripts/check.py` — stdlib schema validator + staleness reporter. Passes.
- `docs/index.html` — single-file vintage scientific-plate dashboard (cream paper, dotted grid, crimson/teal/ochre), region/status filters, incorporation toggle, claim-tier stamps. JSON embedded.

## Build v2 — the ceiling
1. **Self-verification** (`scripts/reverify.py`, stdlib urllib only):
   - Fetch each program's `source_url`; detect status flips (open/paused/closed) via keyword heuristics + HTTP status.
   - On flip: update `programs.json` (status, status_since, checked), append event to `data/ledger.jsonl`.
   - Never silently drop a program on fetch failure — mark `tier` concern, log it, keep old status.
2. **Eligibility engine** (`data/profile.yaml` + `scripts/match.py`):
   - Profile: unincorporated independent builder, Calgary AB, AI/software, pre-revenue, solo, no R&D payroll yet.
   - Score each program: eligible-now / blocked (with the single unblock step) / not-for-him.
   - Output `data/shortlist.json`: the shortlist + the "unlock roadmap" (incorporate → unlocks X; first R&D dollar → unlocks SR&ED stack).
3. **Change ledger** (`data/ledger.jsonl`): every status flip as an event — {date, program_id, old_status, new_status, evidence_url, tier}. Dashboard renders it as a timeline.
4. **Dashboard v2** (`docs/index.html`): keep the scientific-plate style; add shortlist view, ledger timeline, "last verified" stamps per card.
5. **Claim-tier discipline**: VERIFIED only for primary-source checks this cycle; everything else INFERRED. No invented amounts, dates, or deadlines.

## Constraints
- stdlib Python only for scripts. Single-file HTML dashboard (no build step, no external deps).
- Small batches, each verified: schema check passes, dashboard renders, no placeholders.
- Ektar manages: verify every batch, report receipts. Nothing ships to GitHub until Marcus Richards taps.
