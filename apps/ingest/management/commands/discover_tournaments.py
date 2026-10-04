"""`manage.py discover_tournaments` — find BWF tournaments the calendar hides.

The season calendar (vue-grouped-year-tournaments) omits some events that
the API does serve — the 2026 Asian Games (tmtIds 5874 individual / 5876
team) were never listed, so sync_calendar never collected them. Tournament
ids are allocated sequentially, so this probes the ids around the highest
known one that aren't in the DB, registers the senior events it finds, and
collects any that have finished but hold no matches.

Ids at or below the highest known id are answered from the cache (they
don't change); ids above it are always asked live, since those are new.

    python manage.py discover_tournaments [--below 600] [--above 100]
"""
from __future__ import annotations

import io
import re
import time
from datetime import date, timedelta

from django.core.management import call_command
from django.db.models import Max

from apps.ingest.api import endpoints
from apps.ingest.api.client import BwfClient
from apps.ingest.management.base import DataCommand
from apps.ingest.models import Tournament

SKIP = re.compile(
    r"junior|youth|\bu ?1\d\b|para|unsanctioned|airbadminton|\btest\b|unknown|"
    r"club|gymnasiade|nomination", re.I)
TEAM = re.compile(r"team|thomas|uber|sudirman|m&f cup", re.I)
BWF_ID_MAX = 100_000  # real tmtIds are small (~6k in 2026); synthetic ids are CRC32-sized


def _date(v):
    return date.fromisoformat(str(v)[:10]) if v else None


class Command(DataCommand):
    help = "Probe unlisted BWF tournament ids; register and collect senior events."

    def add_arguments(self, parser):
        parser.add_argument("--below", type=int, default=600,
                            help="probe this many ids below the highest known")
        parser.add_argument("--above", type=int, default=100,
                            help="probe this many ids above the highest known")
        parser.add_argument("--no-collect", action="store_true")

    def handle(self, *args, **opts):
        top = (Tournament.objects.filter(tournament_id__lt=BWF_ID_MAX)
               .aggregate(m=Max("tournament_id"))["m"]) or 0
        known = set(Tournament.objects.filter(
            tournament_id__gte=top - opts["below"]).values_list("tournament_id", flat=True))
        ids = [i for i in range(max(1, top - opts["below"]), top + opts["above"] + 1)
               if i not in known]
        self.stdout.write(f"probing {len(ids)} unknown ids around {top}")
        found = []
        with BwfClient() as cached, BwfClient(use_cache=False) as live:
            for n, tid in enumerate(ids):
                client = cached if tid <= top else live
                try:
                    res = (client.get_json(endpoints.vue_tournament_detail(tid)) or {}).get("results")
                except Exception:  # noqa: BLE001 - one bad id must not stop the sweep
                    continue
                if not isinstance(res, dict) or not res.get("name"):
                    continue
                cat = (res.get("categoryModel") or {}).get("name") or ""
                if SKIP.search(f"{res['name']} {cat}"):
                    continue
                start = _date(res.get("start_date"))
                if not start or start > date.today() + timedelta(days=7):
                    continue  # future events: the season calendar will list them
                t, created = Tournament.objects.update_or_create(
                    tournament_id=tid,
                    defaults={"name": res["name"], "code": res.get("code") or None,
                              "category_name": cat, "start_date": _date(res.get("start_date")),
                              "end_date": _date(res.get("end_date"))},
                )
                if created:
                    found.append(t)
                    self.stdout.write(f"  + [{tid}] {t.name} ({cat}, {t.start_date})")
                if client is live and n % 30 == 29:
                    time.sleep(15)  # the fan API 500s under sustained volume
        self.stdout.write(f"registered {len(found)} new tournaments")
        if opts["no_collect"]:
            return
        today = date.today()
        for t in Tournament.objects.filter(tournament_id__lt=BWF_ID_MAX, match_count=0,
                                           end_date__lt=today,
                                           tournament_id__gte=top - opts["below"]):
            if SKIP.search(f"{t.name} {t.category_name}") or "cancel" in t.name.lower():
                continue
            cmd, args = (("scrape_bwf_team", [str(t.tournament_id), "--auto"])
                         if TEAM.search(t.name) else
                         ("scrape", ["--id", str(t.tournament_id), "--include-qualifying"]))
            out = io.StringIO()
            try:
                call_command(cmd, *args, stdout=out, stderr=out)
            except Exception as e:  # noqa: BLE001
                out.write(f"error: {e}")
            self.stdout.write(f"  collected [{t.tournament_id}] {t.name[:50]}: "
                              f"{out.getvalue().strip().splitlines()[-1:] or ''}")
