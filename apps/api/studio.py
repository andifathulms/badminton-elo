"""Studio write API — the manual-curation backend behind the in-app admin.

Everything here mutates ingested data and is gated to staff (SessionAuthentication
+ IsAdminUser). The public read API in views.py stays open and untouched.

Why this exists: old tournaments (pre-2006) come from Wikipedia/manual sources
with gaps — a missing logo, a wrong date, a match that was never scraped, a
player whose nationality is blank. This lets a curator fix those in-app instead
of hand-editing the DB.

Synthetic ids: Match.match_id and Player.player_id are non-auto integer PKs
sourced from BWF. Manually-created rows draw from a high band (MANUAL_ID_BASE)
that BWF's real ids never reach, so a later scrape can't collide with them.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.ingest.models import Game, Match, MatchPlayer, Player, Tournament
from apps.ingest.normalize import default_scoring_format, map_status, round_order

from .serializers import PlayerBriefSerializer, TournamentListSerializer

# BWF ids sit well below this; manual rows count up from here (fits int32).
MANUAL_ID_BASE = 2_000_000_000


def staff(view):
    """Decorator stack for a staff-only write view (session auth + CSRF)."""
    return authentication_classes([SessionAuthentication])(
        permission_classes([IsAdminUser])(view)
    )


def _next_manual_id(model, pk_field: str) -> int:
    """Allocate the next id in the manual band for `model`."""
    top = (
        model.objects.filter(**{f"{pk_field}__gte": MANUAL_ID_BASE})
        .aggregate(m=Max(pk_field))["m"]
    )
    return (top + 1) if top else MANUAL_ID_BASE


def _norm_country(v) -> str:
    """Normalize a nationality code: trimmed, uppercased if alphabetic."""
    s = (v or "").strip()
    return s.upper() if s.isalpha() else s


# --- Tournament metadata ----------------------------------------------------
class TournamentEditSerializer(serializers.ModelSerializer):
    """Editable tournament metadata. All fields optional (PATCH semantics)."""

    class Meta:
        model = Tournament
        fields = (
            "name",
            "category_name",
            "start_date",
            "end_date",
            "venue_name",
            "prize_money",
            "logo_url",
        )
        extra_kwargs = {f: {"required": False} for f in fields}


@api_view(["GET", "POST"])
@staff
def tournament_collection(request):
    """GET  /api/studio/tournaments?q= — search ALL tournaments (unlike the
    public list, this includes 0-match shells, which are exactly what a curator
    needs to reach to add matches).
    POST /api/studio/tournaments — create a tournament from scratch."""
    if request.method == "GET":
        return _tournament_search(request)

    name = (request.data.get("name") or "").strip()
    if not name:
        raise ValidationError({"name": "required"})
    ser = TournamentEditSerializer(data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    with transaction.atomic():
        tid = _next_manual_id(Tournament, "tournament_id")
        t = Tournament.objects.create(tournament_id=tid, **ser.validated_data)
    from django.db.models import Count

    fresh = Tournament.objects.annotate(match_count=Count("matches")).get(pk=t.pk)
    return Response(TournamentListSerializer(fresh).data, status=status.HTTP_201_CREATED)


def _tournament_search(request):
    from django.db.models import Count

    qs = Tournament.objects.annotate(match_count=Count("matches"))
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(name__icontains=q)
    year = request.query_params.get("year")
    if year and year.isdigit():
        qs = qs.filter(start_date__year=int(year))
    qs = qs.order_by("-start_date", "name")[:20]
    return Response({"results": TournamentListSerializer(qs, many=True).data})


@api_view(["PATCH"])
@staff
def tournament_edit(request, tournament_id):
    """PATCH /api/studio/tournaments/{id} — update tournament metadata."""
    try:
        t = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        raise NotFound("tournament not found")
    ser = TournamentEditSerializer(t, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    from django.db.models import Count

    fresh = Tournament.objects.annotate(match_count=Count("matches")).get(pk=t.pk)
    return Response(TournamentListSerializer(fresh).data)


# --- Players ----------------------------------------------------------------
@api_view(["POST"])
@staff
def player_create(request):
    """POST /api/studio/players {name_display, country_code, gender?} — create a
    manually-entered player (for matches whose players BWF never indexed)."""
    name = (request.data.get("name_display") or "").strip()
    if not name:
        raise ValidationError({"name_display": "required"})
    gender = (request.data.get("gender") or "").strip().upper()
    if gender and gender not in ("M", "F"):
        raise ValidationError({"gender": "must be M, F, or blank"})
    with transaction.atomic():
        pid = _next_manual_id(Player, "player_id")
        p = Player.objects.create(
            player_id=pid,
            name_display=name,
            country_code=_norm_country(request.data.get("country_code")),
            gender=gender,
        )
    return Response(PlayerBriefSerializer(p).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@staff
def player_edit(request, player_id):
    """PATCH /api/studio/players/{id} — edit nationality (and name/gender)."""
    try:
        p = Player.objects.get(pk=player_id)
    except Player.DoesNotExist:
        raise NotFound("player not found")
    if "country_code" in request.data:
        p.country_code = _norm_country(request.data.get("country_code"))
    if "name_display" in request.data:
        name = (request.data.get("name_display") or "").strip()
        if not name:
            raise ValidationError({"name_display": "cannot be blank"})
        p.name_display = name
    if "gender" in request.data:
        g = (request.data.get("gender") or "").strip().upper()
        if g and g not in ("M", "F"):
            raise ValidationError({"gender": "must be M, F, or blank"})
        p.gender = g
    p.save()
    return Response(PlayerBriefSerializer(p).data)


# --- Matches ----------------------------------------------------------------
# Canonical statuses a curator may set. map_status() (shared with the scraper)
# turns each into its (label, rating_excluded) pair — so a Walkover entered here
# is excluded from rating exactly as a scraped one is.
STATUS_CHOICES = (
    "Normal", "Retired", "Walkover", "NoMatch", "Disqualified", "Promoted", "Bye",
)


def _parse_dt(v):
    """Accept an ISO datetime or a bare date (old tournaments often only know a
    day). Naive values are treated as UTC (the project's TIME_ZONE)."""
    if not v:
        return None
    dt = parse_datetime(v)
    if dt is None:
        d = parse_date(v)
        if d is None:
            raise ValidationError({"match_time_utc": "not a valid date/datetime"})
        from datetime import datetime

        dt = datetime(d.year, d.month, d.day)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _resolve_side(ids, key):
    """Validate a side's player ids exist; return them as ints (order kept)."""
    if ids is None:
        return None
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        raise ValidationError({key: "must be a list of player ids"})
    if not (1 <= len(ids) <= 2):
        raise ValidationError({key: "a side needs 1 or 2 players"})
    known = set(Player.objects.filter(player_id__in=ids).values_list("player_id", flat=True))
    missing = [i for i in ids if i not in known]
    if missing:
        raise ValidationError({key: f"unknown player id(s): {missing}"})
    return ids


def _apply_scalars(m, data, tournament):
    """Set the editable scalar fields present in `data` onto match `m`.

    winner_side is taken verbatim (who ADVANCED — never inferred from the
    scoreline, per the domain rules), and score_status drives rating_excluded.
    """
    if "event" in data:
        m.event = (data["event"] or "").strip()
    if "round_name" in data:
        rn = (data["round_name"] or "").strip()
        m.round_name = rn
        m.round_order = round_order(rn)
    if "match_time_utc" in data:
        m.match_time_utc = _parse_dt(data["match_time_utc"])
    if "winner_side" in data:
        ws = data["winner_side"]
        if ws in ("", None):
            m.winner_side = None
        elif str(ws) in ("1", "2"):
            m.winner_side = int(ws)
        else:
            raise ValidationError({"winner_side": "must be 1, 2, or null"})
    if "score_status" in data:
        raw = (data["score_status"] or "Normal").strip()
        if raw not in STATUS_CHOICES:
            raise ValidationError({"score_status": f"one of {', '.join(STATUS_CHOICES)}"})
        m.score_status, m.rating_excluded = map_status(raw)
    if "side1_country" in data:
        m.side1_country = _norm_country(data["side1_country"])
    if "side2_country" in data:
        m.side2_country = _norm_country(data["side2_country"])
    if "scoring_format" in data:
        m.scoring_format = (data["scoring_format"] or "").strip()
    # Fall back to the era/date default so margins stay format-comparable.
    if not m.scoring_format:
        d = m.match_time_utc.date() if m.match_time_utc else tournament.start_date
        m.scoring_format = default_scoring_format(d)


def _set_side(m, side, ids):
    MatchPlayer.objects.filter(match=m, side=side).delete()
    for pid in ids:
        MatchPlayer.objects.create(match=m, side=side, player_id=pid)


def _set_games(m, games):
    """Rebuild the game rows. score is side1(home)-side2(away), never reordered."""
    if games is None:
        return
    m.games.all().delete()
    for i, g in enumerate(games, start=1):
        try:
            a, b = int(g[0]), int(g[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValidationError({"games": f"game {i} must be [side1, side2] integers"})
        if a < 0 or b < 0:
            raise ValidationError({"games": f"game {i} points must be ≥ 0"})
        Game.objects.create(match=m, game_no=i, side1_points=a, side2_points=b)


def _match_repr(m) -> dict:
    """Full editable projection of a match for the Studio editor."""
    lineup = list(m.lineup.select_related("player").all())
    return {
        "match_id": m.match_id,
        "event": m.event,
        "round_name": m.round_name,
        "round_order": m.round_order,
        "match_time_utc": m.match_time_utc,
        "winner_side": m.winner_side,
        "score_status": m.score_status,
        "scoring_format": m.scoring_format,
        "rating_excluded": m.rating_excluded,
        "side1_country": m.side1_country,
        "side2_country": m.side2_country,
        "is_manual": (m.source_key or "").startswith("manual:"),
        "side1": PlayerBriefSerializer(
            [l.player for l in lineup if l.side == 1], many=True
        ).data,
        "side2": PlayerBriefSerializer(
            [l.player for l in lineup if l.side == 2], many=True
        ).data,
        "games": [[g.side1_points, g.side2_points] for g in m.games.order_by("game_no")],
    }


@api_view(["GET", "POST"])
@staff
def match_collection(request, tournament_id):
    """GET  /api/studio/tournaments/{id}/matches — every match, editable form.
    POST /api/studio/tournaments/{id}/matches — create a match manually."""
    try:
        t = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        raise NotFound("tournament not found")

    if request.method == "GET":
        matches = (
            Match.objects.filter(tournament=t)
            .prefetch_related("lineup__player", "games")
            .order_by("event", "round_order", "match_id")
        )
        return Response({"results": [_match_repr(m) for m in matches]})

    data = request.data
    if not (data.get("event") or "").strip():
        raise ValidationError({"event": "required"})
    s1 = _resolve_side(data.get("side1"), "side1")
    s2 = _resolve_side(data.get("side2"), "side2")
    if s1 is None or s2 is None:
        raise ValidationError({"detail": "both side1 and side2 are required"})
    if set(s1) & set(s2):
        raise ValidationError({"detail": "a player can't be on both sides"})

    with transaction.atomic():
        mid = _next_manual_id(Match, "match_id")
        m = Match(match_id=mid, tournament=t, source_key=f"manual:{mid}",
                  score_status="Normal", rating_excluded=False)
        _apply_scalars(m, {"score_status": "Normal", **data}, t)
        m.save()
        _set_side(m, 1, s1)
        _set_side(m, 2, s2)
        _set_games(m, data.get("games") or [])
    return Response(_match_repr(m), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@staff
def match_detail(request, match_id):
    """PATCH /api/studio/matches/{id} — edit; DELETE — remove the match."""
    try:
        m = Match.objects.select_related("tournament").get(pk=match_id)
    except Match.DoesNotExist:
        raise NotFound("match not found")

    if request.method == "DELETE":
        m.delete()  # cascades lineup + games
        return Response(status=status.HTTP_204_NO_CONTENT)

    data = request.data
    s1 = _resolve_side(data["side1"], "side1") if "side1" in data else None
    s2 = _resolve_side(data["side2"], "side2") if "side2" in data else None
    # Overlap check against the final lineup (provided side else existing).
    final1 = set(s1) if s1 is not None else set(
        m.lineup.filter(side=1).values_list("player_id", flat=True)
    )
    final2 = set(s2) if s2 is not None else set(
        m.lineup.filter(side=2).values_list("player_id", flat=True)
    )
    if final1 & final2:
        raise ValidationError({"detail": "a player can't be on both sides"})

    with transaction.atomic():
        _apply_scalars(m, data, m.tournament)
        m.save()
        if s1 is not None:
            _set_side(m, 1, s1)
        if s2 is not None:
            _set_side(m, 2, s2)
        if "games" in data:
            _set_games(m, data["games"] or [])
    m.refresh_from_db()
    return Response(_match_repr(m))


# --- Rebuild ratings --------------------------------------------------------
@api_view(["POST"])
@staff
def rebuild(request):
    """POST /api/studio/rebuild — re-rate the current data + rebuild analytics in
    the background (no collection). Poll GET /api/refresh/status for progress."""
    from . import refresh

    if not refresh._allowed():
        return Response(
            {"allowed": False, "detail": "Rebuild is disabled on this deployment."},
            status=status.HTTP_403_FORBIDDEN,
        )
    started, snap = refresh.begin("rebuild")
    return Response({"started": started, **snap})
