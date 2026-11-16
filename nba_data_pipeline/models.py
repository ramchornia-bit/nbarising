from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    team_id: int
    abbreviation: str
    name: str
    city: str | None = None


@dataclass(frozen=True)
class Player:
    player_id: int
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    current_team_id: int | None = None
    active: bool | None = None


@dataclass(frozen=True)
class Game:
    game_id: str
    season: str
    game_date: str
    status: str | None
    home_team_id: int
    away_team_id: int
    home_score: int | None = None
    away_score: int | None = None
    season_type: int | None = None  # ESPN: 1 preseason, 2 regular season, 3 postseason


@dataclass(frozen=True)
class PlayerGameStat:
    game_id: str
    player_id: int
    team_id: int
    opponent_team_id: int
    game_date: str
    started: bool | None
    played: bool | None
    minutes_seconds: int | None
    points: int | None
    rebounds: int | None
    offensive_rebounds: int | None
    defensive_rebounds: int | None
    assists: int | None
    steals: int | None
    blocks: int | None
    turnovers: int | None
    personal_fouls: int | None
    plus_minus: float | None
    fgm: int | None
    fga: int | None
    fg3m: int | None
    fg3a: int | None
    ftm: int | None
    fta: int | None
    nba_fantasy_points: float | None
    source: str


@dataclass(frozen=True)
class PlayerGameAdvancedStat:
    game_id: str
    player_id: int
    usage_percentage: float | None
    estimated_usage_percentage: float | None
    true_shooting_percentage: float | None
    effective_field_goal_percentage: float | None
    pace: float | None
    possessions: float | None
    pie: float | None
    source: str
