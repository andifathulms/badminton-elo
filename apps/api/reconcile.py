"""Human-in-the-loop player reconciliation review.

Served against the MASTER db (local `manage.py runserver`, not the read-only
Docker snapshot) so decisions persist. Surfaces Wikipedia-sourced players whose
name matches one or more BWF players but which weren't auto-merged (ambiguous,
or blank Wiki country). The reviewer compares both players' match histories and
rules: same person (merge, picking the canonical BWF id) or distinct.
"""
from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.shortcuts import render
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.ingest.models import (
    Match, MatchPlayer, Player, ReconcileDecision,
)
from apps.ingest.management.commands.reconcile_players import norm, canon_country

BASE = 2_000_000_000


def _matches_for(player_id, limit=60):
    """Compact match history: tournament, year, event, round, partners, opps."""
    mps = (
        MatchPlayer.objects.filter(player_id=player_id)
        .select_related("match__tournament")
        .prefetch_related("match__lineup__player", "match__games")
        .order_by("-match__tournament__start_date", "match__round_order")[:limit]
    )
    out = []
    for mp in mps:
        m = mp.match
        lineup = list(m.lineup.all())
        opps = [l.player.name_display for l in lineup if l.side != mp.side]
        partners = [l.player.name_display for l in lineup
                    if l.side == mp.side and l.player_id != player_id]
        games = [f"{g.side1_points}-{g.side2_points}" for g in m.games.all()]
        out.append({
            "tournament": m.tournament.name,
            "year": m.tournament.start_date.year if m.tournament.start_date else None,
            "event": m.event,
            "round": m.round_name,
            "partners": partners,
            "opponents": opps,
            "score": " ".join(games),
            "won": m.winner_side == mp.side,
        })
    return out


def _player_brief(p):
    return {"player_id": p.player_id, "name": p.name_display,
            "country": p.country_code, "matches": MatchPlayer.objects
            .filter(player=p).count()}


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def cases(request):
    """Unresolved Wiki players whose name matches >=1 BWF player."""
    decided = set(ReconcileDecision.objects.values_list("wiki_title", flat=True))
    bwf_by_name = defaultdict(list)
    for p in Player.objects.filter(player_id__lt=BASE):
        bwf_by_name[norm(p.name_display)].append(p)

    # default: only the genuinely ambiguous (2+ BWF candidates); ?all=1 also
    # shows single-candidate blank-country cases (Axelsen-type).
    show_all = request.query_params.get("all") == "1"
    out = []
    for w in Player.objects.filter(player_id__gte=BASE).exclude(wiki_title=""):
        if w.wiki_title in decided:
            continue
        cands = bwf_by_name.get(norm(w.name_display), [])
        if not cands:
            continue
        # auto-merges already applied; what's left is ambiguous or blank-country
        wc = canon_country(w.country_code)
        exact = [c for c in cands if canon_country(c.country_code) == wc] if w.country_code else []
        if w.country_code and len(exact) == 1 and len(cands) == 1:
            continue  # would have auto-merged
        if not show_all and len(cands) < 2:
            continue  # hide easy single-candidate cases unless ?all=1
        out.append({
            "wiki": _player_brief(w),
            "wiki_matches": _matches_for(w.player_id),
            "candidates": [
                {**_player_brief(c), "match_list": _matches_for(c.player_id)}
                for c in sorted(cands, key=lambda c: -MatchPlayer.objects.filter(player=c).count())
            ],
        })
    out.sort(key=lambda c: -c["wiki"]["matches"])
    return Response({"count": len(out), "cases": out})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def decide(request):
    """Body: {wiki_id, action: 'merge'|'distinct', target_id?, merge_bwf?: [a,b]}."""
    d = request.data
    wiki = Player.objects.filter(player_id=d["wiki_id"]).first()
    action = d.get("action")
    with transaction.atomic():
        if action == "merge":
            target = Player.objects.get(player_id=d["target_id"])
            _repoint(wiki, target)
            if not target.wiki_title:
                target.wiki_title = wiki.wiki_title
            if not target.country_code and wiki.country_code:
                target.country_code = wiki.country_code
            target.save()
            ReconcileDecision.objects.update_or_create(
                wiki_title=wiki.wiki_title,
                defaults={"decision": "merged", "target_player_id": target.player_id})
            wiki.delete()
        elif action == "distinct":
            ReconcileDecision.objects.update_or_create(
                wiki_title=wiki.wiki_title, defaults={"decision": "distinct"})
        # optional: also merge two BWF duplicates (a -> keep b)
        mb = d.get("merge_bwf")
        if mb:
            a = Player.objects.get(player_id=mb[0])
            b = Player.objects.get(player_id=mb[1])
            _repoint(a, b)
            a.delete()
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def merge_all_single(request):
    """Auto-merge every remaining single-candidate case (unique name, one BWF
    match — the blank-country 'Axelsen' type). Multi-candidate ambiguous cases
    are left untouched for manual review."""
    decided = set(ReconcileDecision.objects.values_list("wiki_title", flat=True))
    bwf_by_name = defaultdict(list)
    for p in Player.objects.filter(player_id__lt=BASE):
        bwf_by_name[norm(p.name_display)].append(p)
    merged = 0
    for w in list(Player.objects.filter(player_id__gte=BASE).exclude(wiki_title="")):
        if w.wiki_title in decided:
            continue
        cands = bwf_by_name.get(norm(w.name_display), [])
        if len(cands) != 1:
            continue
        target = cands[0]
        with transaction.atomic():
            _repoint(w, target)
            if not target.wiki_title:
                target.wiki_title = w.wiki_title
            if not target.country_code and w.country_code:
                target.country_code = w.country_code
            target.save()
            ReconcileDecision.objects.update_or_create(
                wiki_title=w.wiki_title,
                defaults={"decision": "merged", "target_player_id": target.player_id})
            w.delete()
        merged += 1
    return Response({"merged": merged})


def _repoint(src: Player, dst: Player):
    for mp in MatchPlayer.objects.filter(player=src):
        if MatchPlayer.objects.filter(match=mp.match, side=mp.side, player=dst).exists():
            mp.delete()
        else:
            mp.player = dst
            mp.save()


def page(request):
    return render(request, "reconcile.html")
