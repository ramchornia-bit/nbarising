from __future__ import annotations

import re
from typing import Any

from .models import Game, Player, PlayerGameAdvancedStat, PlayerGameStat, Team


ISO_MINUTES_RE = re.compile(r"^PT(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$")

NBA_TEAMS_BY_ABBREVIATION = {
    "ATL": (1610612737, "Hawks", "Atlanta"),
    "BOS": (1610612738, "Celtics", "Boston"),
    "BKN": (1610612751, "Nets", "Brooklyn"),
    "CHA": (1610612766, "Hornets", "Charlotte"),
    "CHI": (1610612741, "Bulls", "Chicago"),
    "CLE": (1610612739, "Cavaliers", "Cleveland"),
    "DAL": (1610612742, "Mavericks", "Dallas"),
    "DEN": (1610612743, "Nuggets", "Denver"),
    "DET": (1610612765, "Pistons", "Detroit"),
    "GSW": (1610612744, "Warriors", "Golden State"),
    "HOU": (1610612745, "Rockets", "Houston"),
    "IND": (1610612754, "Pacers", "Indiana"),
    "LAC": (1610612746, "Clippers", "LA"),
    "LAL": (1610612747, "Lakers", "Los Angeles"),
    "MEM": (1610612763, "Grizzlies", "Memphis"),
    "MIA": (1610612748, "Heat", "Miami"),
    "MIL": (1610612749, "Bucks", "Milwaukee"),
    "MIN": (1610612750, "Timberwolves", "Minnesota"),
    "NOP": (1610612740, "Pelicans", "New Orleans"),
    "NYK": (1610612752, "Knicks", "New York"),
    "OKC": (1610612760, "Thunder", "Oklahoma City"),
    "ORL": (1610612753, "Magic", "Orlando"),
    "PHI": (1610612755, "76ers", "Philadelphia"),
    "PHX": (1610612756, "Suns", "Phoenix"),
    "POR": (1610612757, "Trail Blazers", "Portland"),
    "SAC": (1610612758, "Kings", "Sacramento"),
    "SAS": (1610612759, "Spurs", "San Antonio"),
    "TOR": (1610612761, "Raptors", "Toronto"),
    "UTA": (1610612762, "Jazz", "Utah"),
    "WAS": (1610612764, "Wizards", "Washington"),
}


def parse_minutes_to_seconds(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value) * 60))
    text = str(value)
    match = ISO_MINUTES_RE.match(text)
    if match:
        minutes = int(match.group("minutes") or 0)
        seconds = float(match.group("seconds") or 0)
        return int(round(minutes * 60 + seconds))
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return int(minutes) * 60 + int(float(seconds))
    return int(round(float(text) * 60))


def season_from_game_date(game_date: str) -> str:
    year = int(game_date[:4])
    month = int(game_date[5:7])
    start_year = year if month >= 10 else year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _as_bool_flag(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).lower() in {"1", "true", "yes"}


def _stat(stats: dict[str, Any], key: str) -> Any:
    return stats.get(key)


def _team_from_abbreviation(abbreviation: str, fallback_id: int | None = None) -> Team:
    details = NBA_TEAMS_BY_ABBREVIATION.get(abbreviation)
    if details:
        team_id, name, city = details
        return Team(team_id, abbreviation, name, city)
    if fallback_id is not None:
        return Team(fallback_id, abbreviation, abbreviation, None)
    generated_id = -sum((index + 1) * ord(char) for index, char in enumerate(abbreviation))
    return Team(generated_id, abbreviation, abbreviation, None)


def _normalize_game_date(value: Any) -> str:
    text = str(value)
    if "-" in text and len(text) >= 10:
        return text[:10]
    month, day, year = text.split("/")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _parse_matchup(matchup: str, team_abbreviation: str) -> tuple[str, bool]:
    if " vs. " in matchup:
        return matchup.split(" vs. ", 1)[1], True
    if " @ " in matchup:
        return matchup.split(" @ ", 1)[1], False
    return team_abbreviation, True


def normalize_live_boxscore(payload: dict[str, Any]) -> tuple[list[Team], list[Player], Game, list[PlayerGameStat]]:
    game_payload = payload["game"]
    game_date = game_payload["gameTimeUTC"][:10]
    home = game_payload["homeTeam"]
    away = game_payload["awayTeam"]

    teams = [
        Team(home["teamId"], home["teamTricode"], home["teamName"], home.get("teamCity")),
        Team(away["teamId"], away["teamTricode"], away["teamName"], away.get("teamCity")),
    ]
    game = Game(
        game_id=game_payload["gameId"],
        season=season_from_game_date(game_date),
        game_date=game_date,
        status=game_payload.get("gameStatusText"),
        home_team_id=home["teamId"],
        away_team_id=away["teamId"],
        home_score=home.get("score"),
        away_score=away.get("score"),
    )

    players: list[Player] = []
    stats_rows: list[PlayerGameStat] = []
    for team_payload, opponent_payload in ((home, away), (away, home)):
        for player_payload in team_payload.get("players", []):
            stats = player_payload.get("statistics", {})
            player_id = int(player_payload["personId"])
            players.append(
                Player(
                    player_id=player_id,
                    full_name=player_payload.get("name") or "",
                    first_name=player_payload.get("firstName"),
                    last_name=player_payload.get("familyName"),
                    current_team_id=team_payload["teamId"],
                    active=player_payload.get("status") == "ACTIVE",
                )
            )
            stats_rows.append(
                PlayerGameStat(
                    game_id=game.game_id,
                    player_id=player_id,
                    team_id=team_payload["teamId"],
                    opponent_team_id=opponent_payload["teamId"],
                    game_date=game.game_date,
                    started=_as_bool_flag(player_payload.get("starter")),
                    played=_as_bool_flag(player_payload.get("played")),
                    minutes_seconds=parse_minutes_to_seconds(_stat(stats, "minutes")),
                    points=_stat(stats, "points"),
                    rebounds=_stat(stats, "reboundsTotal"),
                    offensive_rebounds=_stat(stats, "reboundsOffensive"),
                    defensive_rebounds=_stat(stats, "reboundsDefensive"),
                    assists=_stat(stats, "assists"),
                    steals=_stat(stats, "steals"),
                    blocks=_stat(stats, "blocks"),
                    turnovers=_stat(stats, "turnovers"),
                    personal_fouls=_stat(stats, "foulsPersonal"),
                    plus_minus=_stat(stats, "plusMinusPoints"),
                    fgm=_stat(stats, "fieldGoalsMade"),
                    fga=_stat(stats, "fieldGoalsAttempted"),
                    fg3m=_stat(stats, "threePointersMade"),
                    fg3a=_stat(stats, "threePointersAttempted"),
                    ftm=_stat(stats, "freeThrowsMade"),
                    fta=_stat(stats, "freeThrowsAttempted"),
                    nba_fantasy_points=None,
                    source="nba_live_boxscore",
                )
            )
    return teams, players, game, stats_rows


def normalize_boxscore_advanced_v3(payload: dict[str, Any]) -> list[PlayerGameAdvancedStat]:
    result_sets = payload.get("resultSets") or payload.get("result_sets") or []
    player_stats = None
    for result_set in result_sets:
        if result_set.get("name") in {"PlayerStats", "player_stats"}:
            player_stats = result_set
            break
    if player_stats is None and result_sets:
        player_stats = result_sets[0]
    if not player_stats:
        return []

    headers = player_stats.get("headers", [])
    rows = player_stats.get("rowSet", [])
    normalized: list[PlayerGameAdvancedStat] = []
    for row in rows:
        item = dict(zip(headers, row, strict=False))
        normalized.append(
            PlayerGameAdvancedStat(
                game_id=item["gameId"],
                player_id=int(item["personId"]),
                usage_percentage=item.get("usagePercentage"),
                estimated_usage_percentage=item.get("estimatedUsagePercentage"),
                true_shooting_percentage=item.get("trueShootingPercentage"),
                effective_field_goal_percentage=item.get("effectiveFieldGoalPercentage"),
                pace=item.get("pace"),
                possessions=item.get("possessions"),
                pie=item.get("PIE"),
                source="nba_stats_boxscoreadvancedv3",
            )
        )
    return normalized


def normalize_player_game_logs(
    payload: dict[str, Any],
) -> tuple[list[Team], list[Player], list[Game], list[PlayerGameStat]]:
    result_sets = payload.get("resultSets") or payload.get("result_sets") or []
    game_logs = None
    for result_set in result_sets:
        if result_set.get("name") in {"PlayerGameLogs", "player_game_logs"}:
            game_logs = result_set
            break
    if game_logs is None and result_sets:
        game_logs = result_sets[0]
    if not game_logs:
        return [], [], [], []

    headers = game_logs.get("headers", [])
    rows = game_logs.get("rowSet", [])
    teams_by_id: dict[int, Team] = {}
    players_by_id: dict[int, Player] = {}
    games_by_id: dict[str, Game] = {}
    stats_rows: list[PlayerGameStat] = []

    for row in rows:
        item = dict(zip(headers, row, strict=False))
        team_abbreviation = item["TEAM_ABBREVIATION"]
        team = _team_from_abbreviation(team_abbreviation, int(item["TEAM_ID"]))
        opponent_abbreviation, is_home = _parse_matchup(item.get("MATCHUP", ""), team_abbreviation)
        opponent = _team_from_abbreviation(opponent_abbreviation)
        teams_by_id[team.team_id] = team
        teams_by_id[opponent.team_id] = opponent

        player_id = int(item["PLAYER_ID"])
        full_name = item["PLAYER_NAME"]
        name_parts = full_name.split(" ", 1)
        players_by_id[player_id] = Player(
            player_id=player_id,
            full_name=full_name,
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else None,
            current_team_id=team.team_id,
            active=None,
        )

        game_date = _normalize_game_date(item["GAME_DATE"])
        home_team_id = team.team_id if is_home else opponent.team_id
        away_team_id = opponent.team_id if is_home else team.team_id
        games_by_id[item["GAME_ID"]] = Game(
            game_id=item["GAME_ID"],
            season=item.get("SEASON_YEAR") or season_from_game_date(game_date),
            game_date=game_date,
            status="Final",
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )

        stats_rows.append(
            PlayerGameStat(
                game_id=item["GAME_ID"],
                player_id=player_id,
                team_id=team.team_id,
                opponent_team_id=opponent.team_id,
                game_date=game_date,
                started=None,
                played=(item.get("MIN") is not None),
                minutes_seconds=parse_minutes_to_seconds(item.get("MIN")),
                points=item.get("PTS"),
                rebounds=item.get("REB"),
                offensive_rebounds=item.get("OREB"),
                defensive_rebounds=item.get("DREB"),
                assists=item.get("AST"),
                steals=item.get("STL"),
                blocks=item.get("BLK"),
                turnovers=item.get("TOV"),
                personal_fouls=item.get("PF"),
                plus_minus=item.get("PLUS_MINUS"),
                fgm=item.get("FGM"),
                fga=item.get("FGA"),
                fg3m=item.get("FG3M"),
                fg3a=item.get("FG3A"),
                ftm=item.get("FTM"),
                fta=item.get("FTA"),
                nba_fantasy_points=item.get("NBA_FANTASY_PTS"),
                source="nba_stats_playergamelogs",
            )
        )

    return list(teams_by_id.values()), list(players_by_id.values()), list(games_by_id.values()), stats_rows
