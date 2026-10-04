"""DRF read-only views (PRD §12), one module per area of the site.

    rankings     leaderboard, pairs, pair detail, head-to-head
    players      profile, search, rating history, style, match history
    matches      a match, a player's tournament run, match records
    tournaments  list, master, tiers, detail, bracket matches, team-cup ties
    analytics    gains/performances/upsets, calibration, clutch, synergy, ...
    cups         national team power, now and over time
    home         the Home composite payload and the discipline list
    common       shared helpers
"""
from .analytics import (
    AgingView,
    AnalyticsView,
    CalibrationView,
    ClutchView,
    ConsistencyView,
    DynastiesView,
    SynergyView,
)
from .cups import CupHistoryView, CupView
from .home import EventsView, HomeView
from .matches import MatchViewSet, PerformancePathView, RecordsView
from .players import PlayerMatchesView, PlayerViewSet
from .rankings import H2HView, LeaderboardView, PairDetailView, PairsView
from .tournaments import TournamentViewSet

__all__ = [
    "AgingView", "AnalyticsView", "CalibrationView", "ClutchView", "ConsistencyView",
    "CupHistoryView", "CupView", "DynastiesView", "EventsView", "H2HView", "HomeView",
    "LeaderboardView", "MatchViewSet", "PairDetailView", "PairsView",
    "PerformancePathView", "PlayerMatchesView", "PlayerViewSet", "RecordsView",
    "SynergyView", "TournamentViewSet",
]
