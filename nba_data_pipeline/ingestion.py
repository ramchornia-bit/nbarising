from __future__ import annotations

import sqlite3
from typing import Any

from .normalizers import normalize_boxscore_advanced_v3, normalize_live_boxscore
from .normalizers import normalize_player_game_logs
from .providers import NbaLiveProvider, NbaStatsProvider
from .storage import save_boxscore, save_player_game_logs, upsert_player_game_advanced_stats


def game_ids_from_scoreboard(scoreboard_payload: dict[str, Any], completed_only: bool = True) -> list[str]:
    games = scoreboard_payload.get("scoreboard", {}).get("games", [])
    ids: list[str] = []
    for game in games:
        if completed_only and game.get("gameStatus") != 3:
            continue
        game_id = game.get("gameId")
        if game_id:
            ids.append(game_id)
    return ids


def ingest_live_boxscore_payload(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    teams, players, game, stats_rows = normalize_live_boxscore(payload)
    save_boxscore(connection, teams, players, game, stats_rows)
    return {
        "gameId": game.game_id,
        "teams": len(teams),
        "players": len(players),
        "playerGameStats": len(stats_rows),
    }


def ingest_todays_completed_games(
    connection: sqlite3.Connection,
    live_provider: NbaLiveProvider | None = None,
    stats_provider: NbaStatsProvider | None = None,
    include_advanced: bool = False,
) -> dict[str, Any]:
    live_provider = live_provider or NbaLiveProvider()
    stats_provider = stats_provider or NbaStatsProvider()
    scoreboard = live_provider.todays_scoreboard()
    game_ids = game_ids_from_scoreboard(scoreboard, completed_only=True)
    results = []
    advanced_rows = 0
    for game_id in game_ids:
        results.append(ingest_live_boxscore_payload(connection, live_provider.boxscore(game_id)))
        if include_advanced:
            advanced = normalize_boxscore_advanced_v3(stats_provider.boxscore_advanced_v3(game_id))
            with connection:
                upsert_player_game_advanced_stats(connection, advanced)
            advanced_rows += len(advanced)
    return {
        "scoreboardDate": scoreboard.get("scoreboard", {}).get("gameDate"),
        "completedGames": len(game_ids),
        "gameIds": game_ids,
        "boxscores": results,
        "advancedRows": advanced_rows,
    }


def ingest_player_game_logs_payload(
    connection: sqlite3.Connection, payload: dict[str, Any]
) -> dict[str, Any]:
    teams, players, games, stats_rows = normalize_player_game_logs(payload)
    save_player_game_logs(connection, teams, players, games, stats_rows)
    return {
        "teams": len(teams),
        "players": len(players),
        "games": len(games),
        "playerGameStats": len(stats_rows),
    }


def backfill_player_game_logs(
    connection: sqlite3.Connection,
    season: str,
    date_from: str = "",
    date_to: str = "",
    season_type: str = "Regular Season",
    stats_provider: NbaStatsProvider | None = None,
) -> dict[str, Any]:
    stats_provider = stats_provider or NbaStatsProvider()
    payload = stats_provider.player_game_logs(season, date_from, date_to, season_type)
    result = ingest_player_game_logs_payload(connection, payload)
    return {
        "season": season,
        "dateFrom": date_from,
        "dateTo": date_to,
        "seasonType": season_type,
        **result,
    }
