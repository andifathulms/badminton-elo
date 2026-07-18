"""Glicko-2-with-pairs update (PRD §7.1–§7.5) — pure, deterministic.

The math, and only the math. No Django, no I/O. `run.py` drives it over an
ordered match stream; `manage.py rate` bridges it to the ORM.

Design (a faithful Glicko-2 adaptation for changing pairs):

  * Rating is per (player, discipline): (mu, rd, sigma) on the natural 1500/350
    scale, converted to Glicko-2's internal (µ, φ) for the update.
  * A doubles side's strength is the blend of its members (PRD §7.2):
    R_T = mean(mu_i), RD_T = sqrt(mean(rd_i²)). Singles is the 1-member case.
  * The outcome S is binary from `winner_side` (who ADVANCED — never the
    scoreline). The team EXPECTATION E uses the opponent-team rating with g(RD)
    damping, so both members of a side share one surprise (S − E).
  * Each player moves scaled by THEIR OWN φ: a high-rd (new/seeded) player has
    large variance v and swings a lot; a low-rd (established) player barely
    moves. This is the "strong A + new C" fairness mechanism (PRD §7.4), and it
    is why A's gains propagate into every future A-pairing for free.
  * Margin (M, PRD §7.3) and tier (W) scale only the magnitude of the µ move,
    never the direction or the volatility estimate. Retirement (PRD §7.5) uses
    K_RETIRE as an extra magnitude scale with M = 1 (dominance not read).
  * φ shrinks after every rated match; run.py re-inflates it for inactivity.

Excluded/walkover matches and any match without a decisive winner return no
deltas (the caller skips them).
"""
from __future__ import annotations

import math

from .dominance import dominance, margin_multiplier
from .types import MatchRecord, Rating, RatingConfig, RatingDelta

# Glicko-2 scale factor between natural (Elo-like) and internal units.
_SCALE = 173.7178
_CONVERGENCE = 1e-6


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_opp: float, phi_opp: float) -> float:
    """Glicko-2 expected score of `mu` vs an opponent (mu_opp, phi_opp)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_opp) * (mu - mu_opp)))


def _team_mu_phi(ratings: list[Rating]) -> tuple[float, float]:
    """Blend members into a team (mu, phi) on the Glicko-2 internal scale."""
    n = len(ratings)
    mu_nat = sum(r.mu for r in ratings) / n
    rd_rms = math.sqrt(sum(r.rd * r.rd for r in ratings) / n)
    return (mu_nat - 1500.0) / _SCALE, rd_rms / _SCALE


def _new_sigma(sigma: float, phi: float, v: float, delta: float, tau: float) -> float:
    """Glicko-2 volatility update via the Illinois root-finder (deterministic)."""
    a = math.log(sigma * sigma)
    d2 = delta * delta
    phi2 = phi * phi

    def f(x: float) -> float:
        ex = math.exp(x)
        denom = phi2 + v + ex
        return (ex * (d2 - phi2 - v - ex)) / (2.0 * denom * denom) - (x - a) / (tau * tau)

    A = a
    if d2 > phi2 + v:
        B = math.log(d2 - phi2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0.0:
            k += 1
        B = a - k * tau

    fA, fB = f(A), f(B)
    while abs(B - A) > _CONVERGENCE:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB <= 0.0:
            A, fA = B, fB
        else:
            fA /= 2.0
        B, fB = C, fC
    return math.exp(A / 2.0)


def update_match(
    match: MatchRecord,
    side1: list[Rating],
    side2: list[Rating],
    config: RatingConfig,
) -> list[RatingDelta]:
    """Apply one match to the given players' ratings, mutating them in place.

    `side1`/`side2` align with `match.side1_player_ids`/`side2_player_ids`.
    Returns one RatingDelta per player (for RatingHistory). Excluded matches or
    a non-decisive winner yield no change.
    """
    if match.rating_excluded or match.winner_side not in (1, 2) or not side1 or not side2:
        return []

    # Margin multiplier — Normal only; retirement reads no dominance (PRD §7.3/§7.5).
    if match.is_retired:
        m_mult = 1.0
        magnitude = config.k_retire
    else:
        d = dominance(match.games, match.winner_side, d_floor=config.d_floor)
        m_mult = margin_multiplier(d, config)
        magnitude = 1.0
    magnitude *= m_mult * match.tier_weight

    s1 = 1.0 if match.winner_side == 1 else 0.0
    mu1_t, phi1_t = _team_mu_phi(side1)
    mu2_t, phi2_t = _team_mu_phi(side2)

    deltas: list[RatingDelta] = []
    deltas += _update_side(
        match, side1, match.side1_player_ids, s1, mu1_t, mu2_t, phi2_t, magnitude, config
    )
    deltas += _update_side(
        match, side2, match.side2_player_ids, 1.0 - s1, mu2_t, mu1_t, phi1_t, magnitude, config
    )
    return deltas


def update_period(
    matches: list[MatchRecord],
    ratings: dict[tuple[int, str], Rating],
    config: RatingConfig,
) -> list[RatingDelta]:
    """Apply one rating period (a tournament) — the tournament-locked update.

    All expectations use each player's rating at the START of the period (the
    `ratings` passed in, left unmutated until the end): so when A and B meet,
    the calc uses their start-of-tournament strength, not a mid-tournament
    figure inflated by earlier-round wins. Each player's Glicko-2 update is
    accumulated across all their matches in the period and applied once. Per-
    match deltas are the marginal contributions (they sum to the period change),
    so the UI can still attribute "+x from this win".
    """
    from collections import defaultdict

    # Frozen (mu, rd) snapshot for team blending — never changes mid-period.
    frozen = {k: (r.mu, r.rd) for k, r in ratings.items()}

    def team(pids, event):
        n = len(pids)
        mu_nat = sum(frozen[(p, event)][0] for p in pids) / n
        rd_rms = math.sqrt(sum(frozen[(p, event)][1] ** 2 for p in pids) / n)
        return (mu_nat - 1500.0) / _SCALE, rd_rms / _SCALE

    acc = defaultdict(
        lambda: {"dsum": 0.0, "dsumw": 0.0, "vinv": 0.0, "n": 0,
                 "last": None, "contribs": []}
    )

    for m in sorted(matches, key=lambda x: (x.round_order, x.match_id)):
        if m.rating_excluded or m.winner_side not in (1, 2):
            continue
        if not m.side1_player_ids or not m.side2_player_ids:
            continue
        if m.is_retired:
            magnitude = config.k_retire * m.tier_weight
        else:
            d = dominance(m.games, m.winner_side, d_floor=config.d_floor)
            magnitude = margin_multiplier(d, config) * m.tier_weight

        mu1, phi1 = team(m.side1_player_ids, m.event)
        mu2, phi2 = team(m.side2_player_ids, m.event)
        s1 = 1.0 if m.winner_side == 1 else 0.0
        for ids, s, mu_t, mu_o, phi_o in (
            (m.side1_player_ids, s1, mu1, mu2, phi2),
            (m.side2_player_ids, 1.0 - s1, mu2, mu1, phi1),
        ):
            g = _g(phi_o)
            e = _expected(mu_t, mu_o, phi_o)
            term = g * (s - e)
            for pid in ids:
                a = acc[(pid, m.event)]
                a["dsum"] += term
                a["dsumw"] += term * magnitude
                a["vinv"] += g * g * e * (1.0 - e)
                a["n"] += 1
                a["contribs"].append((m, term * magnitude))
                if m.match_time_utc and (a["last"] is None or m.match_time_utc > a["last"]):
                    a["last"] = m.match_time_utc

    deltas: list[RatingDelta] = []
    for (pid, event), a in acc.items():
        if a["vinv"] <= 0.0:
            continue
        r = ratings[(pid, event)]
        mu = (r.mu - 1500.0) / _SCALE
        phi = r.rd / _SCALE
        v = 1.0 / a["vinv"]
        sigma_new = _new_sigma(r.sigma, phi, v, v * a["dsum"], config.tau)
        phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
        phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)

        mu_before, rd_before = r.mu, r.rd
        r.mu = (mu + phi_new * phi_new * a["dsumw"]) * _SCALE + 1500.0
        r.rd = min(phi_new * _SCALE, config.rd_init)
        r.sigma = sigma_new
        r.matches_played += a["n"]
        r.last_match_utc = a["last"] or r.last_match_utc

        # Per-match marginal deltas (sum to r.mu - mu_before), in round order.
        cum = 0.0
        for m, contrib in a["contribs"]:
            d_pts = phi_new * phi_new * contrib * _SCALE
            cum += d_pts
            deltas.append(
                RatingDelta(
                    player_id=pid, event=event, match_id=m.match_id,
                    mu_before=mu_before, mu_after=mu_before + cum,
                    rd_before=rd_before, rd_after=r.rd,
                    delta=d_pts, applied_utc=m.match_time_utc,
                )
            )
    return deltas


def _update_side(
    match: MatchRecord,
    ratings: list[Rating],
    player_ids: tuple[int, ...],
    s: float,
    mu_team: float,
    mu_opp: float,
    phi_opp: float,
    magnitude: float,
    config: RatingConfig,
) -> list[RatingDelta]:
    """Update every player on one side against the opponent team."""
    g_opp = _g(phi_opp)
    # Team-level expectation — shared surprise for both members (PRD §7.4).
    e_team = _expected(mu_team, mu_opp, phi_opp)
    surprise = s - e_team

    out: list[RatingDelta] = []
    for player_id, r in zip(player_ids, ratings):
        mu = (r.mu - 1500.0) / _SCALE
        phi = r.rd / _SCALE

        # Per-player variance from the shared expectation — high phi => big v.
        v = 1.0 / (g_opp * g_opp * e_team * (1.0 - e_team))
        delta = v * g_opp * surprise  # direction only; no margin/tier here

        sigma_new = _new_sigma(r.sigma, phi, v, delta, config.tau)
        phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
        phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)

        # Magnitude (margin × tier × retire) scales the µ move only.
        mu_new = mu + phi_new * phi_new * g_opp * surprise * magnitude

        mu_before, rd_before = r.mu, r.rd
        r.mu = mu_new * _SCALE + 1500.0
        r.rd = min(phi_new * _SCALE, config.rd_init)
        r.sigma = sigma_new
        r.matches_played += 1
        r.last_match_utc = match.match_time_utc

        out.append(
            RatingDelta(
                player_id=player_id,
                event=match.event,
                match_id=match.match_id,
                mu_before=mu_before,
                mu_after=r.mu,
                rd_before=rd_before,
                rd_after=r.rd,
                delta=r.mu - mu_before,
                applied_utc=match.match_time_utc,
            )
        )
    return out
