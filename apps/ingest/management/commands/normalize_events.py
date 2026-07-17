"""`manage.py normalize_events` — re-canonicalize event codes on existing rows.

Applies normalize.canonical_event to every Match (and Draw) already in the DB,
folding spelling/language variants into MS/WS/MD/WD/XD, keeping masters/youth as
distinct suffixed buckets, and flagging exhibitions as rating-excluded. Fast:
one bulk UPDATE per distinct raw value. Run `rate` afterwards.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ingest.models import Draw, Match
from apps.ingest.normalize import canonical_event


class Command(BaseCommand):
    help = "Fold Match/Draw event codes to canonical disciplines in place."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing.",
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        m_changed = self._remap_matches(dry)
        d_changed = self._remap_draws(dry)
        verb = "would update" if dry else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {m_changed} matches and {d_changed} draws."
            )
        )
        if not dry:
            self.stdout.write("Run `manage.py rate` to recompute with folded events.")

    def _remap_matches(self, dry: bool) -> int:
        changed = 0
        for raw in Match.objects.values_list("event", flat=True).distinct():
            code, exhibition = canonical_event(raw)
            if code == raw and not exhibition:
                continue
            qs = Match.objects.filter(event=raw)
            n = qs.count()
            self.stdout.write(
                f"  {raw!r:<34} -> {code!r}"
                + ("  [exhibition -> excluded]" if exhibition else "")
                + f"  ({n})"
            )
            if not dry:
                if exhibition:
                    qs.update(event=code, rating_excluded=True)
                else:
                    qs.update(event=code)
            changed += n
        return changed

    def _remap_draws(self, dry: bool) -> int:
        changed = 0
        for raw in Draw.objects.values_list("event", flat=True).distinct():
            code, _ = canonical_event(raw)
            if code == raw:
                continue
            qs = Draw.objects.filter(event=raw)
            changed += qs.count()
            if not dry:
                qs.update(event=code)
        return changed
