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
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.ingest.models import Player, Tournament

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
