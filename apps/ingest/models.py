"""Django models for BWF ingestion (PRD §5).

Persistence layer only. The rating math lives in the pure `rating/` package and
never touches these models directly — `manage.py rate` reads rows out, converts
them to plain dataclasses, and writes PlayerRating/RatingHistory back.

Domain invariants enforced here and in normalize.py:
  * upsert by stable ids (tournament_id, player_id, match_id) — re-scrape is a no-op
  * winner_side = who ADVANCED (may hold fewer points on retire/walkover)
  * side1 = team1 = score.home; side2 = team2 = score.away — never reordered
"""
from __future__ import annotations

from django.db import models


class Tournament(models.Model):
    tournament_id = models.IntegerField(primary_key=True)  # detail.results.id
    # GUID. Null for very old tournaments that predate BWF's GUIDs (SQLite and
    # Postgres both allow multiple NULLs under a unique constraint).
    code = models.CharField(max_length=64, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(blank=True, max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    category_id = models.IntegerField(null=True, blank=True)
    category_name = models.CharField(max_length=255, blank=True)  # tier
    logo_url = models.URLField(max_length=512, blank=True)  # BWF tournament logo
    series_id = models.IntegerField(null=True, blank=True)
    prize_money = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    venue_name = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tournament_id})"


class Player(models.Model):
    player_id = models.IntegerField(primary_key=True)  # stable BWF id
    name_display = models.CharField(max_length=255)
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    name_short = models.CharField(max_length=128, blank=True)
    slug = models.SlugField(blank=True, max_length=255)
    country_code = models.CharField(max_length=8, blank=True)
    avatar_url = models.URLField(blank=True, max_length=512)
    dob = models.DateField(null=True, blank=True)
    height_cm = models.IntegerField(null=True, blank=True)
    plays = models.CharField(max_length=8, blank=True)
    # From BWF vue-player-bio (filled by collect_player_bio).
    current_residence = models.CharField(max_length=128, blank=True)
    languages = models.CharField(max_length=128, blank=True)
    birth_place = models.CharField(max_length=128, blank=True)
    prize_money = models.CharField(max_length=32, blank=True)
    # Inferred from discipline participation (MS/MD -> M, WS/WD -> F), NOT from
    # the payload. Blank when only XD/unknown events are seen. See infer_gender.
    gender = models.CharField(max_length=1, blank=True)  # "M" | "F" | ""
    # For players sourced from Wikipedia (1983-2006 gap). Their stable [[wiki
    # title]] is the identity; player_id is a synthetic namespaced id. Reconcile
    # to a real BWF id later by name. Blank for BWF-API players.
    wiki_title = models.CharField(max_length=255, blank=True, db_index=True)

    class Meta:
        ordering = ["name_display"]
        indexes = [models.Index(fields=["country_code"])]

    def __str__(self) -> str:
        return f"{self.name_display} ({self.player_id})"


class Draw(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="draws"
    )
    draw_value = models.CharField(max_length=16)  # "10"
    event = models.CharField(max_length=4)  # MS/WS/MD/WD/XD
    stage = models.CharField(max_length=32)  # Main Draw / Qualifying
    doubles = models.BooleanField(default=False)
    size = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("tournament", "draw_value")
        ordering = ["tournament", "event"]

    def __str__(self) -> str:
        return f"{self.tournament_id}/{self.event} (draw {self.draw_value})"


class Match(models.Model):
    match_id = models.IntegerField(primary_key=True)  # BWF match id (upsert key)
    code = models.CharField(max_length=16, blank=True)
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="matches"
    )
    draw = models.ForeignKey(
        Draw, on_delete=models.CASCADE, null=True, blank=True, related_name="matches"
    )
    event = models.CharField(max_length=4)
    round_name = models.CharField(max_length=16)  # R32…Final
    round_order = models.IntegerField(default=0)  # derived (PRD §6.4)
    match_time_utc = models.DateTimeField(null=True, blank=True)
    duration_min = models.IntegerField(null=True, blank=True)
    court_name = models.CharField(max_length=64, blank=True)
    score_status = models.CharField(max_length=32)  # Normal/Retired/Walkover/…
    reliability = models.IntegerField(null=True, blank=True)  # 0/1
    winner_side = models.IntegerField(null=True, blank=True)  # 1 or 2 (advanced)
    side1_seed = models.CharField(max_length=8, blank=True)
    side2_seed = models.CharField(max_length=8, blank=True)
    scoring_format = models.CharField(max_length=16, blank=True)  # 3x21|3x15|…
    # True unless walkover/no-play/unknown status (PRD §6.6). Rating engine skips
    # rating_excluded matches; they are still ingested for completeness.
    rating_excluded = models.BooleanField(default=False)
    # Stable dedup key for non-BWF-API sources (e.g. Wikipedia). Lets re-scrapes
    # find the existing row so its synthetic match_id stays put. Null for BWF.
    source_key = models.CharField(max_length=255, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["match_time_utc", "round_order", "match_id"]
        indexes = [
            models.Index(fields=["tournament", "event"]),
            models.Index(fields=["event", "match_time_utc"]),
        ]

    def __str__(self) -> str:
        return f"Match {self.match_id} [{self.event} {self.round_name}]"


class MatchPlayer(models.Model):
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="lineup"
    )
    side = models.IntegerField()  # 1 or 2
    player = models.ForeignKey(Player, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("match", "side", "player")
        ordering = ["match", "side"]

    def __str__(self) -> str:
        return f"M{self.match_id} side{self.side}: {self.player_id}"


class Game(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="games")
    game_no = models.IntegerField()
    side1_points = models.IntegerField()  # score.home
    side2_points = models.IntegerField()  # score.away

    class Meta:
        unique_together = ("match", "game_no")
        ordering = ["match", "game_no"]

    def __str__(self) -> str:
        return f"M{self.match_id} G{self.game_no}: {self.side1_points}-{self.side2_points}"


# --- Phase 2 outputs (written by `manage.py rate`) --------------------------
class PlayerRating(models.Model):
    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="ratings"
    )
    event = models.CharField(max_length=4)  # discipline bucket
    mu = models.FloatField()
    rd = models.FloatField()
    sigma = models.FloatField()
    matches_played = models.IntegerField(default=0)
    last_match_utc = models.DateTimeField(null=True, blank=True)
    # All-time peak (highest mu ever reached) and the state/date at that peak.
    peak_mu = models.FloatField(null=True, blank=True)
    peak_rd = models.FloatField(null=True, blank=True)
    peak_utc = models.DateTimeField(null=True, blank=True)
    # Standard deviation of this player's per-match rating deltas in the event —
    # a form-volatility measure (low = steady, high = erratic). Set by
    # build_consistency after rate; null until then.
    volatility = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("player", "event")
        ordering = ["event", "-mu"]

    def __str__(self) -> str:
        return f"{self.player_id}/{self.event}: mu={self.mu:.0f} rd={self.rd:.0f}"


class RatingHistory(models.Model):
    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="rating_history"
    )
    event = models.CharField(max_length=4)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    mu_before = models.FloatField()
    mu_after = models.FloatField()
    rd_before = models.FloatField()
    rd_after = models.FloatField()
    delta = models.FloatField()
    # Null only for the rare match with neither a match time nor a tournament date.
    applied_utc = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["applied_utc", "match_id"]
        indexes = [models.Index(fields=["player", "event", "applied_utc"])]

    def __str__(self) -> str:
        return f"{self.player_id}/{self.event} @M{self.match_id}: {self.delta:+.1f}"


class Partnership(models.Model):
    """A doubles/mixed partnership (derived, PRD domain rule 5: no PAIR rating is
    computed by the engine — this is a read-side aggregate of two members who
    played together, with their combined current strength for ranking)."""

    event = models.CharField(max_length=8)  # MD / WD / XD
    player1 = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="partnerships_as_p1"
    )
    player2 = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="partnerships_as_p2"
    )
    matches_together = models.IntegerField(default=0)
    wins_together = models.IntegerField(default=0)
    combined_mu = models.FloatField()  # mean of members' current mu
    combined_rd = models.FloatField()  # RMS of members' current rd
    # Combined all-time peak — mean of members' peak mu / RMS of peak rd.
    combined_peak_mu = models.FloatField(null=True, blank=True)
    combined_peak_rd = models.FloatField(null=True, blank=True)
    last_match_utc = models.DateTimeField(null=True, blank=True)
    # Chess-style performance rating from the pair's own results vs the fields
    # they faced, and synergy = perf_rating − combined_mu (how much the duo
    # over/under-performs the mean of its members). Set by build_synergy.
    perf_rating = models.FloatField(null=True, blank=True)
    synergy = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("event", "player1", "player2")
        ordering = ["event", "-combined_mu"]
        indexes = [models.Index(fields=["event", "-combined_mu"])]

    def __str__(self) -> str:
        return f"{self.event}: {self.player1_id}+{self.player2_id} ({self.matches_together})"


class MatchStatistics(models.Model):
    """Rich per-match statistics from the h2h/match endpoint (rally counts +
    point-by-point progression). Optional enrichment, fetched lazily/in bulk."""

    match = models.OneToOneField(
        Match, on_delete=models.CASCADE, related_name="stats", primary_key=True
    )
    team1_rallies_won = models.IntegerField(null=True, blank=True)
    team1_rallies_played = models.IntegerField(null=True, blank=True)
    team2_rallies_won = models.IntegerField(null=True, blank=True)
    team2_rallies_played = models.IntegerField(null=True, blank=True)
    team1_consecutive_points = models.IntegerField(null=True, blank=True)
    team2_consecutive_points = models.IntegerField(null=True, blank=True)
    team1_game_points = models.IntegerField(null=True, blank=True)
    team2_game_points = models.IntegerField(null=True, blank=True)
    duration_min = models.IntegerField(null=True, blank=True)
    # Per-game running score after every rally: [[[t1,t2], ...], ...per game].
    point_progression = models.JSONField(null=True, blank=True)
    # Biggest points deficit a game-winner overcame (e.g. down 10-20 -> 10).
    max_comeback = models.IntegerField(null=True, blank=True)
    fetched_utc = models.DateTimeField(null=True, blank=True)

    @property
    def total_rallies(self):
        return self.team1_rallies_played or self.team2_rallies_played

    def __str__(self) -> str:
        return f"stats M{self.match_id}"


class ReconcileDecision(models.Model):
    """A human ruling on an ambiguous Wikipedia<->BWF identity, keyed by the
    Wiki player's stable title so it isn't surfaced again once decided."""
    wiki_title = models.CharField(max_length=255, unique=True)
    decision = models.CharField(max_length=16)  # "merged" | "distinct"
    target_player_id = models.IntegerField(null=True, blank=True)  # for merged
    created_utc = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.wiki_title}: {self.decision}"


class PlayerSeedRank(models.Model):
    """Earliest-observed BWF World Ranking per (player, event), captured from
    h2h/statistics. Used to seed the rating engine (PRD §7.6)."""

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="seed_ranks"
    )
    event = models.CharField(max_length=8)
    rank = models.IntegerField()
    observed_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("player", "event")
        indexes = [models.Index(fields=["event", "rank"])]

    def __str__(self) -> str:
        return f"{self.player_id}/{self.event} rank {self.rank}"


class TournamentPerformance(models.Model):
    """Analytics: a player's net rating change across one tournament (a rating
    period). Derived from RatingHistory by `build_analytics` for fast browsing —
    e.g. the biggest ELO gainers of a tournament."""

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="tournament_perfs"
    )
    event = models.CharField(max_length=8)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    net_delta = models.FloatField()  # rating gained/lost over the tournament
    matches = models.IntegerField()
    mu_start = models.FloatField()  # rating at tournament start (locked)
    mu_end = models.FloatField()
    rd_start = models.FloatField(default=350.0)  # uncertainty at start (low = settled)
    best_match = models.ForeignKey(
        Match, on_delete=models.SET_NULL, null=True, blank=True
    )
    best_delta = models.FloatField(null=True, blank=True)  # biggest single win
    # Chess-style performance rating for this tournament: the rating at which the
    # player's/pair's results against this field of opponents would be expected.
    perf_rating = models.FloatField(null=True, blank=True)
    # For doubles: the player's main partner this tournament (to collapse the
    # two members' rows into one pair in analytics). Null for singles.
    partner = models.ForeignKey(
        Player, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tournament_perfs_as_partner",
    )

    class Meta:
        unique_together = ("player", "event", "tournament")
        indexes = [
            models.Index(fields=["-net_delta"]),
            models.Index(fields=["event", "-net_delta"]),
        ]

    def __str__(self) -> str:
        return f"{self.player_id}/{self.event} @{self.tournament_id}: {self.net_delta:+.0f}"


class CupPowerHistory(models.Model):
    """Analytics: a country's national-team power per year, reconstructed from
    RatingHistory (each player's rating as-of that year, active only). Powers the
    Cups timeline graph. cup in {thomas, uber, sudirman}."""

    cup = models.CharField(max_length=16)
    country = models.CharField(max_length=8)
    year = models.IntegerField()
    power = models.FloatField()

    class Meta:
        unique_together = ("cup", "country", "year")
        indexes = [models.Index(fields=["cup", "year"])]

    def __str__(self) -> str:
        return f"{self.cup} {self.country} {self.year}: {self.power:.0f}"


class CalibrationBin(models.Model):
    """Analytics: rating reliability. Every rated match is bucketed by the
    favorite's pre-match predicted win probability; `correct` counts how often
    that favorite actually won. Comparing predicted vs actual per bucket is a
    reliability diagram — the honest test of whether the rating is trustworthy.
    Built by `build_calibration` from RatingHistory. event="ALL" is every
    discipline pooled.
    """

    event = models.CharField(max_length=8)  # MS/WS/MD/WD/XD or "ALL"
    bucket = models.IntegerField()  # floor(prob*10): 5→[.50,.60) … 9→[.90,1.0]
    n = models.IntegerField(default=0)  # matches in this bucket
    correct = models.IntegerField(default=0)  # favorite won
    prob_sum = models.FloatField(default=0.0)  # Σ predicted prob (for the mean)

    class Meta:
        unique_together = ("event", "bucket")
        ordering = ["event", "bucket"]

    def __str__(self) -> str:
        return f"calib {self.event} b{self.bucket}: {self.correct}/{self.n}"


class ClutchStat(models.Model):
    """Analytics: 'clutch' record — how a player fares when a match goes the
    distance to a deciding third game. Built by `build_clutch` from the game
    counts + winner side (Normal matches only). `deciders_won / deciders_played`
    is the third-game win rate; `matches`/`wins` are the player's overall record
    in that discipline for context.
    """

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="clutch_stats"
    )
    event = models.CharField(max_length=8)  # MS/WS/MD/WD/XD
    deciders_played = models.IntegerField(default=0)  # matches that reached a 3rd game
    deciders_won = models.IntegerField(default=0)
    matches = models.IntegerField(default=0)  # all Normal matches in the event
    wins = models.IntegerField(default=0)

    class Meta:
        unique_together = ("player", "event")
        indexes = [models.Index(fields=["event", "-deciders_played"])]

    def __str__(self) -> str:
        return f"clutch {self.player_id}/{self.event}: {self.deciders_won}/{self.deciders_played}"


class NationYear(models.Model):
    """Analytics: a country's strength in one discipline as of each year-end —
    the sum of its top-3 active players' rating that year (mirrors
    CupPowerHistory but per single discipline). Built by `build_nation_power`
    from RatingHistory; powers the per-discipline dominance / dynasty timeline.
    """

    event = models.CharField(max_length=8)  # MS/WS/MD/WD/XD
    country = models.CharField(max_length=8)
    year = models.IntegerField()
    power = models.FloatField()  # Σ top-3 active players' mu
    players = models.IntegerField(default=0)  # how many contributed (<=3)

    class Meta:
        unique_together = ("event", "country", "year")
        indexes = [models.Index(fields=["event", "year"])]

    def __str__(self) -> str:
        return f"{self.event} {self.country} {self.year}: {self.power:.0f}"


class RawCache(models.Model):
    """Read-through cache of every raw API response (PRD §5, domain rule 9).

    The scraper reads from here before hitting the network; a matching row means
    zero HTTP. Bodies are also mirrored to data/raw/ for offline inspection.
    """

    url = models.CharField(max_length=512, primary_key=True)
    fetched_utc = models.DateTimeField()
    status = models.IntegerField()
    body = models.TextField()

    class Meta:
        ordering = ["-fetched_utc"]

    def __str__(self) -> str:
        return f"{self.status} {self.url}"
