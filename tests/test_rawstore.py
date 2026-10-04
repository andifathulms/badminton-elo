"""Raw response bodies live on disk; RawCache rows are the index."""
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ingest.api.client import BwfClient, Response
from apps.ingest.models import RawCache
from apps.ingest.rawstore import raw_path, read_body


@pytest.fixture(autouse=True)
def raw_dir(tmp_path, settings):
    settings.RAW_CACHE_DIR = tmp_path / "raw"
    return settings.RAW_CACHE_DIR


URL = "https://extranet-lv.bwfbadminton.com/api/vue-tournament-detail?tmt=1"


@pytest.mark.django_db
def test_write_cache_stores_body_on_disk_not_in_db():
    with BwfClient() as c:
        c._write_cache(Response(url=URL, status=200, body='{"a": 1}', from_cache=False))
    row = RawCache.objects.get(pk=URL)
    assert row.body == ""
    assert read_body(URL) == '{"a": 1}'
    with BwfClient() as c:
        hit = c._read_cache(URL)
    assert hit.from_cache and hit.json() == {"a": 1}


@pytest.mark.django_db
def test_missing_file_is_a_cache_miss_and_drops_the_row():
    RawCache.objects.create(url=URL, fetched_utc=timezone.now(), status=200, body="")
    with BwfClient() as c:
        assert c._read_cache(URL) is None
    assert not RawCache.objects.filter(pk=URL).exists()


@pytest.mark.django_db
def test_legacy_inline_row_still_served_and_offloadable():
    RawCache.objects.create(url=URL, fetched_utc=timezone.now(), status=200, body='{"b": 2}')
    with BwfClient() as c:
        assert c._read_cache(URL).json() == {"b": 2}
    call_command("offload_raw_cache", verbosity=0)
    assert RawCache.objects.get(pk=URL).body == ""
    assert raw_path(URL).read_text() == '{"b": 2}'
