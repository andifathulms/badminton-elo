"""Base class for management commands that change served data."""
from __future__ import annotations

from django.core.management.base import BaseCommand


class DataCommand(BaseCommand):
    """A command whose writes are visible through the API.

    After `handle()` returns successfully the DataVersion is bumped, which
    invalidates every cached API response at once (apps.api.cache). A command
    that raises leaves the version alone.
    """

    def execute(self, *args, **options):
        output = super().execute(*args, **options)
        from apps.ingest.dataversion import bump

        bump()
        return output
