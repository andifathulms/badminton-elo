"""A one-click data refresh: collect the latest season, re-rate, rebuild.

Runs the same pipeline as scripts/refresh_ratings.sh — sync_calendar (cache-first,
so it only hits the network for genuinely new days) → dedup → normalize → fix cup
events → rate --rebuild → build_* — but in a background thread so the request
returns immediately. Progress is polled from GET /api/refresh/status.

Consistency: everything after collection (normalize → rate → every build_*)
runs in ONE transaction. Readers (WAL) keep seeing the complete old data until
it commits, then the complete new data — never a half-built mix, e.g. new
ratings with last run's analytics. The DataVersion bumps inside it become
visible at the same moment, so caches flip exactly once.

Run state lives in the RefreshJob row (written outside that transaction), so
every gunicorn worker can answer "is a refresh running / how did it end".
Step-by-step progress is in memory of the worker running the job; other
workers report it as running without the step detail.

Gated behind settings.ALLOW_DATA_REFRESH (defaults to DEBUG) so it can't be
triggered on a locked-down deployment.
"""
from __future__ import annotations

import io
import threading
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.db.models import Max
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.ingest.models import RefreshJob, Tournament

# A job still "running" after this long died with its process; allow a new one.
STALE_AFTER = timedelta(hours=3)

_lock = threading.Lock()
_progress = {"phase": None, "steps_done": 0}  # this worker's running job only


def _allowed() -> bool:
    return bool(getattr(settings, "ALLOW_DATA_REFRESH", settings.DEBUG))


def _target_year() -> int:
    latest = Tournament.objects.aggregate(m=Max("start_date"))["m"]
    return latest.year if latest else timezone.now().year


# (label, callable) — mirrors scripts/refresh_ratings.sh.
# mode="full": collect the latest season, then re-rate + rebuild analytics.
# mode="rebuild": skip collection — just re-rate the data already in the DB
# (e.g. after manual Studio edits) and rebuild the derived analytics.
def _steps(year, mode="full"):
    """([collection steps], [steps that run in one transaction])."""
    def cmd(name, **kw):
        return lambda: call_command(name, stdout=io.StringIO(), stderr=io.StringIO(), **kw)

    builds = ("build_movement", "build_pairs", "build_analytics", "build_cup_history", "build_records",
              "build_calibration", "build_clutch", "build_nation_power",
              "build_consistency", "build_synergy", "build_ties")

    def run_builds():
        for b in builds:
            call_command(b, stdout=io.StringIO(), stderr=io.StringIO())

    collect = [
        (f"Collecting {year} tournaments", cmd("sync_calendar", year=year)),
        ("Deduplicating matches", cmd("dedup_matches", apply=True)),
    ]
    rebuild = [
        ("Normalizing events", cmd("normalize_events")),
        ("Fixing cup disciplines", cmd("fix_cup_events")),
        ("Backfilling countries", cmd("backfill_cup_country")),
        ("Recomputing ratings", cmd("rate", rebuild=True)),
        ("Building analytics", run_builds),
    ]
    return (collect if mode == "full" else []), rebuild


@contextmanager
def _one_transaction():
    """Run the block as ONE database transaction, committed at the end.

    Autocommit is switched off instead of wrapping in atomic(): each command's
    own atomic() blocks then join this transaction as plain blocks (Django
    treats them as outermost with nothing to commit) rather than nesting as
    SAVEPOINTs — which on SQLite keep a copy of every page the rebuild rewrites
    and made the pipeline ~3x slower.
    """
    connection.set_autocommit(False)
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.set_autocommit(True)


def _set_progress(label, done):
    with _lock:
        _progress.update(phase=label, steps_done=done)


def _finish(ok, message):
    RefreshJob.objects.filter(pk=1).update(
        running=False, ok=ok, message=message[:300], finished_at=timezone.now()
    )
    with _lock:
        _progress.update(phase=None)


def _run(year, mode="full"):
    collect, rebuild = _steps(year, mode)
    done = 0
    try:
        for label, fn in collect:
            _set_progress(label, done)
            fn()
            done += 1
        with _one_transaction():
            for label, fn in rebuild:
                _set_progress(label, done)
                fn()
                done += 1
        _set_progress(None, done)
        _finish(True, "Data updated. Reload to see the latest.")
    except Exception as e:  # noqa: BLE001 - surface any pipeline failure to the UI
        _finish(False, f"{type(e).__name__}: {e}")
    finally:
        close_old_connections()


def _snapshot():
    job = RefreshJob.objects.filter(pk=1).first()
    with _lock:
        progress = dict(_progress)
    if job is None:
        return {"running": False, "phase": None, "steps_done": 0, "steps_total": 0,
                "started_at": None, "finished_at": None, "ok": None, "message": None,
                "allowed": _allowed()}
    return {
        "running": job.running,
        "phase": progress["phase"] if job.running else None,
        "steps_done": progress["steps_done"] if job.running else job.steps_total,
        "steps_total": job.steps_total,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "ok": job.ok,
        "message": job.message or None,
        "allowed": _allowed(),
    }


def begin(mode="full"):
    """Kick off a background job in `mode` if one isn't already running.

    Returns (started, snapshot). Shared by the public refresh and the Studio
    rebuild so there is only ever one pipeline in flight — across every web
    process, because the claim is an atomic UPDATE on the RefreshJob row.
    """
    now = timezone.now()
    year = _target_year()
    collect, rebuild = _steps(year, mode)
    RefreshJob.objects.get_or_create(pk=1)
    claimed = RefreshJob.objects.filter(pk=1).exclude(
        running=True, started_at__gt=now - STALE_AFTER
    ).update(
        running=True, mode=mode, steps_total=len(collect) + len(rebuild),
        started_at=now, finished_at=None, ok=None, message="",
    )
    if not claimed:
        return False, _snapshot()
    _set_progress("Starting…", 0)
    threading.Thread(target=_run, args=(year, mode), daemon=True).start()
    return True, _snapshot()


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def start(request):
    """POST /api/refresh — kick off a background data refresh (if not running).
    Staff-only: it now lives in the Studio's Data tab, not the public header."""
    if not _allowed():
        return Response({"allowed": False, "detail": "Data refresh is disabled."}, status=403)
    started, snap = begin("full")
    return Response({"started": started, **snap})


@api_view(["GET"])
def status(request):
    """GET /api/refresh/status — current job state (for polling)."""
    return Response(_snapshot())
