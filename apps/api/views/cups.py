"""National team power for the Thomas/Uber/Sudirman Cups, now and over time."""
from __future__ import annotations

from collections import defaultdict

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingest.models import Partnership, PlayerRating

from ..serializers import PlayerBriefSerializer
from .common import active_cutoff

# (event, kind, slots) per cup — the disciplines a national team fields.
CUP_SPECS = {
    "thomas": [("MS", "single", 3), ("MD", "pair", 2)],   # men's team
    "uber": [("WS", "single", 3), ("WD", "pair", 2)],      # women's team
    "sudirman": [                                          # mixed team
        ("MS", "single", 1), ("WS", "single", 1),
        ("MD", "pair", 1), ("WD", "pair", 1), ("XD", "pair", 1),
    ],
}


class CupView(APIView):
    """GET /api/cups/{thomas|uber|sudirman} — national team power.

    A country's power is the sum of its strongest ACTIVE players/pairs for the
    disciplines that cup contests (Thomas = 3 MS + 2 MD, Uber = 3 WS + 2 WD,
    Sudirman = 1 of each of MS/WS/MD/WD/XD). Retired players (idle > 1 year) are
    excluded, so the table reflects who could field a team right now. Only
    countries able to fill every slot are ranked.
    """

    def get(self, request, cup):
        spec = CUP_SPECS.get(cup)
        if not spec:
            raise ValidationError({"cup": f"one of {', '.join(CUP_SPECS)}"})
        cutoff = active_cutoff()

        # country -> {slot_key: [(rating_value, contributor_dict), ...]}
        by_country: dict = defaultdict(dict)
        for event, kind, slots in spec:
            per: dict = defaultdict(list)
            if kind == "single":
                for r in PlayerRating.objects.filter(
                    event=event, last_match_utc__gte=cutoff
                ).select_related("player"):
                    cc = r.player.country_code
                    if cc:
                        per[cc].append(
                            (r.mu, {
                                "event": event, "rating": round(r.mu),
                                "players": [PlayerBriefSerializer(r.player).data],
                            })
                        )
            else:
                for p in Partnership.objects.filter(
                    event=event, last_match_utc__gte=cutoff
                ).select_related("player1", "player2"):
                    cc = p.player1.country_code
                    if cc and cc == p.player2.country_code:
                        per[cc].append(
                            (p.combined_mu, {
                                "event": event, "rating": round(p.combined_mu),
                                "players": PlayerBriefSerializer(
                                    [p.player1, p.player2], many=True
                                ).data,
                            })
                        )
            key = f"{event}:{kind}"
            for cc, items in per.items():
                items.sort(key=lambda it: it[0], reverse=True)
                by_country[cc][key] = items[:slots]

        rows = []
        for cc, slotmap in by_country.items():
            if any(
                len(slotmap.get(f"{e}:{k}", [])) < n for e, k, n in spec
            ):
                continue  # can't field a full team
            contributors, power = [], 0.0
            for e, k, n in spec:
                for value, c in slotmap[f"{e}:{k}"]:
                    power += value
                    contributors.append(c)
            rows.append(
                {"country": cc, "power": round(power), "contributors": contributors}
            )
        rows.sort(key=lambda r: r["power"], reverse=True)
        return Response({"cup": cup, "results": rows})


class CupHistoryView(APIView):
    """GET /api/cups/{cup}/history — each top country's team power per year, so
    the Cups timeline shows dominance eras."""

    def get(self, request, cup):
        from apps.ingest.models import CupPowerHistory

        if cup not in CUP_SPECS:
            raise ValidationError({"cup": f"one of {', '.join(CUP_SPECS)}"})
        rows = list(
            CupPowerHistory.objects.filter(cup=cup).values("country", "year", "power")
        )
        if not rows:
            return Response({"cup": cup, "years": [], "series": []})
        years = sorted({r["year"] for r in rows})
        by_country: dict = defaultdict(dict)
        peak: dict = defaultdict(float)
        for r in rows:
            by_country[r["country"]][r["year"]] = r["power"]
            peak[r["country"]] = max(peak[r["country"]], r["power"])
        top = sorted(peak, key=peak.get, reverse=True)[:8]
        series = [
            {
                "country": cc,
                "points": [
                    {"year": y, "power": by_country[cc].get(y)} for y in years
                ],
            }
            for cc in top
        ]
        return Response({"cup": cup, "years": years, "series": series})
