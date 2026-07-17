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
    code = models.CharField(max_length=64, unique=True)  # GUID
    name = models.CharField(max_length=255)
    slug = models.SlugField(blank=True, max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    category_id = models.IntegerField(null=True, blank=True)
    category_name = models.CharField(max_length=255, blank=True)  # tier
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
