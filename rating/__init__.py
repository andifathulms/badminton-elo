"""Pure rating engine (PRD §7) — NO Django, NO ORM, NO request cycle.

This package takes plain dataclasses/dicts in and returns rating rows out. The
ONLY bridge to persistence is `manage.py rate`, which reads ORM rows, converts
them to the dataclasses in `rating.types`, calls `rating.run`, and writes the
results back. Keeping this boundary is non-negotiable (CLAUDE.md architecture
principle): it is what keeps the rating math unit-testable and uncorrupted.

Phase status: dominance (§7.3) is implemented and tested; the Glicko-2-with-
pairs update (§7.1–§7.5) and the chronological driver are Phase-2 stubs, not to
be fleshed out until the M1 ingestion acceptance test passes.
"""
from .dominance import dominance, margin_multiplier

__all__ = ["dominance", "margin_multiplier"]
