"""Normalize validated raw payloads into ORM rows (PRD §6).

The ingestion contract. Every rule here is stack-independent and, if ignored,
silently corrupts ratings downstream (CLAUDE.md "CRITICAL domain rules"):

  * winner_side comes from the `winner` field only — never from the scoreline
  * side1 = team1 = score.home, side2 = team2 = score.away — never reordered
  * scoring_format is stored per match (era/format-comparable margins later)
  * non-Normal statuses are ingested but flagged rating_excluded per §6.6
  * everything upserts on stable ids so re-scraping changes nothing

This module writes rows but performs NO rating math (that is Phase 2, in the
pure `rating/` package).
"""
from __future__ import annotations

import logging
import re
import zlib
from datetime import date

from django.db import transaction

from .models import Draw, Game, Match, MatchPlayer, Player, Tournament
from .schemas import CalendarTournament, DrawData, MatchRaw, TournamentDetail

logger = logging.getLogger(__name__)

# --- PRD §6.4 round order ---------------------------------------------------
ROUND_ORDER = {
    "R128": 1,
    "R64": 2,
    "R32": 3,
    "R16": 4,
    "QF": 5,
    "SF": 6,
    "Final": 7,
    "F": 7,
}

# Aliases seen in roundName strings ("Round of 32", "Quarter Finals", ...).
_ROUND_ALIASES = {
    "round of 128": "R128",
    "round of 64": "R64",
    "round of 32": "R32",
    "round of 16": "R16",
    "quarter": "QF",
    "quarterfinal": "QF",
    "quarter finals": "QF",
    "semi": "SF",
    "semifinal": "SF",
    "semi finals": "SF",
    "final": "Final",
}

# --- PRD §6.6 status mapping ------------------------------------------------
# score_status_value -> (canonical label, rating_excluded)
STATUS_MAP = {
    "Normal": ("Normal", False),
    "Retired": ("Retired", False),  # counts, reduced-weight (engine's K_RETIRE)
    "Walkover": ("Walkover", True),
    "No Match": ("NoMatch", True),
    "NoMatch": ("NoMatch", True),
    "Disqualified": ("Disqualified", True),
    # Seen live in the 2026 season: a bye/promotion — no contest was played,
    # so it is ingested for completeness but excluded from rating.
    "Promoted": ("Promoted", True),
    "Bye": ("Bye", True),
}


# --- event canonicalization (PRD §6.6 discipline bucket) --------------------
# BWF payloads spell the discipline inconsistently across eras/languages
# ("MS", "Men's Singles", "Mens Singles", "ms", "Individual Masculino", …).
# Fold these into the five open codes; keep age-group (masters) and youth events
# as distinct suffixed buckets so they never pollute the open pools; flag
# exhibitions for rating exclusion.
OPEN_EVENTS = ("MS", "WS", "MD", "WD", "XD")
_AGE = re.compile(r"\b(35|40|45|50|55|60|65|70|75)\b")
_YOUTH = re.compile(r"u[\s-]?(1[3-9])\b")


def _detect_discipline(low: str) -> str | None:
    """Best-effort open-discipline code from a lowercased label, else None."""
    if "mixed" in low or "mixto" in low or "mixte" in low or low.startswith(("xd", "mx")):
        return "XD"
    women = (
        "women" in low or "woman" in low or "girl" in low or "female" in low
        or "femenin" in low or "dames" in low or "damen" in low
        or low.startswith(("ws", "wd", "gs", "gd"))
    )
    # "men" is a substring of "women" — only credit it when women isn't present.
    men = (
        "boy" in low or "masculino" in low or "hommes" in low or "herren" in low
        or (("men" in low or "man" in low) and not women)
        or low.startswith(("ms", "md", "bs", "bd"))
    )
    doubles = (
        "double" in low or "dobles" in low or "doppel" in low
        or low.startswith(("md", "wd", "bd", "gd", "dd"))
    )
    if doubles:
        if women and not men:
            return "WD"
        return "MD" if men else None
    if "single" in low or "individual" in low or low.startswith(("ms", "ws", "bs", "gs")):
        if women and not men:
            return "WS"
        return "MS" if men else None
    return None


def canonical_event(raw: str) -> tuple[str, bool]:
    """Return (event_code, is_exhibition).

    Open disciplines fold to MS/WS/MD/WD/XD; masters keep an age suffix (MS45),
    youth a U-age suffix (MSU19); unmappable labels pass through unchanged.
    """
    if not raw:
        return raw, False
    s = raw.strip()
    if s in OPEN_EVENTS:
        return s, False
    low = s.lower()
    exhibition = any(w in low for w in ("exhibition", "farewell", "unified", "plate"))
    base = _detect_discipline(low)
    if base is None:
        return s, exhibition
    youth = _YOUTH.search(low)
    if youth:
        return f"{base}U{youth.group(1)}", exhibition
    age = _AGE.search(s)
    if age:
        return f"{base}{age.group(1)}", exhibition
    return base, exhibition


def round_order(round_name: str) -> int:
    """Map a roundName to its chronological order (PRD §6.4). Unknown -> 0."""
    if not round_name:
        return 0
    key = round_name.strip()
    if key in ROUND_ORDER:
        return ROUND_ORDER[key]
    alias = _ROUND_ALIASES.get(key.lower())
    return ROUND_ORDER.get(alias, 0)


def default_scoring_format(match_date: date | None) -> str:
    """Date-based scoring-format default (PRD §6.5).

    Explicit per-tournament overrides should win over this (some 2026 domestic
    events already used 3x15) — the caller passes an override when known.
    """
    if match_date is None:
        return ""
    if match_date >= date(2027, 1, 4):
        return "3x15"
    if match_date >= date(2006, 1, 1):
        return "3x21"
    # historical eras — coarse buckets; refine per-tournament when known
    if match_date >= date(2002, 1, 1):
        return "15x3s"
    return "5x7"


def map_status(score_status_value: str) -> tuple[str, bool]:
    """Return (canonical_status, rating_excluded); unknown -> excluded + log."""
    if score_status_value in STATUS_MAP:
        return STATUS_MAP[score_status_value]
    logger.warning("unknown scoreStatusValue %r -> rating-excluded", score_status_value)
    return (score_status_value or "Unknown", True)


# --- upserts ----------------------------------------------------------------
def upsert_tournament(detail: TournamentDetail) -> Tournament:
    category_name = detail.category_model.name if detail.category_model else ""
    obj, _ = Tournament.objects.update_or_create(
        tournament_id=detail.id,
        defaults={
            "code": detail.code,
            "name": detail.name,
            "slug": detail.slug,
            "start_date": detail.start_date,
            "end_date": detail.end_date,
            "category_id": detail.tournament_category_id,
            "category_name": category_name,
            "series_id": detail.tournament_series_id,
            "prize_money": detail.prize_money,
            "venue_name": detail.venue_name,
        },
    )
    return obj


def _upsert_player(ref) -> Player:
    obj, _ = Player.objects.update_or_create(
        player_id=ref.id,
        defaults={
            "name_display": ref.name_display or ref.name_short or str(ref.id),
            "first_name": ref.first_name,
            "last_name": ref.last_name,
            "name_short": ref.name_short,
            "slug": ref.slug,
            "country_code": ref.country_code,
        },
    )
    return obj


@transaction.atomic
def normalize_match(
    raw: MatchRaw,
    *,
    tournament: Tournament,
    draw: Draw | None,
    scoring_format_override: str | None = None,
) -> Match:
    """Upsert one match with its lineup and games. Idempotent on match_id."""
    status_label, rating_excluded = map_status(raw.score_status_value)
    event_code, is_exhibition = canonical_event(raw.event_name)
    match_date = raw.match_time_utc.date() if raw.match_time_utc else tournament.start_date
    scoring_format = scoring_format_override or default_scoring_format(match_date)

    match, _ = Match.objects.update_or_create(
        match_id=raw.id,
        defaults={
            "code": raw.code,
            "tournament": tournament,
            "draw": draw,
            "event": event_code,
            "round_name": raw.round_name,
            "round_order": round_order(raw.round_name),
            "match_time_utc": raw.match_time_utc,
            "duration_min": raw.duration,
            "court_name": raw.court_name,
            "score_status": status_label,
            "reliability": raw.reliability,
            "winner_side": raw.winner,  # who ADVANCED — never inferred from score
            "side1_seed": raw.team1_seed,
            "side2_seed": raw.team2_seed,
            "scoring_format": scoring_format,
            "rating_excluded": rating_excluded or is_exhibition,
        },
    )

    # Rebuild lineup (side 1 = team1, side 2 = team2 — fixed orientation).
    match.lineup.all().delete()
    for side, team in ((1, raw.team1), (2, raw.team2)):
        if not team:
            continue
        for ref in team.players:
            player = _upsert_player(ref)
            MatchPlayer.objects.update_or_create(
                match=match, side=side, player=player
            )

    # Rebuild games from the flat score[] (home=side1, away=side2).
    match.games.all().delete()
    for i, g in enumerate(raw.score, start=1):
        Game.objects.update_or_create(
            match=match,
            game_no=g.set or i,
            defaults={"side1_points": g.home, "side2_points": g.away},
        )

    return match


def normalize_draw_data(
    data: DrawData,
    *,
    tournament: Tournament,
    draw: Draw | None,
    scoring_format_override: str | None = None,
) -> tuple[int, int]:
    """Normalize every match in a draw. Returns (ingested, skipped).

    A single malformed match is logged and skipped so the rest of the draw
    still ingests (PRD §9 "log + skip rather than crash").
    """
    ingested = skipped = 0
    for raw in data.matches:
        try:
            normalize_match(
                raw,
                tournament=tournament,
                draw=draw,
                scoring_format_override=scoring_format_override,
            )
            ingested += 1
        except Exception:  # noqa: BLE001 - isolate a bad match, keep the draw
            logger.exception("skipping malformed match id=%s", getattr(raw, "id", "?"))
            skipped += 1
    return ingested, skipped


# --- day-matches path (PRD §4.4) --------------------------------------------
# day-matches is the only live-confirmed endpoint (see api/endpoints.CONFIRMED),
# so it is the primary collector. It lacks a numeric tournament id, so we derive
# a stable synthetic primary key from the GUID; `code` stays unique and lets a
# future vue-tournament-detail pass reconcile to the real id.
def synthetic_tournament_id(code: str) -> int:
    """Deterministic, collision-resistant int PK from a tournament GUID.

    CRC32 masked to signed 32-bit so it fits IntegerField on every backend.
    Stable across runs -> re-scraping upserts the same Tournament row.
    """
    return zlib.crc32(code.encode("utf-8")) & 0x7FFFFFFF


@transaction.atomic
def upsert_tournament_from_calendar(cal: CalendarTournament) -> Tournament:
    """Upsert a Tournament from a calendar entry — the AUTHORITATIVE source.

    Carries the real numeric id, dates, and tier (category), so it supersedes
    the synthetic-id row a day-matches-only run may have created for the same
    GUID. If such a row exists under a different PK, migrate its children to the
    real id and drop the stale row (keeps re-collection idempotent).
    """
    defaults = {
        "code": cal.code,
        "name": cal.name,
        "slug": cal.slug,
        "start_date": cal.start,
        "end_date": cal.end,
        "category_name": cal.category,
        "prize_money": cal.prize_money_decimal,
        "venue_name": cal.location,
    }

    stale = (
        Tournament.objects.filter(code=cal.code)
        .exclude(tournament_id=cal.id)
        .first()
        if cal.code
        else None
    )
    if stale is not None:
        # 1) create the real-id row (blank code first to avoid the unique clash)
        obj, _ = Tournament.objects.update_or_create(
            tournament_id=cal.id, defaults={**defaults, "code": ""}
        )
        # 2) re-point children, 3) drop the stale row, 4) set the real code
        Match.objects.filter(tournament=stale).update(tournament=obj)
        Draw.objects.filter(tournament=stale).update(tournament=obj)
        stale.delete()
        obj.code = cal.code
        obj.save(update_fields=["code"])
        return obj

    obj, _ = Tournament.objects.update_or_create(
        tournament_id=cal.id, defaults=defaults
    )
    return obj


def upsert_tournament_from_code(code: str, name: str = "") -> Tournament:
    """Minimal Tournament from a day-matches payload (no detail endpoint).

    Only code+name are known here; category/tier and exact dates stay blank
    until vue-tournament-detail is captured. Keyed by the synthetic id but kept
    idempotent on `code`.
    """
    existing = Tournament.objects.filter(code=code).first()
    tid = existing.tournament_id if existing else synthetic_tournament_id(code)
    defaults = {"code": code}
    if name:
        defaults["name"] = name
    obj, _ = Tournament.objects.update_or_create(
        tournament_id=tid,
        defaults={**defaults, "name": defaults.get("name", existing.name if existing else name or code)},
    )
    return obj


def _upsert_draw_from_match(tournament: Tournament, raw: MatchRaw) -> Draw | None:
    """Group day-matches into Draw rows by drawCode (+eventName).

    If a Draw already exists (e.g. created by the draw-data path with its real
    stage/qualification), reuse it untouched — day-matches can't tell qualifying
    from main, so it must not clobber that richer info.
    """
    if not raw.draw_code:
        return None
    existing = Draw.objects.filter(
        tournament=tournament, draw_value=raw.draw_code
    ).first()
    if existing is not None:
        return existing
    return Draw.objects.create(
        tournament=tournament,
        draw_value=raw.draw_code,
        event=raw.event_name,
        stage="Main Draw",  # day-matches doesn't expose qualification/stage
        doubles=raw.event_name in {"MD", "WD", "XD"},
    )


def normalize_day_matches(
    matches: list[MatchRaw],
    *,
    tournament: Tournament,
    scoring_format_override: str | None = None,
) -> tuple[int, int]:
    """Normalize a day-matches array. Returns (ingested, skipped).

    Skips team-match rubbers and entries missing both lineups. A malformed
    match is logged and skipped so the rest of the day still ingests.
    """
    ingested = skipped = 0
    for raw in matches:
        try:
            if not (raw.team1 and raw.team1.players) and not (
                raw.team2 and raw.team2.players
            ):
                skipped += 1
                continue
            draw = _upsert_draw_from_match(tournament, raw)
            normalize_match(
                raw,
                tournament=tournament,
                draw=draw,
                scoring_format_override=scoring_format_override,
            )
            ingested += 1
        except Exception:  # noqa: BLE001 - isolate a bad match, keep the day
            logger.exception("skipping malformed match id=%s", getattr(raw, "id", "?"))
            skipped += 1
    return ingested, skipped
