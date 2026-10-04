"""Refresh pipeline: one job across processes; the rebuild is all-or-nothing."""
import pytest

from apps.api import refresh
from apps.ingest.models import RefreshJob, Tournament


@pytest.fixture
def no_thread(monkeypatch):
    started = []
    monkeypatch.setattr(refresh.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: started.append(args)})())
    return started


@pytest.mark.django_db
def test_only_one_refresh_can_be_claimed(no_thread):
    ok1, snap = refresh.begin("rebuild")
    ok2, _ = refresh.begin("rebuild")
    assert ok1 and not ok2
    assert snap["running"] and RefreshJob.objects.get(pk=1).running
    assert len(no_thread) == 1


@pytest.mark.django_db(transaction=True)
def test_failed_rebuild_rolls_back_every_step(monkeypatch):
    def write():
        Tournament.objects.create(tournament_id=1, name="half-built")

    def boom():
        raise RuntimeError("build failed")

    monkeypatch.setattr(refresh, "_steps", lambda year, mode: ([], [("write", write), ("boom", boom)]))
    RefreshJob.objects.create(pk=1, running=True, steps_total=2)
    refresh._run(2026, "rebuild")
    assert not Tournament.objects.exists()  # step 1 rolled back with step 2
    job = RefreshJob.objects.get(pk=1)
    assert not job.running and job.ok is False and "build failed" in job.message
