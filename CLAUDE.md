# CLAUDE.md

Operational guide for building this project with Claude Code. Read this before writing code. Full spec is in `PRD.md`; this file is the how-to-work-here layer.

## What this is
A per-discipline badminton rating system seeded and updated from BWF tournament results. Build in phases: **Phase 1 = scrape + normalize results into the DB** (do first, get green), then Phase 2 = rating engine, then Phase 3 = serving. Do not start Phase 2 until Phase 1 ingests the fixture tournament correctly.

## Architecture principle (governs everything)
Three strictly separated layers:
1. **Ingestion** — Django app `apps/ingest` (models, `scrape` command, normalizer, endpoint builders).
2. **Rating engine** — a **pure Python package** `rating/`, NOT a Django app. No Django imports, no ORM, no request cycle. Takes plain dataclasses/dicts, returns rating rows. `manage.py rate` is the only bridge. This isolation is non-negotiable.
3. **Serving** — DRF (`apps/api`) + React (`frontend/`), Phase 3 only.

Django owns persistence/admin/migrations/HTTP. The engine owns the math and knows nothing about Django.

## Tech stack
Python 3.12 · Django 5 · Django REST Framework (Phase 3) · React + Vite (Phase 3) · Docker/compose with Postgres (Phase 3). Ingestion uses `httpx` + `pydantic` v2 (validate raw payloads before ORM writes). Tests: `pytest` + `pytest-django`. Local dev is SQLite + no Docker until Phase 3 — get the first ingested result before adding containers.

## Repo layout
```
badminton-elo/
  pyproject.toml            # or requirements + Django project
  manage.py
  CLAUDE.md  PRD.md
  config/                   # Django project (settings, urls, wsgi)
    settings.py             # DATABASES (sqlite dev / postgres docker), app config (PRD §8)
  apps/
    ingest/
      models.py             # PRD §5 (Tournament, Player, Draw, Match, MatchPlayer, Game, RawCache, ...)
      admin.py              # register all models — this is the Phase-1 inspection UI
      api/
        client.py           # httpx: rate-limit, retry/backoff, RawCache read-through, UA
        endpoints.py        # URL builders (already drafted; single source of truth)
      normalize.py          # raw match -> Match/Game/MatchPlayer rows (PRD §6)
      management/commands/
        scrape.py           # detail -> draws -> draw-data -> normalize
        ingest_status.py
        rate.py             # bridges DB <-> rating/ package (Phase 2)
        leaderboard.py      # export a discipline ranking (Phase 2)
    api/                     # DRF viewsets/serializers (Phase 3)
  rating/                    # PURE package — no Django
    engine.py               # Glicko-2-with-pairs update (PRD §7)
    dominance.py            # format-normalized margin (PRD §7.3)
    seeding.py              # flat now; rank-based later
    run.py                  # chronological driver over plain match records
  frontend/                 # Vite + React (Phase 3)
  docker-compose.yml        # db + web (frontend + worker later)
  data/                     # sqlite db + cached raw json (gitignored)
  tests/
    fixtures/               # captured JSON payloads
```

## Commands
```bash
# local first win (no Docker)
python manage.py migrate
python manage.py scrape --code <TOURNAMENT_GUID>   # cached, idempotent
python manage.py scrape --all                      # settings.TOURNAMENT_CODES
python manage.py ingest_status
python manage.py rate            # Phase 2 incremental
python manage.py rate --rebuild  # Phase 2 deterministic recompute
python manage.py leaderboard --event XD
pytest

# Docker (Phase 3)
docker compose up --build
docker compose run --rm web python manage.py scrape --all
```

## CRITICAL domain rules (stack-independent — ignoring these silently corrupts ratings)

1. **`winner` = who ADVANCED, not who scored more.** For retirements/walkovers the advancing side can have fewer points. Take the winner from the `winner` field only. Real case: draw-data match `344`, `winner:2`, score `11-5` in team1's favor — team1 led and retired, team2 advances.

2. **Compute margin/dominance ONLY for `scoreStatus == Normal`.** Otherwise dominance is undefined; never infer from the scoreline. Retirement = reduced-weight loss for the retiree (`K_RETIRE`); walkover/no-play = ingest but mark rating-excluded.

3. **Score orientation fixed:** `score[].home` = side 1 (team1), `.away` = side 2 (team2). Never reorder sides by winner.

4. **Player `id` is the stable identity** across partners and disciplines (GAO Jia Xuan = 57943 everywhere). Upsert by `player_id`; build partnerships from ids, never names.

5. **Rate individuals per discipline, not pairs.** Rating key is `(player_id, event)`. Pair strength is derived from members at match time. No stored "pair rating."

6. **`eventName` selects the discipline bucket** (MS/WS/MD/WD/XD). Don't infer player sex; not needed.

7. **Process matches chronologically** by `(match_time_utc, round_order, match_id)`. `rate --rebuild` must reproduce ratings exactly.

8. **Normalize margins across scoring formats.** Never feed raw point differences to the engine — convert to the format-independent dominance ratio first (PRD §7.3). Store each match's `scoring_format`.

9. **Idempotent + polite scraping.** `update_or_create` on stable keys; cache every raw response to `RawCache` + `data/` and read cache before the network; rate-limit (`RATE_LIMIT_QPS`, default 1), retry w/ backoff, descriptive `USER_AGENT`. Re-running a scrape changes nothing.

## Ingestion flow (Phase 1, `scrape.py`)
1. `vue-tournament-detail` → `update_or_create` Tournament (capture `categoryModel.name` = tier).
2. `vue-tournament-draws` → for each draw with `qualification==0` (unless `INCLUDE_QUALIFYING`) → `update_or_create` Draw.
3. `vue-tournament-draw-data?draw={value}` → consume the flat **`matches`** array (ignore the `results` bracket map for now). Per match: upsert Player rows (from `team1/2.players[]`), Match, MatchPlayer (side 1/2), Game rows.
4. Default `scoring_format` from date (PRD §6.5) unless overridden.
> Query-param names for draws/draw-data/players/statistics need one confirmation pass vs the network tab. `endpoints.py` centralizes them — a rename is one line. Start from `tests/fixtures/`.

## Rating engine (Phase 2, `rating/`)
Pure module. Glicko-2 per `(player,event)`; team rating = mean of members, combined RD = RMS; expected score with `g(RD)` damping; binary `S` for direction; magnitude × `M` (dominance) × `W_tier`; each player moves scaled by own RD; shrink RD after, inflate for inactivity. Retirement path: `K_RETIRE`, no dominance. Constants from Django settings, passed **in** to the engine (engine never reads settings itself).

## Do / Don't
- DO validate every raw payload through a pydantic model before ORM writes; log + skip a malformed match rather than crashing the draw.
- DO register every model in admin — it's your Phase-1 data browser.
- DO keep `rating/` free of Django imports; pass data in as plain objects.
- DO keep `endpoints.py` the single source of truth for URLs/params.
- DON'T store or compute a per-pair rating.
- DON'T read the scoreline for non-`Normal` matches.
- DON'T reorder sides, dedupe players by name, or hit the network when the cache has the response.
- DON'T scaffold React or docker-compose during Phase 1. SQLite + admin + `scrape` first.
- DON'T start Phase 2 before the M1 acceptance test passes.

## M1 acceptance (Phase 1 done)
Ingest the Malaysia Masters 2026 XD draw fixture and assert: 31 main-draw matches; winners correct including retired `344` (winner side 2 despite trailing 5-11); players deduped by id; Game rows match scorelines; a second `scrape` produces zero changes.
