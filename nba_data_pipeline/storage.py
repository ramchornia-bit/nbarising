from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import Game, Player, PlayerGameAdvancedStat, PlayerGameStat, Team


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY,
    abbreviation TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    city TEXT
);

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    current_team_id INTEGER,
    active INTEGER
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    season TEXT NOT NULL,
    game_date TEXT NOT NULL,
    status TEXT,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    home_score INTEGER,
    away_score INTEGER
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    opponent_team_id INTEGER NOT NULL,
    game_date TEXT NOT NULL,
    started INTEGER,
    played INTEGER,
    minutes_seconds INTEGER,
    points INTEGER,
    rebounds INTEGER,
    offensive_rebounds INTEGER,
    defensive_rebounds INTEGER,
    assists INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    personal_fouls INTEGER,
    plus_minus REAL,
    fgm INTEGER,
    fga INTEGER,
    fg3m INTEGER,
    fg3a INTEGER,
    ftm INTEGER,
    fta INTEGER,
    nba_fantasy_points REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (game_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_player_game_stats_player_date
    ON player_game_stats (player_id, game_date DESC);

CREATE TABLE IF NOT EXISTS player_game_advanced_stats (
    game_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    usage_percentage REAL,
    estimated_usage_percentage REAL,
    true_shooting_percentage REAL,
    effective_field_goal_percentage REAL,
    pace REAL,
    possessions REAL,
    pie REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (game_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_form_snapshots (
    player_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    window_games INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    avg_fantasy_points REAL,
    avg_minutes REAL,
    avg_shot_volume REAL,
    fantasy_points_slope REAL,
    minutes_slope REAL,
    shot_volume_slope REAL,
    consistency_score REAL,
    opportunity_score REAL,
    breakout_score REAL,
    drop_risk REAL,
    waiver_score REAL,
    profile TEXT NOT NULL,
    explanation TEXT NOT NULL,
    PRIMARY KEY (player_id, as_of_date, window_games)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SQLITE_SCHEMA)
    connection.commit()


def upsert_teams(connection: sqlite3.Connection, teams: Iterable[Team]) -> None:
    connection.executemany(
        """
        INSERT INTO teams (team_id, abbreviation, name, city)
        VALUES (:team_id, :abbreviation, :name, :city)
        ON CONFLICT(team_id) DO UPDATE SET
            abbreviation = excluded.abbreviation,
            name = excluded.name,
            city = excluded.city
        """,
        [asdict(team) for team in teams],
    )


def upsert_players(connection: sqlite3.Connection, players: Iterable[Player]) -> None:
    rows = []
    for player in players:
        row = asdict(player)
        row["active"] = None if player.active is None else int(player.active)
        rows.append(row)
    connection.executemany(
        """
        INSERT INTO players (player_id, full_name, first_name, last_name, current_team_id, active)
        VALUES (:player_id, :full_name, :first_name, :last_name, :current_team_id, :active)
        ON CONFLICT(player_id) DO UPDATE SET
            full_name = excluded.full_name,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            current_team_id = excluded.current_team_id,
            active = excluded.active
        """,
        rows,
    )


def upsert_game(connection: sqlite3.Connection, game: Game) -> None:
    connection.execute(
        """
        INSERT INTO games (
            game_id, season, game_date, status, home_team_id, away_team_id, home_score, away_score
        )
        VALUES (
            :game_id, :season, :game_date, :status, :home_team_id, :away_team_id, :home_score, :away_score
        )
        ON CONFLICT(game_id) DO UPDATE SET
            season = excluded.season,
            game_date = excluded.game_date,
            status = excluded.status,
            home_team_id = excluded.home_team_id,
            away_team_id = excluded.away_team_id,
            home_score = excluded.home_score,
            away_score = excluded.away_score
        """,
        asdict(game),
    )


def upsert_player_game_stats(
    connection: sqlite3.Connection, stats_rows: Iterable[PlayerGameStat]
) -> None:
    rows = []
    for stat in stats_rows:
        row = asdict(stat)
        row["started"] = None if stat.started is None else int(stat.started)
        row["played"] = None if stat.played is None else int(stat.played)
        rows.append(row)
    connection.executemany(
        """
        INSERT INTO player_game_stats (
            game_id, player_id, team_id, opponent_team_id, game_date, started, played,
            minutes_seconds, points, rebounds, offensive_rebounds, defensive_rebounds,
            assists, steals, blocks, turnovers, personal_fouls, plus_minus, fgm, fga,
            fg3m, fg3a, ftm, fta, nba_fantasy_points, source
        )
        VALUES (
            :game_id, :player_id, :team_id, :opponent_team_id, :game_date, :started, :played,
            :minutes_seconds, :points, :rebounds, :offensive_rebounds, :defensive_rebounds,
            :assists, :steals, :blocks, :turnovers, :personal_fouls, :plus_minus, :fgm, :fga,
            :fg3m, :fg3a, :ftm, :fta, :nba_fantasy_points, :source
        )
        ON CONFLICT(game_id, player_id) DO UPDATE SET
            team_id = excluded.team_id,
            opponent_team_id = excluded.opponent_team_id,
            game_date = excluded.game_date,
            started = COALESCE(excluded.started, player_game_stats.started),
            played = COALESCE(excluded.played, player_game_stats.played),
            minutes_seconds = excluded.minutes_seconds,
            points = excluded.points,
            rebounds = excluded.rebounds,
            offensive_rebounds = excluded.offensive_rebounds,
            defensive_rebounds = excluded.defensive_rebounds,
            assists = excluded.assists,
            steals = excluded.steals,
            blocks = excluded.blocks,
            turnovers = excluded.turnovers,
            personal_fouls = excluded.personal_fouls,
            plus_minus = excluded.plus_minus,
            fgm = excluded.fgm,
            fga = excluded.fga,
            fg3m = excluded.fg3m,
            fg3a = excluded.fg3a,
            ftm = excluded.ftm,
            fta = excluded.fta,
            nba_fantasy_points = excluded.nba_fantasy_points,
            source = excluded.source
        """,
        rows,
    )


def save_boxscore(
    connection: sqlite3.Connection,
    teams: list[Team],
    players: list[Player],
    game: Game,
    stats_rows: list[PlayerGameStat],
) -> None:
    with connection:
        upsert_teams(connection, teams)
        upsert_players(connection, players)
        upsert_game(connection, game)
        upsert_player_game_stats(connection, stats_rows)


def save_player_game_logs(
    connection: sqlite3.Connection,
    teams: list[Team],
    players: list[Player],
    games: list[Game],
    stats_rows: list[PlayerGameStat],
) -> None:
    with connection:
        upsert_teams(connection, teams)
        upsert_players(connection, players)
        for game in games:
            upsert_game(connection, game)
        upsert_player_game_stats(connection, stats_rows)


def upsert_player_game_advanced_stats(
    connection: sqlite3.Connection, stats_rows: Iterable[PlayerGameAdvancedStat]
) -> None:
    connection.executemany(
        """
        INSERT INTO player_game_advanced_stats (
            game_id, player_id, usage_percentage, estimated_usage_percentage,
            true_shooting_percentage, effective_field_goal_percentage, pace,
            possessions, pie, source
        )
        VALUES (
            :game_id, :player_id, :usage_percentage, :estimated_usage_percentage,
            :true_shooting_percentage, :effective_field_goal_percentage, :pace,
            :possessions, :pie, :source
        )
        ON CONFLICT(game_id, player_id) DO UPDATE SET
            usage_percentage = excluded.usage_percentage,
            estimated_usage_percentage = excluded.estimated_usage_percentage,
            true_shooting_percentage = excluded.true_shooting_percentage,
            effective_field_goal_percentage = excluded.effective_field_goal_percentage,
            pace = excluded.pace,
            possessions = excluded.possessions,
            pie = excluded.pie,
            source = excluded.source
        """,
        [asdict(row) for row in stats_rows],
    )
