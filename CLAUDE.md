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
        rate.py             # bridges DB <-> rating/ package (incremental; --rebuild = reference)
        rate_history.py     # smoothed all-time ratings (after rate)
        backtest.py         # grade an engine/setting change before shipping it
        leaderboard.py      # export a discipline ranking (Phase 2)
      base.py               # DataCommand: bumps DataVersion (API cache) on success
    incremental.py          # replay only changed tournaments (undo logs)
    engine_config.py        # settings.RATING -> RatingConfig + matching predictor
    rawstore.py             # raw API bodies live in data/raw/, RawCache is the index
  api/                       # DRF (Phase 3)
    views/                  # one module per area (rankings, players, tournaments, …)
    cache.py                # versioned response cache + ETag (keyed on DataVersion)
    ties.py                 # team-cup ties service (precomputed by build_ties)
  rating/                    # PURE package — no Django
    run.py                  # chronological driver; resume (initial=) + undo logs
    points.py               # LIVE engine: rally-level likelihood (settings ENGINE)
    engine.py               # Glicko-2-with-pairs update (alternative engine)
    dominance.py            # format-normalized margin (glicko engine, PRD §7.3)
    seeding.py              # rank seed (only if known at debut) + cross-discipline prior
    predict.py              # read-side win probability per engine
    peaks.py                # all-time peak (settled ratings only)
    history.py              # TrueSkill Through Time smoothing (all-time board)
    backtest.py             # log-loss/Brier/ECE harness
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
python manage.py rate            # incremental: replays only changed tournaments
python manage.py rate --rebuild  # deterministic recompute (the reference)
python manage.py rate_history    # smoothed all-time ratings (after rate)
python manage.py backtest [--set KEY=VALUE] [--since/--until]   # before changing RATING
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
Pure module. Ratings per `(player,event)`; team rating = mean of members, combined RD = RMS; each tournament is a rating period rated against start-of-period ratings; each player moves scaled by own RD (Glicko Newton step); RD shrinks after, inflates for inactivity. Constants from Django settings, passed **in** to the engine (engine never reads settings itself; `apps/ingest/engine_config.py` is the bridge).
- **Live engine = `points`** (`settings.RATING["ENGINE"]`): the rating gap sets the chance of winning a rally; game/match odds follow from the scoring rules; updates use rallies won (`RALLY_WEIGHT` per rally). Side-out-era (pre-2006) games are read by `rating/sideout.py` (P(game score) under side-out rules, `SIDEOUT_WEIGHT`); retired/scoreless matches update on the result through the same model. `glicko` (binary result × dominance `M` × `W_tier`) remains selectable.
- Seeds: a BWF rank seeds a debut only if observed by then; otherwise the cross-discipline prior, else flat.
- **Change engine settings only through `manage.py backtest`** (held-out log-loss; confirm on a second window). Current: points 0.5135 vs glicko 0.5210 (2023+).
- `rate` is incremental and must equal `rate --rebuild` exactly (tests enforce it). Settings/seed changes force a full rebuild automatically.
- All-time board = `rate_history` (TrueSkill Through Time, smoothed, calibrated to the live scale). Never used for live ratings.

## Serving (Phase 3)
- Every data-writing command subclasses `DataCommand`; a successful run bumps `DataVersion`, which invalidates the API cache (`apps/api/cache.py`) and is the ETag. Don't write served data outside a DataCommand or an unsafe `/api/` request.
- Per-request aggregates belong in a build step (precompute), not in views. Add new heavy reads to `build_*`/`rate`.
- The refresh pipeline runs everything after collection in ONE transaction (autocommit off; no nested `atomic()` savepoints around big rewrites — they make SQLite ~3x slower).

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
- DON'T put raw response bodies back in the DB (`RawCache.body` stays empty; `rawstore`).

## M1 acceptance (Phase 1 done)
Ingest the Malaysia Masters 2026 XD draw fixture and assert: 31 main-draw matches; winners correct including retired `344` (winner side 2 despite trailing 5-11); players deduped by id; Game rows match scorelines; a second `scrape` produces zero changes.
