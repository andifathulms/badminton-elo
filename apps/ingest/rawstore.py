"""On-disk store for raw API response bodies (domain rule 9).

Bodies used to live in the RawCache table, which grew to 3 GB of a 4 GB
SQLite file and spread the rows the site actually serves across far more
pages. The table now keeps only the index (url, status, fetched_utc); the
body lives at data/raw/<stem>.<sha1[:16]>.json — the same file name the
client has always mirrored to, so existing mirrors already serve as the store.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings


def raw_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode()).hexdigest()[:16]
    stem = (urlparse(url).path.rsplit("/", 1)[-1] or "root")[:60]
    return Path(settings.RAW_CACHE_DIR) / f"{stem}.{digest}.json"


def read_body(url: str) -> str | None:
    """The stored body for `url`, or None if there is no file."""
    try:
        return raw_path(url).read_text()
    except FileNotFoundError:
        return None


def write_body(url: str, body: str) -> Path:
    """Atomically write `body` for `url` (temp file + rename)."""
    path = raw_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
