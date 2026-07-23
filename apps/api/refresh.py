"""A one-click data refresh: collect the latest season, re-rate, rebuild.

Runs the same pipeline as scripts/refresh_ratings.sh — sync_calendar (cache-first,
so it only hits the network for genuinely new days) → dedup → normalize → fix cup
events → rate --rebuild → build_* — but in a background thread so the request
returns immediately. Progress is polled from GET /api/refresh/status.

Gated behind settings.ALLOW_DATA_REFRESH (defaults to DEBUG) so it can't be
triggered on a locked-down deployment. Single-process only: the job state lives
in memory, so under multiple gunicorn workers a poll may hit a different worker
(fine for the local single-process demo this is built for).
"""
from __future__ import annotations

import io
import threading

from django.conf import settings
from django.core.management import call_command
from django.db.models import Max
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.ingest.models import Tournament

_lock = threading.Lock()
_job = {
    "running": False, "phase": None, "steps_done": 0, "steps_total": 0,
    "started_at": None, "finished_at": None, "ok": None, "message": None,
}


def _allowed() -> bool:
    return bool(getattr(settings, "ALLOW_DATA_REFRESH", settings.DEBUG))


def _target_year() -> int:
    latest = Tournament.objects.aggregate(m=Max("start_date"))["m"]
    return latest.year if latest else timezone.now().year


# (label, callable) — mirrors scripts/refresh_ratings.sh.
def _steps(year):
    def cmd(name, **kw):
        return lambda: call_command(name, stdout=io.StringIO(), stderr=io.StringIO(), **kw)

    builds = ("build_pairs", "build_analytics", "build_cup_history", "build_records",
              "build_calibration", "build_clutch", "build_nation_power",
              "build_consistency", "build_synergy")

    def run_builds():
        for b in builds:
            call_command(b, stdout=io.StringIO(), stderr=io.StringIO())

    return [
        (f"Collecting {year} tournaments", cmd("sync_calendar", year=year)),
        ("Deduplicating matches", cmd("dedup_matches", apply=True)),
        ("Normalizing events", cmd("normalize_events")),
        ("Fixing cup disciplines", cmd("fix_cup_events")),
        ("Backfilling countries", cmd("backfill_cup_country")),
        ("Recomputing ratings", cmd("rate", rebuild=True)),
        ("Building analytics", run_builds),
    ]


def _run(year):
    steps = _steps(year)
    with _lock:
        _job["steps_total"] = len(steps)
    try:
        for i, (label, fn) in enumerate(steps):
            with _lock:
                _job["phase"] = label
                _job["steps_done"] = i
            fn()
        with _lock:
            _job["ok"] = True
            _job["message"] = "Data updated. Reload to see the latest."
            _job["steps_done"] = len(steps)
    except Exception as e:  # noqa: BLE001 - surface any pipeline failure to the UI
        with _lock:
            _job["ok"] = False
            _job["message"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        with _lock:
            _job["running"] = False
            _job["phase"] = None
            _job["finished_at"] = timezone.now()


def _snapshot():
    with _lock:
        return {**_job, "allowed": _allowed()}


@api_view(["POST"])
def start(request):
    """POST /api/refresh — kick off a background data refresh (if not running)."""
    if not _allowed():
        return Response({"allowed": False, "detail": "Data refresh is disabled."}, status=403)
    with _lock:
        if _job["running"]:
            return Response({"started": False, **_job, "allowed": True})
        _job.update(running=True, phase="Starting…", steps_done=0, steps_total=0,
                    started_at=timezone.now(), finished_at=None, ok=None, message=None)
    year = _target_year()
    threading.Thread(target=_run, args=(year,), daemon=True).start()
    return Response({"started": True, **_snapshot()})


@api_view(["GET"])
def status(request):
    """GET /api/refresh/status — current job state (for polling)."""
    return Response(_snapshot())
