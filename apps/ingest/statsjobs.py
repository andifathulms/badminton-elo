"""Background fetching of per-match rally statistics.

The statistics endpoint used to call BWF inside the web request: a cache miss
blocked a worker on a rate-limited (1 QPS) call with a 20 s timeout and 3
retries. Now a miss only queues a StatsFetchJob and returns "pending"; a worker
thread drains the queue through the polite client, and the page polls.

Claiming is an atomic UPDATE (pending -> running), so several web processes
(or `manage.py run_stats_jobs`) can drain the same queue without fetching a
match twice.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from django.db import OperationalError, close_old_connections
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
RETRY_FAILED_AFTER = timedelta(hours=12)
STALE_RUNNING_AFTER = timedelta(minutes=5)  # a worker died mid-fetch

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue(match) -> str:
    """Queue a fetch for `match` (idempotent). Returns the job's status."""
    from .models import StatsFetchJob

    job, created = StatsFetchJob.objects.get_or_create(
        match=match, defaults={"status": PENDING, "updated_utc": timezone.now()}
    )
    if not created and job.status == FAILED and (
        timezone.now() - job.updated_utc > RETRY_FAILED_AFTER
    ):
        StatsFetchJob.objects.filter(pk=job.pk, status=FAILED).update(
            status=PENDING, updated_utc=timezone.now()
        )
        job.status = PENDING
    if not created and job.status == RUNNING and (
        timezone.now() - job.updated_utc > STALE_RUNNING_AFTER
    ):
        StatsFetchJob.objects.filter(pk=job.pk, status=RUNNING).update(
            status=PENDING, updated_utc=timezone.now()
        )
        job.status = PENDING
    return job.status


def _claim_next():
    from .models import StatsFetchJob

    for job_id in (
        StatsFetchJob.objects.filter(status=PENDING)
        .order_by("updated_utc")
        .values_list("pk", flat=True)[:5]
    ):
        claimed = StatsFetchJob.objects.filter(pk=job_id, status=PENDING).update(
            status=RUNNING, updated_utc=timezone.now(), attempts=F("attempts") + 1
        )
        if claimed:
            return StatsFetchJob.objects.select_related("match").get(pk=job_id)
    return None


def drain(max_jobs: int | None = None) -> int:
    """Fetch queued matches until the queue is empty (or max_jobs). Returns
    how many jobs ran. Safe to call from several processes at once."""
    from .api.client import BwfClient
    from .h2h import fetch_and_store_stats
    from .models import StatsFetchJob

    ran = 0
    with BwfClient() as client:
        while max_jobs is None or ran < max_jobs:
            job = _claim_next()
            if job is None:
                break
            ran += 1
            try:
                stats = fetch_and_store_stats(job.match, client=client)
                status = DONE if stats is not None else FAILED
            except OperationalError:
                # The database is busy (e.g. a refresh holds the write lock):
                # not this match's fault — put it back and stop for now.
                logger.warning("database busy; requeueing stats job %s", job.match_id)
                StatsFetchJob.objects.filter(pk=job.pk).update(
                    status=PENDING, updated_utc=timezone.now()
                )
                break
            except Exception:  # noqa: BLE001 - a bad match must not stop the queue
                logger.exception("stats fetch failed for match %s", job.match_id)
                status = FAILED
            StatsFetchJob.objects.filter(pk=job.pk).update(
                status=status, updated_utc=timezone.now()
            )
    return ran


def _run_worker():
    try:
        drain()
    finally:
        close_old_connections()


def kick() -> None:
    """Start this process's worker thread if it isn't already running."""
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run_worker, name="stats-fetch", daemon=True)
        _worker.start()
