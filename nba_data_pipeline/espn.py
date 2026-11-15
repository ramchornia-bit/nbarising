"""ESPN public NBA feed: provider, normalizer and ingestion.

Verified fields (probe on game 401810011): MIN, PTS, FG, 3PT, FT, REB, AST, TO, STL, BLK,
OREB, DREB, PF, +/-, plus per-player `starter`, `didNotPlay`, `active`.
Not provided: usage rate, NBA fantasy points (analysis computes fantasy points itself),
minutes are whole minutes only (no seconds).

IDs are ESPN IDs (players, teams) and the ESPN event id (games). Do not mix this
source with NBA-id data in the same database; use a dedicated DB file.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

from .models import Game, Player, PlayerGameStat, Team
from .normalizers import season_from_game_date
from .storage import save_boxscore

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
SOURCE = "espn_summary"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class EspnProvider:
    def __init__(self, pause_seconds: float = 0.3, retries: int = 3) -> None:
        self.pause_seconds = pause_seconds
        self.retries = retries

    def _get(self, url: str) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                request = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                time.sleep(self.pause_seconds)
                return payload
            except (urllib.error.URLError, TimeoutError) as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"ESPN request failed after {self.retries} tries: {url}: {last!r}")

    def scoreboard(self, day: date) -> dict[str, Any]:
        return self._get(f"{BASE}/scoreboard?dates={day:%Y%m%d}")

    def summary(self, event_id: str) -> dict[str, Any]:
        return self._get(f"{BASE}/summary?event={event_id}")


def _int(text: Any) -> int | None:
    try:
        return int(round(float(str(text).replace("+", ""))))
    except (TypeError, ValueError):
        return None


def _made_attempted(text: Any) -> tuple[int | None, int | None]:
    parts = str(text or "").split("-")
    if len(parts) != 2:
        return None, None
    return _int(parts[0]), _int(parts[1])


def _team(raw: dict[str, Any]) -> Team:
    return Team(
        team_id=int(raw["id"]),
        abbreviation=str(raw.get("abbreviation") or raw["id"]),
        name=str(raw.get("name") or raw.get("displayName") or raw.get("abbreviation")),
        city=raw.get("location"),
    )


def normalize_espn_game(
    event: dict[str, Any], summary: dict[str, Any], game_date: str
) -> tuple[list[Team], list[Player], Game, list[PlayerGameStat]]:
    """`event` is one scoreboard event; `game_date` is the requested scoreboard day (YYYY-MM-DD).

    The scoreboard day is used (not the event's UTC timestamp) so late games stay on their US date.
    """
    competition = event["competitions"][0]
    competitors = {c["homeAway"]: c for c in competition["competitors"]}
    home, away = competitors["home"], competitors["away"]
    teams = {int(c["team"]["id"]): _team(c["team"]) for c in (home, away)}
    home_id, away_id = int(home["team"]["id"]), int(away["team"]["id"])
    status = event.get("status", {}).get("type", {}).get("description")
    game = Game(
        game_id=str(event["id"]),
        season=season_from_game_date(game_date),
        game_date=game_date,
        status=status,
        home_team_id=home_id,
        away_team_id=away_id,
        home_score=_int(home.get("score")),
        away_score=_int(away.get("score")),
    )

    players: dict[int, Player] = {}
    rows: list[PlayerGameStat] = []
    for group in summary.get("boxscore", {}).get("players", []):
        team_id = int(group["team"]["id"])
        opponent_id = away_id if team_id == home_id else home_id
        for block in group.get("statistics", []):
            labels = block.get("labels", [])
            for entry in block.get("athletes", []):
                athlete = entry.get("athlete", {})
                if "id" not in athlete:
                    continue
                player_id = int(athlete["id"])
                stats = dict(zip(labels, entry.get("stats", [])))
                minutes = _int(stats.get("MIN"))
                played = (not entry.get("didNotPlay", False)) and bool(minutes)
                players[player_id] = Player(
                    player_id=player_id,
                    full_name=str(athlete.get("displayName") or athlete.get("shortName") or player_id),
                    current_team_id=team_id,
                    active=entry.get("active"),
                )
                if not played:
                    rows.append(
                        PlayerGameStat(
                            game_id=game.game_id, player_id=player_id, team_id=team_id,
                            opponent_team_id=opponent_id, game_date=game_date,
                            started=bool(entry.get("starter")), played=False,
                            minutes_seconds=0, points=0, rebounds=0, offensive_rebounds=0,
                            defensive_rebounds=0, assists=0, steals=0, blocks=0, turnovers=0,
                            personal_fouls=0, plus_minus=None, fgm=0, fga=0, fg3m=0, fg3a=0,
                            ftm=0, fta=0, nba_fantasy_points=None, source=SOURCE,
                        )
                    )
                    continue
                fgm, fga = _made_attempted(stats.get("FG"))
                fg3m, fg3a = _made_attempted(stats.get("3PT"))
                ftm, fta = _made_attempted(stats.get("FT"))
                plus_minus = _int(stats.get("+/-"))
                rows.append(
                    PlayerGameStat(
                        game_id=game.game_id, player_id=player_id, team_id=team_id,
                        opponent_team_id=opponent_id, game_date=game_date,
                        started=bool(entry.get("starter")), played=True,
                        minutes_seconds=(minutes or 0) * 60,
                        points=_int(stats.get("PTS")), rebounds=_int(stats.get("REB")),
                        offensive_rebounds=_int(stats.get("OREB")),
                        defensive_rebounds=_int(stats.get("DREB")),
                        assists=_int(stats.get("AST")), steals=_int(stats.get("STL")),
                        blocks=_int(stats.get("BLK")), turnovers=_int(stats.get("TO")),
                        personal_fouls=_int(stats.get("PF")),
                        plus_minus=None if plus_minus is None else float(plus_minus),
                        fgm=fgm, fga=fga, fg3m=fg3m, fg3a=fg3a, ftm=ftm, fta=fta,
                        nba_fantasy_points=None, source=SOURCE,
                    )
                )
    return list(teams.values()), list(players.values()), game, rows


def _already_ingested(connection: sqlite3.Connection, game_id: str) -> bool:
    row = connection.execute(
        "SELECT COUNT(*) FROM player_game_stats WHERE game_id = ?", (game_id,)
    ).fetchone()
    return bool(row and row[0])


def ingest_espn_day(
    connection: sqlite3.Connection,
    day: date,
    provider: EspnProvider | None = None,
    force: bool = False,
) -> dict[str, Any]:
    provider = provider or EspnProvider()
    board = provider.scoreboard(day)
    stored = skipped = pending = 0
    for event in board.get("events", []):
        if not event.get("status", {}).get("type", {}).get("completed"):
            pending += 1
            continue
        if not force and _already_ingested(connection, str(event["id"])):
            skipped += 1
            continue
        summary = provider.summary(str(event["id"]))
        teams, players, game, rows = normalize_espn_game(event, summary, f"{day:%Y-%m-%d}")
        save_boxscore(connection, teams, players, game, rows)
        stored += 1
    return {"date": f"{day:%Y-%m-%d}", "stored": stored, "alreadyHad": skipped, "notFinished": pending}


def backfill_espn(
    connection: sqlite3.Connection,
    date_from: date,
    date_to: date,
    provider: EspnProvider | None = None,
    force: bool = False,
    progress: bool = True,
) -> dict[str, Any]:
    provider = provider or EspnProvider()
    totals = {"days": 0, "stored": 0, "alreadyHad": 0, "notFinished": 0}
    errors: list[str] = []
    day = date_from
    while day <= date_to:
        try:
            result = ingest_espn_day(connection, day, provider, force)
            totals["days"] += 1
            for key in ("stored", "alreadyHad", "notFinished"):
                totals[key] += result[key]
            if progress:
                print(f"{result['date']}: +{result['stored']} games "
                      f"(had {result['alreadyHad']})", flush=True)
        except Exception as exc:  # keep going; failed days are reported and can be re-run
            errors.append(f"{day:%Y-%m-%d}: {exc!r}")
            if progress:
                print(f"{day:%Y-%m-%d}: ERROR {exc!r}", flush=True)
        day += timedelta(days=1)
    return {"dateFrom": f"{date_from:%Y-%m-%d}", "dateTo": f"{date_to:%Y-%m-%d}", **totals, "errors": errors}


def parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()
