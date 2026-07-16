"""Glicko-2-with-pairs update (PRD §7.1–§7.5) — Phase 2.

STUB. Not to be implemented until the M1 ingestion acceptance test passes
(CLAUDE.md: "DON'T start Phase 2 before M1"). The signature and contract are
fixed here so the persistence bridge (`manage.py rate`) and the pair-blend math
can be designed against a stable interface.

Planned update (per match, both sides):
  team rating   R_T  = mean(mu_i)         (PAIR_BLEND, default mean)
  team RD       RD_T = sqrt(mean(rd_i^2))
  expected      E    = 1 / (1 + 10^((R_opp - R_T)/400)) with g(RD_opp) damping
  surprise      S - E, S binary from winner_side
  magnitude    *= margin_multiplier(dominance) * tier_weight   (Normal only)
  retirement    reduced update K_RETIRE, dominance NOT read from scoreline
  each player moves scaled by their OWN rd; shrink rd after; inflate for inactivity
"""
from __future__ import annotations

from .types import MatchRecord, Rating, RatingConfig, RatingDelta


def update_match(
    match: MatchRecord,
    side1: list[Rating],
    side2: list[Rating],
    config: RatingConfig,
) -> list[RatingDelta]:
    """Apply one match to the given players' ratings (mutates in place).

    Returns a RatingDelta per player for RatingHistory. Phase 2.
    """
    raise NotImplementedError("rating.engine.update_match is Phase 2 (post-M1)")
