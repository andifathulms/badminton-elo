"""`manage.py normalize_events` — canonicalize event codes on existing rows.

Two passes, both leaving already-clean open/masters/youth buckets (MS, MS45,
MSU19) untouched:

  1. String pass — fold spelling/language variants via normalize.canonical_event
     (e.g. "Ladies Singles" -> WS, "MIX" -> XD), and flag exhibitions
     rating-excluded, but only when the result is a clean bucket.
  2. Lineup pass — for labels no string rule can map (foreign abbreviations like
     the French SM/DM or Dutch HE/DD), infer the discipline from the actual
     lineup (player count + gender), carrying any age/youth suffix in the label.
  3. Youth pass — plain open codes in a junior/U-age tournament get the
     tournament's youth suffix (World Junior 'MS' -> MSU19).

Run `rate` (and the build_* steps) afterwards. Fast: bulk update per raw value.
"""
from __future__ import annotations

from collections import Counter


from apps.ingest.cup_events import rubber_discipline
from apps.ingest.management.base import DataCommand
from django.db.models import Q

from apps.ingest.models import Draw, Match, Tournament
from apps.ingest.normalize import _AGE, _YOUTH, canonical_event, is_final_event

EXHIBITION_WORDS = ("exhibition", "farewell", "unified", "plate")


def _suffix(raw: str) -> str:
    """Age/youth suffix carried by a raw label, e.g. 'U19 LS' -> 'U19'."""
    y = _YOUTH.search(raw.lower())
    if y:
        return f"U{y.group(1)}"
    a = _AGE.search(raw)
    return a.group(1) if a else ""


OPEN = ("MS", "WS", "MD", "WD", "XD")


def tournament_youth(name: str) -> str:
    """The youth bucket a whole tournament belongs to, from its name: the
    oldest explicit U-age ('Jakarta Open Junior International (U17 & U15)' ->
    U17), else U19 for 'Junior'/'Youth' events; '' for open events."""
    low = (name or "").lower()
    ages = [int(a) for a in _YOUTH.findall(low)]
    if ages:
        return f"U{max(ages)}"
    if "junior" in low or "youth" in low:
        return "U19"
    return ""


class Command(DataCommand):
    help = "Fold Match/Draw event codes to canonical disciplines in place."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change without writing.")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        moves: Counter = Counter()

        # --- Pass 1: string-based folding (canonical_event) -------------------
        # .order_by() clears the model's default ordering, which otherwise breaks
        # DISTINCT (SQL adds the ORDER BY columns to the SELECT).
        m_changed = 0
        for raw in Match.objects.values_list("event", flat=True).order_by().distinct():
            if is_final_event(raw):
                continue
            code, exhibition = canonical_event(raw)
            if not is_final_event(code):
                continue  # leave for the lineup pass
            qs = Match.objects.filter(event=raw)
            n = qs.count()
            moves[f"{raw!r}->{code}{' [excl]' if exhibition else ''}"] += n
            m_changed += n
            if not dry:
                if exhibition:
                    qs.update(event=code, rating_excluded=True)
                else:
                    qs.update(event=code)

        # --- Pass 2: lineup-based inference for the rest ----------------------
        lineup_changed = 0
        for raw in Match.objects.values_list("event", flat=True).order_by().distinct():
            if is_final_event(raw):
                continue
            low = raw.lower()
            exhibition = any(w in low for w in EXHIBITION_WORDS)
            suffix = _suffix(raw)
            updates = []
            for m in (
                Match.objects.filter(event=raw).prefetch_related("lineup__player")
            ):
                s1 = [l.player for l in m.lineup.all() if l.side == 1]
                s2 = [l.player for l in m.lineup.all() if l.side == 2]
                base = rubber_discipline(s1, s2)
                if base is None:
                    continue
                m.event = f"{base}{suffix}"
                if exhibition:
                    m.rating_excluded = True
                updates.append(m)
                moves[f"{raw!r}->{base}{suffix} (lineup)"] += 1
            lineup_changed += len(updates)
            if not dry and updates:
                Match.objects.bulk_update(updates, ["event", "rating_excluded"],
                                          batch_size=1000)

        # --- Pass 3: youth tournaments --------------------------------------
        # Junior events often label disciplines plainly ('MS'), which put World
        # Junior / U17 results into the open ratings. The tournament name says
        # which youth bucket they belong to.
        youth_changed = 0
        for tid, name in Tournament.objects.filter(
            Q(name__icontains="junior") | Q(name__icontains="youth") | Q(name__iregex=r"u[ -]?1[3-9]")
        ).values_list("tournament_id", "name"):
            suffix = tournament_youth(name)
            if not suffix:
                continue
            for code in OPEN:
                qs = Match.objects.filter(tournament_id=tid, event=code)
                n = qs.count()
                if n:
                    moves[f"{code}->{code}{suffix} (youth tournament)"] += n
                    youth_changed += n
                    if not dry:
                        qs.update(event=f"{code}{suffix}")

        # --- Draws: string pass only (no lineup) ------------------------------
        d_changed = 0
        for raw in Draw.objects.values_list("event", flat=True).order_by().distinct():
            if is_final_event(raw):
                continue
            code, _ = canonical_event(raw)
            if not is_final_event(code):
                continue
            qs = Draw.objects.filter(event=raw)
            d_changed += qs.count()
            if not dry:
                qs.update(event=code)

        for mv, n in moves.most_common():
            self.stdout.write(f"  {mv}  ({n})")
        verb = "would update" if dry else "updated"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {m_changed} (string) + {lineup_changed} (lineup) + "
            f"{youth_changed} (youth tournament) matches, "
            f"{d_changed} draws."))
        if not dry:
            self.stdout.write("Run `manage.py rate` + build_* to recompute.")
