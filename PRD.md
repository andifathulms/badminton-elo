# PRD — Badminton Rating System (BWF)

## 1. Goal

Build a per-discipline **skill rating** system for badminton players, seeded and updated from BWF tournament results. Unlike chess/football, badminton has five disciplines (MS, WS, MD, WD, XD), three of which are pairs whose composition changes constantly. The system must rate **individual players per discipline**, derive pair strength from members, reward margin of victory in a way that is comparable across scoring formats and eras, and handle retirements/walkovers correctly.

This document specifies the whole system but is **phased**. The immediately buildable milestone is **Phase 1: ingestion (scrape + normalize results)**. Phases 2–3 (rating engine, serving/UI) are specified so the Phase-1 data model is correct, but are built after Phase 1 is green.

## 2. Scope

### In scope
- Phase 1 — Ingestion: pull tournament → draws → matches from the BWF fan API, normalize into the database, idempotently and politely.
- Phase 2 — Rating engine: per-(player, discipline) rating with uncertainty; pair blend; format-normalized margin; retirement handling; chronological processing; seeding.
- Phase 3 — Serving: DRF read API + React leaderboard/player pages.

### Out of scope (for now)
- Live/in-play updates. We ingest finished matches only.
- Predictions/betting features.
- Gender inference (not needed; ratings are keyed by discipline, not sex).

## 3. Architecture principle (READ FIRST — governs the whole build)

Three layers, kept strictly separated regardless of framework:

1. **Ingestion** — Django app (`apps/ingest`): models, management command `scrape`, normalizer, and the API endpoint builders.
2. **Rating engine** — a **pure Python package** (`rating/`), NOT a Django app. No Django imports, no ORM, no request cycle. It takes plain dataclasses/dicts in and returns rating rows out. Django's `manage.py rate` command is the only bridge between the DB and the engine. This isolation is non-negotiable: it is what keeps the rating math unit-testable and uncorrupted.
3. **Serving** — DRF viewsets (`apps/api`) + React (`frontend/`), Phase 3 only.

Django owns persistence, admin, migrations, and the HTTP API. The rating engine owns the math and knows nothing about Django.

## 4. Data sources (BWF fan API)

Base host observed: `https://extranet-lv.bwfbadminton.com/api`. Public fan-site JSON. Field names below are from real captured responses. URL builders live in `apps/ingest/api/endpoints.py` (already drafted); only `day-matches` has a fully confirmed request URL, the rest have confirmed response shapes but to-confirm request params.

> **Responsible use.** Undocumented public API. The scraper MUST rate-limit, cache raw responses, set a descriptive User-Agent, retry with backoff, and never parallel-hammer the host. Check the site's ToS before running at scale.

### 4.1 `vue-tournament-detail` — tournament metadata
`results`: `id`, `code` (GUID), `name`, `slug`, `start_date`, `end_date`, `tournament_category_id`, `categoryModel.name` (e.g. `"HSBC BWF World Tour Super 500"`), `tournament_series_id`, `prize_money`, `venue_name`.
Use for: tournament record + **tier** (drives optional K-weight).

### 4.2 `vue-tournament-draws` — list of draws
`results[]`: `value` (draw id, e.g. `"10"`), `text` (`"XD"`), `slug`, `size`, `doubles` (bool), `qualification` (0/1), `stage_name` (`"Main Draw"`/`"Qualifying"`), `stage_order`.
Use for: enumerate draws. **Filter to `qualification == 0`** for the MVP.

### 4.3 `vue-tournament-draw-data` — **PRIMARY results source**
Params: `tournamentCode` + draw `value`. Returns `results` (bracket map, `"{col}-{row}"`) and — the part we consume — **`matches`: a flat array of every match in the draw**. Each match:
- `id` (int, globally unique — **primary upsert key**), `code`
- `eventName` (`MS`/`WS`/`MD`/`WD`/`XD`), `drawName`, `drawCode`, `roundName` (`R32`…`Final`)
- `matchStatus` (`F`), `scoreStatus` (int) + `scoreStatusValue` (`Normal`/`Retired`/…)
- `winner` (1 or 2 — **who ADVANCED, not who scored more**; see §6.3)
- `team1`/`team2`: `players[]` with stable `id`, names, `countryCode`; `team1seed`/`team2seed`
- `score[]`: `{set, home, away}`, where **`home`=team1, `away`=team2**
- `matchTimeUtc`, `duration`, `reliability` (0/1 — capture, optionally down-weight `0`)

### 4.4 `day-matches` — matches for one date (secondary / reconciliation)
`.../tournaments/day-matches?tournamentCode={code}&date={YYYY-MM-DD}&order=2&court=0`. Same match shape as 4.3 but per-day across disciplines. Iterate `start_date..end_date`.

### 4.5 `players` — player directory (supplementary)
`players[]`: `id`, `nameDisplay`, `firstName`, `lastName`, `nameShort`, `slug`, `countryCode`, `avatar.thumbnailUrl`.

### 4.6 match `statistics` — per-match detail (optional Phase 1; valuable Phase 2 seeding)
Per match: `progress.games[]`, `statistics.team{1,2}` (`ralliesWon/Played`, `gamePoints`, `consecutivePoints`), `ranking.team{1,2}[].currentRank` (**for rank seeding**), `careerStats`, `players` (dob/height/`plays`), `officials`. Fetch lazily; do not block Phase 1.

### 4.7 Known gaps (TODO, non-blocking)
- **Tournament enumeration / calendar** — not captured. MVP reads `TOURNAMENT_CODES` from settings. Find the calendar API later.
- **Standalone rankings endpoint** — not captured. MVP seeds flat (§7.6). Rank-seeding later.

## 5. Data model (Django models, `apps/ingest/models.py`)

SQLite locally; Postgres in Docker — same models, only `DATABASES` changes. Sketch (key fields; add `Meta`, indexes, `__str__` as needed):

```python
class Tournament(models.Model):
    tournament_id = models.IntegerField(primary_key=True)   # detail.results.id (5229)
    code = models.CharField(max_length=64, unique=True)     # GUID
    name = models.CharField(max_length=255); slug = models.SlugField(blank=True)
    start_date = models.DateField(null=True); end_date = models.DateField(null=True)
    category_id = models.IntegerField(null=True)
    category_name = models.CharField(max_length=255, blank=True)  # tier
    series_id = models.IntegerField(null=True)
    prize_money = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    venue_name = models.CharField(max_length=255, blank=True)

class Player(models.Model):
    player_id = models.IntegerField(primary_key=True)       # stable BWF id
    name_display = models.CharField(max_length=255)
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    name_short = models.CharField(max_length=128, blank=True)
    slug = models.SlugField(blank=True)
    country_code = models.CharField(max_length=8, blank=True)
    avatar_url = models.URLField(blank=True)
    dob = models.DateField(null=True); height_cm = models.IntegerField(null=True)
    plays = models.CharField(max_length=8, blank=True)

class Draw(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    draw_value = models.CharField(max_length=16)            # "10"
    event = models.CharField(max_length=4)                  # MS/WS/MD/WD/XD
    stage = models.CharField(max_length=32)                 # Main Draw/Qualifying
    doubles = models.BooleanField(default=False)
    size = models.IntegerField(null=True)
    class Meta: unique_together = ("tournament", "draw_value")

class Match(models.Model):
    match_id = models.IntegerField(primary_key=True)        # BWF match id (upsert key)
    code = models.CharField(max_length=16, blank=True)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    draw = models.ForeignKey(Draw, on_delete=models.CASCADE, null=True)
    event = models.CharField(max_length=4)
    round_name = models.CharField(max_length=16)            # R32…Final
    round_order = models.IntegerField(default=0)            # derived (§6.4)
    match_time_utc = models.DateTimeField(null=True)
    duration_min = models.IntegerField(null=True)
    court_name = models.CharField(max_length=64, blank=True)
    score_status = models.CharField(max_length=32)          # Normal/Retired/Walkover/…
    reliability = models.IntegerField(null=True)            # 0/1
    winner_side = models.IntegerField(null=True)            # 1 or 2 (who advanced)
    side1_seed = models.CharField(max_length=8, blank=True)
    side2_seed = models.CharField(max_length=8, blank=True)
    scoring_format = models.CharField(max_length=16, blank=True)  # 3x21|3x15|5x11|…

class MatchPlayer(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="lineup")
    side = models.IntegerField()                           # 1 or 2
    player = models.ForeignKey(Player, on_delete=models.PROTECT)
    class Meta: unique_together = ("match", "side", "player")

class Game(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="games")
    game_no = models.IntegerField()
    side1_points = models.IntegerField(); side2_points = models.IntegerField()
    class Meta: unique_together = ("match", "game_no")

# --- Phase 2 outputs ---
class PlayerRating(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    event = models.CharField(max_length=4)                 # discipline bucket
    mu = models.FloatField(); rd = models.FloatField(); sigma = models.FloatField()
    matches_played = models.IntegerField(default=0)
    last_match_utc = models.DateTimeField(null=True)
    class Meta: unique_together = ("player", "event")

class RatingHistory(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    event = models.CharField(max_length=4)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    mu_before = models.FloatField(); mu_after = models.FloatField()
    rd_before = models.FloatField(); rd_after = models.FloatField()
    delta = models.FloatField(); applied_utc = models.DateTimeField()

class RawCache(models.Model):
    url = models.CharField(max_length=512, primary_key=True)
    fetched_utc = models.DateTimeField()
    status = models.IntegerField()
    body = models.TextField()
```

Register all of these in `apps/ingest/admin.py` so ingested data is browsable immediately (the admin is your Phase-1 inspection UI — no custom tooling needed).

## 6. Normalization rules (the ingestion contract)

### 6.1 Upsert, don't append
Stable keys (`tournament_id`, `player_id`, `match_id`). Use `update_or_create` so re-scraping is idempotent.

### 6.2 Side/score orientation
`score[].home` → side 1 (team1); `.away` → side 2 (team2). Sides fixed; never reorder by winner.

### 6.3 `winner` is "who advanced" — CRITICAL
`winner` ∈ {1,2} is the side that progresses, which for **retirements/walkovers can be the side with FEWER points**. Take the winner from `winner` only. Derived margin/dominance (§7.3) is computed **only for `scoreStatus == Normal`**; never inferred from the scoreline otherwise.

### 6.4 Round order
`R128=1,R64=2,R32=3,R16=4,QF=5,SF=6,Final=7` → `round_order`.

### 6.5 Scoring format per match
Store the format for era-comparable margins. Date defaults: `>=2027-01-04`→`3x15`; `2006..2026`→`3x21`; historical→`15x3s`/`11x3s`/`5x7`. Allow explicit per-tournament override (India domestic already used `3x15` from Jul 2026, so date-only defaults misclassify some 2026 matches — prefer explicit when known).

### 6.6 Status mapping
`Normal`→counts fully; `Retired`→partial-info loss for retiree (§7.5); `Walkover`/no-play→ingest but mark rating-excluded; unknown→rating-excluded + log.

## 7. Rating engine spec (Phase 2 — pure package `rating/`)

Deterministic function over normalized matches/games, processed in `match_time_utc` order. No Django imports.

### 7.1 Per-(player, discipline) rating with uncertainty
`(mu, rd, sigma)` Glicko-2 style. Defaults `mu=1500, rd=350, sigma=0.06, tau=0.5`. Independent per discipline (a man may hold MS/MD/XD).

### 7.2 Pair strength = blend of members
`R_T = mean(mu_i)`, `RD_T = sqrt(mean(rd_i^2))`. Default average; weaker-partner weighting / synergy is a later refinement (`PAIR_BLEND`).

### 7.3 Format-normalized dominance → margin multiplier
For `Normal` only: `d = winner_points / (winner_points + loser_points)` across the match — comparable across `3x21`/`3x15`/`5x11`/side-out. Floor at `D_FLOOR` (0.50) for close-games wins. `M = 1 + LAMBDA*(2d-1)` clamped `[M_MIN,M_MAX]` (`0.5, 0.7, 1.4`). Win/loss stays binary; `M` only scales magnitude.

### 7.4 Per-player update scaled by uncertainty
Team surprise `(S - E)`, `E = 1/(1+10^((R_opp-R_T)/400))` with `g(RD_opp)` damping. Each player updates using **their own** `rd` × `M` × optional `W_tier`. New/seeded (high `rd`) converge fast; established (low `rd`) barely move — the fairness mechanism for "strong A + new C", and why A's gains propagate into every future A-pairing for free. Shrink `rd` after; inflate for inactivity.

### 7.5 Retirement / walkover
Walkover→skip. Retirement→loss for retiree (winner from `winner` field), reduced update (`K_RETIRE=0.3`), dominance NOT read from scoreline. Optional stricter policy: only count after ≥1 completed game; flag injury retirements.

### 7.6 Seeding & cold start
MVP: all start `mu=1500, rd=350`; self-corrects after ~10–15 matches each. Phase 2: seed `mu` from BWF `currentRank` via percentile→Elo curve with **high `rd`** (priors, not truth). Doubles ranks are per-pair → seed an individual from best/points-weighted partnership (`SEED_DOUBLES_FROM`).

### 7.7 Determinism
Order `(match_time_utc, round_order, match_id)`. `rate --rebuild` recomputes from scratch, identical output.

## 8. Config (`settings.py` / env; defaults overridable)
`TOURNAMENT_CODES`, `INCLUDE_QUALIFYING=false`, `RATE_LIMIT_QPS=1`, `HTTP_TIMEOUT=20`, `USER_AGENT`, `MU_INIT=1500`, `RD_INIT=350`, `SIGMA_INIT=0.06`, `TAU=0.5`, `PAIR_BLEND=mean`, `LAMBDA=0.5`, `M_MIN=0.7`, `M_MAX=1.4`, `D_FLOOR=0.50`, `K_RETIRE=0.3`, `RD_INFLATE_C=…`, `TIER_WEIGHTS={Super1000:1.1,…,Super100:0.9}`.

## 9. Tech stack
Python 3.12 · **Django 5** (ORM, admin, migrations, management commands) · **Django REST Framework** (Phase 3 read API) · **React + Vite** (Phase 3 UI) · **Docker / docker-compose** (Postgres + web; frontend + scrape worker later). Ingestion: `httpx` client, `pydantic` v2 to validate raw payloads before ORM writes. Tests: `pytest` + `pytest-django`. The `rating/` package is framework-free.

## 10. Commands
```bash
# local (no Docker) for the first win
python manage.py migrate
python manage.py scrape --code <GUID>     # detail -> draws -> draw-data -> DB (cached, idempotent)
python manage.py scrape --all             # iterate settings.TOURNAMENT_CODES
python manage.py ingest_status            # row counts, last fetch, cache hits
python manage.py rate                     # Phase 2 incremental
python manage.py rate --rebuild           # Phase 2 deterministic recompute
python manage.py leaderboard --event XD   # Phase 2 export
pytest                                     # tests

# Docker (Phase 3 / prod-like)
docker compose up --build                  # db + web (+ frontend, worker when added)
docker compose run --rm web python manage.py scrape --all
```

## 11. Deployment / Docker (Phase 3)
`docker-compose.yml` services: `db` (postgres:16, volume), `web` (Django/DRF, depends_on db). Add later: `frontend` (Vite build served static or via nginx) and `worker`/cron for scheduled `scrape --all`. Local dev stays SQLite + no Docker until Phase 3 — don't let container setup delay the first ingested result.

## 12. Serving design (Phase 3 — DRF + React)
DRF read-only viewsets: `GET /api/leaderboard?event=XD` (paginated `PlayerRating` joined to `Player`), `GET /api/players/{id}` (ratings across disciplines + `RatingHistory`), `GET /api/matches/{id}`. React (Vite): leaderboard table with discipline tabs, player page (rating-over-time from history), match detail. No auth for MVP; read-only.

## 13. Milestones
- **M1 (Phase 1) — buildable now, local/SQLite/no Docker.** `scrape` ingests tournament→draws→draw-data, normalizes, idempotent, cached, rate-limited; admin browsable. **Acceptance:** Malaysia Masters 2026 XD draw ingests to 31 main-draw matches with correct winners incl. the retired `344` (winner side 2 despite trailing 5-11); players deduped by id; re-run changes nothing.
- **M2 (Phase 2).** `rating/` package + `rate`/`rate --rebuild`; `PlayerRating`+`RatingHistory` populated; leaderboard export. Deterministic; retirements handled; uncertainty shrinks with matches.
- **M3 (Phase 3).** Postgres + Docker; DRF API; React leaderboard/player UI; scheduled scrape worker.

## 14. Testing
Fixtures: captured JSON in `tests/fixtures/` (day-matches, draw-data with the retired match, statistics, draws, detail, players). Unit: normalization (side orientation, winner-vs-score for retirement, round_order, format defaulting), dominance across formats, uncertainty-scaled update, retirement path. Integration: ingest fixture tournament → assert row counts + known winners/scores; run `rate` twice → identical ratings.
