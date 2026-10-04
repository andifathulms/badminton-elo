"""Insights boards: tournament gains/performances/upsets, calibration,
clutch, synergy, consistency, dynasties and aging."""
from __future__ import annotations

from collections import defaultdict

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import (
    Match,
    Partnership,
    PlayerRating,
    RatingHistory,
    TournamentPerformance,
)

from ..serializers import (
    PlayerBriefSerializer,
    TournamentBriefSerializer,
    TournamentPerformanceSerializer,
)
from .common import DOUBLES, EVENTS, _team_rating

ANALYTICS_MAX_ROWS = 100  # a board's depth; pages are served from within it


class AnalyticsView(APIView):
    """GET /api/analytics/{tournament-gains|upsets|performances}
    [?event=&min_matches=&limit=&offset=] — one page of the top 100 (`count`).

    tournament-gains: biggest net ELO gained across a single tournament.
    upsets: biggest single-match ELO gains (the standout wins).
    Doubles rows are collapsed into one pair (both partners) instead of two.
    """

    def get(self, request, kind):
        event = request.query_params.get("event")
        try:
            min_matches = int(request.query_params.get("min_matches", 2))
        except ValueError:
            min_matches = 2
        try:
            limit = min(int(request.query_params.get("limit", 40)), ANALYTICS_MAX_ROWS)
        except ValueError:
            limit = 40
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            offset = 0

        # Upsets are ranked per MATCH (every standout single win), not per
        # tournament-performance — a pair can appear twice in one tournament.
        if kind == "upsets":
            return self._match_upsets(request, event, limit, offset)

        qs = TournamentPerformance.objects.select_related(
            "player", "partner", "tournament"
        ).filter(matches__gte=min_matches)
        if event in EVENTS:
            qs = qs.filter(event=event)
        if request.query_params.get("include_new") != "1":
            qs = qs.filter(rd_start__lte=130)
        if kind == "performances":
            qs = qs.exclude(perf_rating=None).order_by("-perf_rating")
        else:
            qs = qs.order_by("-net_delta")

        # Collapse the two members of a doubles pair into one row. partner_id can
        # be missing on some performances, so also collapse by the shared match:
        # two winners of the same match are the same pair.
        seen: set = set()
        picked: list = []
        for tp in qs[:2000]:
            if len(picked) >= ANALYTICS_MAX_ROWS:
                break
            if tp.event in DOUBLES:
                keys = []
                if tp.partner_id:
                    keys.append(
                        (tp.tournament_id, tp.event,
                         frozenset((tp.player_id, tp.partner_id)))
                    )
                if tp.best_match_id:
                    keys.append(("match", tp.best_match_id))
                if any(k in seen for k in keys):
                    continue
                seen.update(keys)
            picked.append(tp)

        # Board = the top ANALYTICS_MAX_ROWS collapsed rows; serve one page of it.
        count = len(picked)
        picked = picked[offset:offset + limit]

        # Show mixed pairs male-first, female-second (the collapsed row's `player`
        # is just whoever performed better that week, so order isn't stable).
        for tp in picked:
            if (tp.event == "XD" and tp.partner_id
                    and tp.player.gender == "F" and tp.partner.gender == "M"):
                # Assigning the related objects also swaps player_id/partner_id via
                # the FK descriptor — don't swap the ids again or they desync.
                tp.player, tp.partner = tp.partner, tp.player

        rows = TournamentPerformanceSerializer(picked, many=True).data
        return Response({"results": rows, "count": count})

    def _match_upsets(self, request, event, limit, offset=0):
        """Biggest single-match upsets: rank individual wins by ELO gained.
        A positive delta means the player won and gained, so the winning side
        is exactly the players with a positive delta. Collapsed to one row per
        match (both partners for doubles)."""
        include_new = request.query_params.get("include_new") == "1"
        # delta >= 30 keeps the sort cheap; any upset that makes a list is well
        # above it. Highest first, so the first row seen per match is its top
        # winner (and carries the pair).
        rh = RatingHistory.objects.filter(delta__gte=30)
        if event in EVENTS:
            rh = rh.filter(event=event)
        if not include_new:
            rh = rh.filter(rd_before__lte=130)
        rh = rh.order_by("-delta").values(
            "match_id", "player_id", "delta"
        )
        seen: set = set()
        picks: list = []
        for r in rh[:5000]:
            if r["match_id"] in seen:
                continue
            seen.add(r["match_id"])
            picks.append(r)
            if len(picks) >= ANALYTICS_MAX_ROWS:
                break
        count = len(picks)
        picks = picks[offset:offset + limit]

        ids = [p["match_id"] for p in picks]
        matches = {
            m.match_id: m
            for m in Match.objects.filter(match_id__in=ids)
            .select_related("tournament")
            .prefetch_related("lineup__player", "games")
        }
        pre = {
            (mid, pid): (mu, rd)
            for mid, pid, mu, rd in RatingHistory.objects.filter(
                match_id__in=ids
            ).values_list("match_id", "player_id", "mu_before", "rd_before")
        }

        out = []
        for p in picks:
            m = matches.get(p["match_id"])
            if not m:
                continue
            lineup = list(m.lineup.all())
            side = next(
                (l.side for l in lineup if l.player_id == p["player_id"]), None
            )
            winners = [l.player for l in lineup if l.side == side]
            opp = [l.player for l in lineup if l.side != side]
            player = next(
                (pl for pl in winners if pl.player_id == p["player_id"]), winners[0]
            )
            partner = next(
                (pl for pl in winners if pl.player_id != p["player_id"]), None
            )
            games = [
                (g.side1_points, g.side2_points)
                for g in sorted(m.games.all(), key=lambda g: g.game_no)
            ]
            if side == 2:
                games = [(b, a) for a, b in games]
            out.append({
                "player": PlayerBriefSerializer(player).data,
                "partner": PlayerBriefSerializer(partner).data if partner else None,
                "event": m.event,
                "tournament": TournamentBriefSerializer(m.tournament).data,
                "best_delta": round(p["delta"], 1),
                "best_match": m.match_id,
                "best_round": m.round_name,
                "beat": PlayerBriefSerializer(opp, many=True).data,
                "best_score": games,
                "best_score_status": m.score_status,
                "winner_rating_before": _team_rating(
                    [pre.get((m.match_id, l.player_id)) or (None, None)
                     for l in lineup if l.side == side]
                ),
                "opponent_rating_before": _team_rating(
                    [pre.get((m.match_id, l.player_id)) or (None, None)
                     for l in lineup if l.side != side]
                ),
            })
        return Response({"results": out, "count": count})


class CalibrationView(APIView):
    """GET /api/analytics/calibration?event= — rating reliability.

    Returns the predicted-vs-actual win rate per probability bucket (a
    reliability diagram) plus the headline accuracy: how often the higher-rated
    side actually wins. event defaults to ALL (every discipline pooled).
    """

    def get(self, request):
        from apps.ingest.models import CalibrationBin

        event = request.query_params.get("event") or "ALL"
        if event not in EVENTS and event != "ALL":
            raise ValidationError({"event": f"one of ALL, {', '.join(EVENTS)}"})
        rows = list(CalibrationBin.objects.filter(event=event).order_by("bucket"))
        bins = [
            {
                "bucket": r.bucket,
                "lo": round(r.bucket / 10, 2),
                "hi": round((r.bucket + 1) / 10, 2),
                "n": r.n,
                "predicted": round(r.prob_sum / r.n, 4) if r.n else None,
                "actual": round(r.correct / r.n, 4) if r.n else None,
            }
            for r in rows
        ]
        n = sum(r.n for r in rows)
        correct = sum(r.correct for r in rows)
        # Mean calibration error: |predicted − actual| weighted by bucket size.
        ece = (
            sum(abs(b["predicted"] - b["actual"]) * b["n"] for b in bins if b["n"])
            / n
            if n else None
        )
        return Response({
            "event": event,
            "n": n,
            "accuracy": round(correct / n, 4) if n else None,
            "calibration_error": round(ece, 4) if ece is not None else None,
            "bins": bins,
        })


class ClutchView(APIView):
    """GET /api/analytics/clutch?event=[&min=&limit=&order=] — deciding-game
    leaderboard: who wins the matches that go the distance to a third game.

    Ranked by third-game win rate among players with at least `min` deciding
    games (default 15), so a small sample can't top the board. order=played
    ranks by sheer volume of deciders instead.
    """

    def get(self, request):
        from apps.ingest.models import ClutchStat

        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})
        try:
            min_dec = int(request.query_params.get("min", 15))
        except ValueError:
            min_dec = 15
        try:
            limit = min(int(request.query_params.get("limit", 40)), 100)
        except ValueError:
            limit = 40

        qs = (
            ClutchStat.objects.filter(event=event, deciders_played__gte=min_dec)
            .select_related("player")
        )
        rows = [
            {
                "player": PlayerBriefSerializer(c.player).data,
                "deciders_played": c.deciders_played,
                "deciders_won": c.deciders_won,
                "decider_pct": round(100.0 * c.deciders_won / c.deciders_played, 1),
                "matches": c.matches,
                "overall_pct": round(100.0 * c.wins / c.matches, 1) if c.matches else None,
            }
            for c in qs
        ]
        if request.query_params.get("order") == "played":
            rows.sort(key=lambda r: (r["deciders_played"], r["decider_pct"]), reverse=True)
        else:
            rows.sort(key=lambda r: (r["decider_pct"], r["deciders_played"]), reverse=True)
        return Response({"event": event, "min": min_dec, "results": rows[:limit]})


class SynergyView(APIView):
    """GET /api/analytics/synergy?event=[&min=&order=&limit=] — partnership
    chemistry. Ranks pairs by synergy = performance rating − combined member
    rating: order=best (default) surfaces duos that overperform the sum of their
    parts, order=worst the underperformers. `min` is the minimum matches together
    (default 20). event is one of MD/WD/XD.
    """

    def get(self, request):
        event = request.query_params.get("event")
        if event not in DOUBLES:
            raise ValidationError({"event": f"required; one of {', '.join(DOUBLES)}"})
        try:
            min_matches = int(request.query_params.get("min", 20))
        except ValueError:
            min_matches = 20
        try:
            limit = min(int(request.query_params.get("limit", 40)), 100)
        except ValueError:
            limit = 40

        qs = (
            Partnership.objects.filter(
                event=event, matches_together__gte=min_matches, synergy__isnull=False
            )
            .select_related("player1", "player2")
        )
        desc = request.query_params.get("order") != "worst"
        qs = qs.order_by("-synergy" if desc else "synergy")[:limit]
        rows = [
            {
                "players": PlayerBriefSerializer([p.player1, p.player2], many=True).data,
                "event": event,
                "synergy": round(p.synergy, 1),
                "perf_rating": round(p.perf_rating),
                "combined_mu": round(p.combined_mu),
                "matches_together": p.matches_together,
                "wins_together": p.wins_together,
                "win_pct": round(100.0 * p.wins_together / p.matches_together, 1)
                if p.matches_together else None,
            }
            for p in qs
        ]
        return Response({"event": event, "order": "best" if desc else "worst",
                         "min": min_matches, "results": rows})


class ConsistencyView(APIView):
    """GET /api/analytics/consistency?event=[&min=&order=&limit=] — form
    volatility leaderboard. order=steady (default) ranks the lowest per-match
    rating-swing (most predictable), order=volatile the highest (giant-killers
    and upset-prone). Restricted to players with at least `min` matches (default
    40) so a short sample can't top either end.
    """

    def get(self, request):
        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})
        try:
            min_matches = int(request.query_params.get("min", 40))
        except ValueError:
            min_matches = 40
        try:
            limit = min(int(request.query_params.get("limit", 40)), 100)
        except ValueError:
            limit = 40

        qs = (
            PlayerRating.objects.filter(
                event=event, matches_played__gte=min_matches, volatility__isnull=False
            )
            .select_related("player")
        )
        desc = request.query_params.get("order") == "volatile"
        qs = qs.order_by("-volatility" if desc else "volatility")[:limit]
        rows = [
            {
                "player": PlayerBriefSerializer(r.player).data,
                "volatility": round(r.volatility, 1),
                "rating": round(r.mu - 2.0 * r.rd, 1),
                "mu": round(r.mu),
                "matches_played": r.matches_played,
            }
            for r in qs
        ]
        return Response({"event": event, "order": "volatile" if desc else "steady",
                         "min": min_matches, "results": rows})


class DynastiesView(APIView):
    """GET /api/analytics/dynasties?event= — which nation ruled a discipline, and
    when. For each year the top country (by summed top-3 rating) is the #1; runs
    of the same #1 across consecutive years are 'reigns'. Returns the year-by-year
    leader, the reigns (longest first), and total years at #1 per country.
    """

    def get(self, request):
        from apps.ingest.models import NationYear

        event = request.query_params.get("event")
        if event not in EVENTS:
            raise ValidationError({"event": f"required; one of {', '.join(EVENTS)}"})

        rows = list(
            NationYear.objects.filter(event=event).order_by("year", "-power")
        )
        if not rows:
            return Response({"event": event, "timeline": [], "reigns": [], "totals": []})

        by_year: dict = defaultdict(list)
        for r in rows:
            by_year[r.year].append(r)

        timeline = []
        for year in sorted(by_year):
            ranked = sorted(by_year[year], key=lambda r: r.power, reverse=True)
            top = ranked[0]
            runner = ranked[1] if len(ranked) > 1 else None
            timeline.append({
                "year": year,
                "country": top.country,
                "power": round(top.power),
                "margin": round(top.power - runner.power) if runner else None,
                "runner_up": runner.country if runner else None,
            })

        # Reigns: consecutive runs of the same #1 country.
        reigns = []
        for t in timeline:
            if reigns and reigns[-1]["country"] == t["country"] \
                    and t["year"] == reigns[-1]["end"] + 1:
                reigns[-1]["end"] = t["year"]
                reigns[-1]["span"] += 1
            else:
                reigns.append({"country": t["country"], "start": t["year"],
                               "end": t["year"], "span": 1})
        reigns_sorted = sorted(reigns, key=lambda r: (r["span"], r["end"]), reverse=True)

        totals: dict = defaultdict(int)
        for t in timeline:
            totals[t["country"]] += 1
        totals_sorted = [
            {"country": c, "years": n}
            for c, n in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        ]

        return Response({
            "event": event,
            "timeline": timeline,
            "reigns": reigns_sorted,
            "totals": totals_sorted,
        })


class AgingView(APIView):
    """GET /api/analytics/aging?event=[&min_matches=] — when players peak.

    Uses each rated player's all-time peak (peak_mu at peak_utc) and date of
    birth to place their career peak on an age axis: the age distribution of
    peaks, the median peak age, and the average peak rating per age — so you can
    see the window a discipline's players tend to be at their best.
    event omitted pools all five main disciplines.
    """

    AGE_MIN, AGE_MAX = 14, 42

    def get(self, request):
        event = request.query_params.get("event")
        if event and event not in EVENTS:
            raise ValidationError({"event": f"one of {', '.join(EVENTS)}"})
        try:
            min_matches = int(request.query_params.get("min_matches", 20))
        except ValueError:
            min_matches = 20

        qs = (
            PlayerRating.objects.filter(matches_played__gte=min_matches)
            .exclude(peak_mu=None).exclude(peak_utc=None)
            .filter(player__dob__isnull=False)
            .select_related("player")
        )
        qs = qs.filter(event=event) if event else qs.filter(event__in=EVENTS)

        ages: list[float] = []
        by_age: dict = defaultdict(lambda: {"n": 0, "mu_sum": 0.0})
        top: list = []
        for r in qs:
            dob = r.player.dob
            peak = r.peak_utc
            age = (peak.date() - dob).days / 365.25
            if not (self.AGE_MIN <= age <= self.AGE_MAX):
                continue
            ages.append(age)
            b = by_age[int(age)]
            b["n"] += 1
            b["mu_sum"] += r.peak_mu
            top.append((r.peak_mu, age, r.player, r.event))

        if not ages:
            return Response({"event": event or "ALL", "n": 0, "bins": []})

        ages.sort()
        n = len(ages)
        median = ages[n // 2] if n % 2 else (ages[n // 2 - 1] + ages[n // 2]) / 2
        bins = [
            {"age": age, "count": b["n"], "avg_peak": round(b["mu_sum"] / b["n"], 1)}
            for age, b in sorted(by_age.items())
        ]
        top.sort(key=lambda t: t[0], reverse=True)
        peakers = [
            {
                "player": PlayerBriefSerializer(p).data,
                "event": ev,
                "peak_mu": round(mu, 1),
                "peak_age": round(age, 1),
            }
            for mu, age, p, ev in top[:10]
        ]
        return Response({
            "event": event or "ALL",
            "n": n,
            "median_peak_age": round(median, 1),
            "mean_peak_age": round(sum(ages) / n, 1),
            "bins": bins,
            "peakers": peakers,
        })
