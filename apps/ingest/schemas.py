"""Pydantic v2 models validating raw BWF payloads before any ORM write (PRD §9).

A malformed match is logged and skipped, not allowed to crash a draw. These
models describe only the fields the ingestion contract (PRD §6) consumes;
unknown keys are ignored so the fan API can add fields without breaking us.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# --- vue-tournament-detail --------------------------------------------------
class CategoryModel(_Base):
    name: str = ""


class TournamentDetail(_Base):
    id: int
    code: str
    name: str
    slug: str = ""
    start_date: date | None = None
    end_date: date | None = None
    tournament_category_id: int | None = None
    category_model: CategoryModel | None = Field(default=None, alias="categoryModel")
    tournament_series_id: int | None = None
    prize_money: Decimal | None = None
    venue_name: str = ""
    venue_address1: str = ""

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _empty_date(cls, v):
        if v in ("", None):
            return None
        # Some tournaments send a datetime with a non-zero time
        # ("2025-06-03 08:00:00"); keep only the calendar date.
        if isinstance(v, str):
            return v.replace("T", " ").split(" ")[0]
        return v

    @field_validator("slug", "venue_name", "venue_address1", mode="before")
    @classmethod
    def _none_to_str(cls, v):
        # The detail payload sends null for missing venue/slug fields.
        return "" if v is None else v


# --- vue-tournament-draws ---------------------------------------------------
class DrawInfo(_Base):
    value: str
    text: str  # "XD" (main) or "XD - Qualification" (qualifying)
    slug: str = ""
    size: int | None = None
    doubles: bool = False
    qualification: int = 0
    stage_name: str = ""
    stage_order: int | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, v):
        return str(v)

    @property
    def event(self) -> str:
        """Clean discipline code (MS/WS/MD/WD/XD) parsed from `text`."""
        return self.text.split(" - ")[0].split("-")[0].strip()


# --- vue-tournament-draw-data (PRIMARY results source) ----------------------
class PlayerRef(_Base):
    id: int
    name_display: str = Field(default="", alias="nameDisplay")
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    name_short: str = Field(default="", alias="nameShort")
    slug: str = ""
    country_code: str = Field(default="", alias="countryCode")

    @field_validator("name_display", mode="before")
    @classmethod
    def _name_fallback(cls, v):
        return v or ""


class TeamRef(_Base):
    players: list[PlayerRef] = Field(default_factory=list)


class GameScore(_Base):
    set: int | None = None
    home: int  # team1 / side 1
    away: int  # team2 / side 2


class MatchRaw(_Base):
    """One match — shared by the flat draw-data `matches` array (PRD §4.3) and
    the day-matches array (PRD §4.4), which carry the same shape."""

    id: int  # globally unique — primary upsert key
    code: str = ""
    event_name: str = Field(default="", alias="eventName")  # MS/WS/MD/WD/XD
    draw_name: str = Field(default="", alias="drawName")
    draw_code: str = Field(default="", alias="drawCode")
    round_name: str = Field(default="", alias="roundName")  # R32…Final
    match_status: str = Field(default="", alias="matchStatus")
    score_status: int | None = Field(default=None, alias="scoreStatus")
    score_status_value: str = Field(default="", alias="scoreStatusValue")
    winner: int | None = None  # 1 or 2 — who ADVANCED (PRD §6.3)
    team1: TeamRef | None = None
    team2: TeamRef | None = None
    team1_seed: str = Field(default="", alias="team1seed")
    team2_seed: str = Field(default="", alias="team2seed")
    score: list[GameScore] = Field(default_factory=list)
    match_time_utc: datetime | None = Field(default=None, alias="matchTimeUtc")
    duration: int | None = None
    reliability: int | None = None
    court_name: str = Field(default="", alias="courtName")
    # Present in day-matches payloads (per-match); absent in draw-data.
    tournament_code: str = Field(default="", alias="tournamentCode")
    tournament_name: str = Field(default="", alias="tournamentName")

    @field_validator("team1_seed", "team2_seed", mode="before")
    @classmethod
    def _seed_str(cls, v):
        return "" if v is None else str(v)

    @field_validator("match_time_utc", mode="before")
    @classmethod
    def _empty_dt(cls, v):
        return None if v in ("", None) else v

    @field_validator("match_time_utc", mode="after")
    @classmethod
    def _as_utc(cls, v: datetime | None):
        # day-matches gives "YYYY-MM-DD HH:MM:SS" (naive UTC); pin the tzinfo so
        # Django's USE_TZ storage never guesses.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class DrawData(_Base):
    matches: list[MatchRaw] = Field(default_factory=list)


# day-matches returns a BARE array of matches (no wrapper object).
DayMatches = TypeAdapter(list[MatchRaw])


# --- vue-grouped-year-tournaments (season calendar) -------------------------
class CalendarTournament(_Base):
    """One tournament entry from the calendar (PRD §4.7 enumeration source)."""

    id: int
    code: str
    name: str
    slug: str = ""
    start_date: datetime | None = None
    end_date: datetime | None = None
    category: str = ""  # tier label, e.g. "HSBC BWF World Tour Super 500"
    country: str = ""
    location: str = ""
    prize_money: str = ""  # calendar sends a formatted string ("1,450,000") or null
    month_no: int | None = Field(default=None, alias="monthNo")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _empty_dt(cls, v):
        return None if v in ("", None) else v

    @field_validator("prize_money", mode="before")
    @classmethod
    def _prize_str(cls, v):
        return "" if v is None else str(v)

    @property
    def start(self) -> date | None:
        return self.start_date.date() if self.start_date else None

    @property
    def end(self) -> date | None:
        return self.end_date.date() if self.end_date else None

    @property
    def prize_money_decimal(self) -> Decimal | None:
        cleaned = self.prize_money.replace(",", "").strip()
        try:
            return Decimal(cleaned) if cleaned else None
        except (ArithmeticError, ValueError):
            return None


class _CalendarMonth(_Base):
    month: str = ""
    month_no: int | None = Field(default=None, alias="monthNo")
    tournaments: list[CalendarTournament] = Field(default_factory=list)


class GroupedYearTournaments(_Base):
    """Response wrapper: results[] is a list of months, each with tournaments."""

    results: list[_CalendarMonth] = Field(default_factory=list)

    def all_tournaments(self) -> list[CalendarTournament]:
        return [t for m in self.results for t in m.tournaments]
