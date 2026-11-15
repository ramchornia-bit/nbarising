from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}


class JsonHttpClient:
    def get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class NbaLiveProvider:
    scoreboard_url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    boxscore_url = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"

    def __init__(self, client: JsonHttpClient | None = None) -> None:
        self.client = client or JsonHttpClient()

    def todays_scoreboard(self) -> dict[str, Any]:
        return self.client.get_json(self.scoreboard_url)

    def boxscore(self, game_id: str) -> dict[str, Any]:
        return self.client.get_json(self.boxscore_url.format(game_id=game_id))


class NbaStatsProvider:
    player_game_logs_url = "https://stats.nba.com/stats/playergamelogs"
    boxscore_advanced_v3_url = "https://stats.nba.com/stats/boxscoreadvancedv3"

    def __init__(self, client: JsonHttpClient | None = None) -> None:
        self.client = client or JsonHttpClient()

    def player_game_logs(
        self,
        season: str,
        date_from: str = "",
        date_to: str = "",
        season_type: str = "Regular Season",
    ) -> dict[str, Any]:
        return self.client.get_json(
            self.player_game_logs_url,
            {
                "DateFrom": date_from,
                "DateTo": date_to,
                "GameSegment": "",
                "LastNGames": "0",
                "LeagueID": "00",
                "Location": "",
                "MeasureType": "Base",
                "Month": "0",
                "OpposingTeamID": "0",
                "Outcome": "",
                "PORound": "0",
                "PerMode": "Totals",
                "Period": "0",
                "PlayerID": "",
                "Season": season,
                "SeasonSegment": "",
                "SeasonType": season_type,
                "ShotClockRange": "",
                "TeamID": "0",
                "VsConference": "",
                "VsDivision": "",
            },
        )

    def boxscore_advanced_v3(self, game_id: str) -> dict[str, Any]:
        return self.client.get_json(
            self.boxscore_advanced_v3_url,
            {
                "EndPeriod": "0",
                "EndRange": "0",
                "GameID": game_id,
                "RangeType": "0",
                "StartPeriod": "0",
                "StartRange": "0",
            },
        )
