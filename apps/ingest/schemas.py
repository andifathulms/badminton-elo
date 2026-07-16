"""Pydantic v2 models validating raw BWF payloads before any ORM write (PRD §9).

A malformed match is logged and skipped, not allowed to crash a draw. These
models describe only the fields the ingestion contract (PRD §6) consumes;
unknown keys are ignored so the fan API can add fields without breaking us.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _empty_date(cls, v):
        return None if v in ("", None) else v


# --- vue-tournament-draws ---------------------------------------------------
class DrawInfo(_Base):
    value: str
    text: str  # event: MS/WS/MD/WD/XD
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
    """One entry of the flat `matches` array (PRD §4.3)."""

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

    @field_validator("team1_seed", "team2_seed", mode="before")
    @classmethod
    def _seed_str(cls, v):
        return "" if v is None else str(v)

    @field_validator("match_time_utc", mode="before")
    @classmethod
    def _empty_dt(cls, v):
        return None if v in ("", None) else v


class DrawData(_Base):
    matches: list[MatchRaw] = Field(default_factory=list)
