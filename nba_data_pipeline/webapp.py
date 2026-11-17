"""Court Signal web service (standard library only, no installs).

Run:  python -m nba_data_pipeline.cli serve-web --db nba_fantasy_espn.sqlite --port 8000

All routes are under /api/v1 and return JSON. Mobile apps and web pages call these.
  GET  /health
  GET  /status
  GET  /lists/{sustained|hot|drop}   ?format=points|categories &limit &all=1 &pool_cutoff &min_games
                                      &window=sustained|hot (drop only) &max_top_tier &drop_protect_rank
                                      &drop_max_baseline_rank &min_recent_minutes &include_settings=1
  POST /lists/{name}                 JSON body = any settings (see settings.example.json); optional
                                      "limit", "all", "window" keys
  GET  /players?q=name               search (max 20)
  GET  /players/{id}/form?games=10   game-by-game values and stat lines for charts
  GET  /injuries                     newest injury snapshot
  GET  /settings/defaults            default settings
Optional protection: set env COURT_SIGNAL_API_KEY; clients then send header X-API-Key.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .config import Settings, load_settings, settings_as_dict, settings_from_dict
from .engine import _regular_season_filter, load_histories, waiver_list
from .injuries import describe, ensure_schema, latest_injury_flags
from .names import normalize_name

PREFIX = "/api/v1"
LIST_NAMES = {"sustained", "hot", "drop"}
CACHE_SECONDS = 120
MAX_BODY = 64 * 1024

# query-string name -> (settings field, parser)
_TRUE = {"1", "true", "yes", "on"}
QUERY_SETTINGS = {
    "format": ("league_format", str),
    "pool_cutoff": ("pool_cutoff", int),
    "pool_max_rank": ("pool_max_rank", int),
    "absence_cap_games": ("absence_cap_games", int),
    "min_production_percentile": ("min_production_percentile", float),
    "min_games": ("min_games", int),
    "min_recent_minutes": ("min_recent_minutes", float),
    "max_top_tier": ("max_top_tier", int),
    "drop_protect_rank": ("drop_protect_rank", int),
    "drop_max_baseline_rank": ("drop_max_baseline_rank", int),
    "min_baseline_minutes": ("min_baseline_minutes", float),
}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int(value: str, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except ValueError:
        raise ApiError(400, f"{name} must be a whole number")
    if not low <= number <= high:
        raise ApiError(400, f"{name} must be between {low} and {high}")
    return number


class Service:
    """Framework-free core: handle() maps (method, path, query, body) to (status, json)."""

    def __init__(self, db_path: str | Path, base_settings: Settings | None = None,
                 api_key: str | None = None, cache_seconds: int = CACHE_SECONDS) -> None:
        self.db_path = Path(db_path)
        self.base = base_settings or load_settings()
        self.api_key = api_key if api_key is not None else os.environ.get("COURT_SIGNAL_API_KEY") or None
        self.cache_seconds = cache_seconds
        self.web_dir: Path | None = None      # folder with the built Flutter web app, served at /app/
        self._cache: dict[str, tuple[float, float, Any]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ plumbing
    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise ApiError(503, "database not found; run backfill-espn first")
        connection = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _db_stamp(self) -> float:
        stamp = 0.0
        for suffix in ("", "-wal"):
            try:
                stamp = max(stamp, os.stat(str(self.db_path) + suffix).st_mtime)
            except OSError:
                pass
        return stamp

    def _cached(self, key: str, compute, ttl: int | None = None):
        stamp, now = self._db_stamp(), time.time()
        limit_seconds = self.cache_seconds if ttl is None or self.cache_seconds == 0 else ttl
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == stamp and now - hit[1] < limit_seconds:
                return hit[2]
        value = compute()
        with self._lock:
            if len(self._cache) > 200:
                self._cache.clear()
            self._cache[key] = (stamp, now, value)
        return value

    def _data_through(self, connection: sqlite3.Connection) -> str | None:
        return connection.execute("SELECT MAX(game_date) FROM games").fetchone()[0]

    # ------------------------------------------------------------ dispatch
    def handle(self, method: str, path: str, query: dict[str, list[str]] | None = None,
               body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, Any]:
        query = query or {}
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            route = path.rstrip("/") or "/"
            if route == "/":
                return 200, {"name": "Court Signal API", "health": PREFIX + "/health", "status": PREFIX + "/status",
                             "lists": [f"{PREFIX}/lists/{n}" for n in sorted(LIST_NAMES)]}
            if route == PREFIX + "/health":
                return 200, {"ok": True, "time": _now()}
            if self.api_key and headers.get("x-api-key") != self.api_key:
                raise ApiError(401, "missing or wrong X-API-Key")
            if not route.startswith(PREFIX + "/"):
                raise ApiError(404, "not found")
            parts = route[len(PREFIX) + 1:].split("/")
            q = {k: v[-1] for k, v in query.items()}

            if method == "GET" and parts == ["status"]:
                return 200, self._status()
            if method == "GET" and parts == ["settings", "defaults"]:
                return 200, settings_as_dict(self.base)
            if parts[0] == "lists" and len(parts) == 2:
                if method == "GET":
                    return 200, self._list(parts[1], q, None)
                if method == "POST":
                    return 200, self._list(parts[1], q, self._json_body(body))
                raise ApiError(405, "use GET or POST")
            if parts == ["backtest"] and method in ("GET", "POST"):
                return 200, self._backtest(q, self._json_body(body) if method == "POST" else None)
            if parts == ["watchlist"] and method == "POST":
                return 200, self._watchlist(q, self._json_body(body))
            if method == "GET" and parts == ["players"]:
                return 200, self._search(q.get("q", ""))
            if method == "GET" and len(parts) == 3 and parts[0] == "players" and parts[2] == "form":
                return 200, self._form(_int(parts[1], "player id", 1, 10**12), q)
            if method == "GET" and parts == ["injuries"]:
                return 200, self._injuries()
            raise ApiError(404, "not found")
        except ApiError as error:
            return error.status, {"error": error.message}
        except ValueError as error:                      # settings validation
            return 422, {"error": str(error)}
        except sqlite3.Error as error:
            return 503, {"error": f"database error: {error}"}

    @staticmethod
    def _json_body(body: bytes | None) -> dict[str, Any]:
        if not body:
            return {}
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "body must be JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data

    # ------------------------------------------------------------ endpoints
    def _status(self) -> dict[str, Any]:
        def compute():
            with self._connect() as c:
                ensure_ro = c.execute(
                    "SELECT name FROM sqlite_master WHERE name='player_injury_snapshots'").fetchone()
                inj = c.execute("SELECT MAX(snapshot_date) FROM player_injury_snapshots").fetchone()[0] if ensure_ro else None
                through = self._data_through(c)
                age = (datetime.now(timezone.utc).date() - datetime.strptime(through, "%Y-%m-%d").date()).days if through else None
                return {
                    "dataThrough": through,
                    "dataAgeDays": age,
                    "games": c.execute("SELECT COUNT(*) FROM games").fetchone()[0],
                    "players": c.execute("SELECT COUNT(*) FROM players").fetchone()[0],
                    "playerGameRows": c.execute(
                        "SELECT COUNT(*) FROM player_game_stats WHERE COALESCE(played,1)=1").fetchone()[0],
                    "injurySnapshotDate": inj,
                    "generatedAt": _now(),
                }
        return self._cached("status", compute)

    def _settings_from(self, q: dict[str, str], body: dict[str, Any] | None) -> tuple[Settings, dict[str, Any]]:
        values = {f: v for f, v in settings_as_dict(self.base).items()}
        extras: dict[str, Any] = {}
        if body is not None:
            extras = {k: body[k] for k in ("limit", "all", "window", "include_settings", "ids", "forward", "step")
                      if k in body}
            values.update({k: v for k, v in body.items() if k not in extras})
        for key, (field, cast) in QUERY_SETTINGS.items():
            if key in q:
                try:
                    values[field] = cast(q[key])
                except ValueError:
                    raise ApiError(400, f"{key} has the wrong type")
        return settings_from_dict(values), extras

    def _list(self, name: str, q: dict[str, str], body: dict[str, Any] | None) -> dict[str, Any]:
        if name not in LIST_NAMES:
            raise ApiError(404, "list must be sustained, hot or drop")
        settings, extras = self._settings_from(q, body)
        limit = extras.get("limit", q.get("limit", 20))
        limit = _int(str(limit), "limit", 1, 200)
        show_all = str(extras.get("all", q.get("all", ""))).lower() in _TRUE
        window = str(extras.get("window", q.get("window", "sustained")))
        if window not in {"sustained", "hot"}:
            raise ApiError(400, "window must be sustained or hot")
        include = str(extras.get("include_settings", q.get("include_settings", ""))).lower() in _TRUE

        key = json.dumps([name, window, limit, show_all, include, settings_as_dict(settings)], sort_keys=True)

        def compute():
            with self._connect() as c:
                result = waiver_list(c, settings, list_name=name, window=window, limit=limit, show_all=show_all)
                result["dataThrough"] = self._data_through(c)
            result["generatedAt"] = _now()
            if not include:
                result.pop("settings", None)
            return result
        return self._cached(key, compute)

    def _backtest(self, q: dict[str, str], body: dict[str, Any] | None) -> dict[str, Any]:
        from .backtest import run_backtest
        settings, extras = self._settings_from(q, body)
        forward = _int(str(extras.get("forward", q.get("forward", 5))), "forward", 2, 10)
        step = _int(str(extras.get("step", q.get("step", 3))), "step", 1, 10)
        key = json.dumps(["backtest", forward, step, settings_as_dict(settings)], sort_keys=True)

        def compute():
            with self._connect() as c:
                result = run_backtest(c, settings, forward_games=forward, step_dates=step)
                result["dataThrough"] = self._data_through(c)
            result["generatedAt"] = _now()
            return result
        return self._cached(key, compute, ttl=3600)

    def _watchlist(self, q: dict[str, str], body: dict[str, Any] | None) -> dict[str, Any]:
        settings, extras = self._settings_from(q, body)
        raw = extras.get("ids")
        if not isinstance(raw, list) or not raw:
            return {"players": [], "dataThrough": None, "generatedAt": _now()}
        if len(raw) > 60:
            raise ApiError(400, "at most 60 players")
        try:
            ids = [int(i) for i in raw]
        except (TypeError, ValueError):
            raise ApiError(400, "ids must be whole numbers")
        key = json.dumps(["watch", sorted(ids), settings_as_dict(settings)], sort_keys=True)

        def compute():
            with self._connect() as c:
                histories, _ = load_histories(c, settings)
                eligible = [pid for pid, h in histories.items() if len(h.games) >= settings.min_games]
                season = {pid: sum(g.value for g in histories[pid].games) / len(histories[pid].games)
                          for pid in eligible}
                rank = {pid: i + 1 for i, pid in enumerate(sorted(eligible, key=lambda p: season[p], reverse=True))}
                scored: dict[str, dict[int, dict[str, Any]]] = {}
                for list_name in ("sustained", "hot"):
                    listing = waiver_list(c, settings, list_name, show_all=True, limit=100000)
                    scored[list_name] = {p["playerId"]: p for p in listing["players"]}
                flags = latest_injury_flags(c, settings)
                names = {r["player_id"]: r["full_name"] for r in c.execute(
                    "SELECT player_id, full_name FROM players WHERE player_id IN (%s)" % ",".join("?" * len(ids)), ids)}
                out = []
                for pid in ids:
                    history = histories.get(pid)
                    if history is None:
                        out.append({"playerId": pid, "name": names.get(pid, "Unknown"), "team": "",
                                    "gamesPlayed": 0, "flags": [flags[pid]] if pid in flags else []})
                        continue
                    values = [g.value for g in history.games]
                    mins = [g.minutes for g in history.games]
                    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
                    entry: dict[str, Any] = {
                        "playerId": pid, "name": history.name, "team": history.team,
                        "gamesPlayed": len(values),
                        "seasonRank": rank.get(pid), "seasonAverage": avg(values),
                        "last3Average": avg(values[-3:]), "last5Average": avg(values[-5:]),
                        "minutesRecent": avg(mins[-5:]), "minutesSeason": avg(mins),
                        "recentValues": [round(v, 1) for v in values[-8:]],
                        "flags": [],
                    }
                    for list_name in ("sustained", "hot"):
                        item = scored[list_name].get(pid)
                        if item:
                            entry[list_name] = {"score": item["score"], "label": item["label"],
                                                "reason": item["reason"]}
                    if pid in flags:
                        entry["flags"].append(flags[pid])
                    out.append(entry)
                return {"players": out, "dataThrough": self._data_through(c), "generatedAt": _now()}
        return self._cached(key, compute)

    def _search(self, text: str) -> dict[str, Any]:
        needle = normalize_name(text)
        if len(needle) < 2:
            raise ApiError(400, "q needs at least 2 characters")
        with self._connect() as c:
            rows = c.execute(
                """SELECT p.player_id, p.full_name, COALESCE(t.abbreviation,'') AS team
                   FROM players p LEFT JOIN teams t ON t.team_id = p.current_team_id""").fetchall()
        hits = [r for r in rows if needle in normalize_name(r["full_name"])]
        hits.sort(key=lambda r: (not normalize_name(r["full_name"]).startswith(needle), r["full_name"]))
        return {"players": [{"playerId": r["player_id"], "name": r["full_name"], "team": r["team"]}
                            for r in hits[:20]]}

    def _form(self, player_id: int, q: dict[str, str]) -> dict[str, Any]:
        games_n = _int(q.get("games", "10"), "games", 1, 82)
        values = settings_as_dict(self.base)
        if "format" in q:
            values["league_format"] = q["format"]
        if q.get("points_weights"):
            try:
                weights = json.loads(q["points_weights"])
            except json.JSONDecodeError:
                raise ApiError(400, "points_weights must be JSON")
            if not isinstance(weights, dict):
                raise ApiError(400, "points_weights must be a JSON object")
            values["points_weights"] = weights
        if q.get("categories"):
            values["categories"] = [c for c in q["categories"].split(",") if c]
        settings = settings_from_dict(values)
        key = json.dumps(["form", player_id, games_n, settings_as_dict(settings)], sort_keys=True)

        def compute():
            with self._connect() as c:
                histories, _ = load_histories(c, settings)
                history = histories.get(player_id)
                if history is None:
                    raise ApiError(404, "no games for that player")
                lines = c.execute(
                    """SELECT s.game_id, s.game_date, s.points, s.rebounds, s.assists, s.steals, s.blocks,
                              s.turnovers, s.fgm, s.fga, s.fg3m, s.fg3a, s.ftm, s.fta,
                              COALESCE(o.abbreviation,'') AS opponent
                       FROM player_game_stats s LEFT JOIN teams o ON o.team_id = s.opponent_team_id
                       LEFT JOIN games g ON g.game_id = s.game_id
                       WHERE s.player_id = ? AND COALESCE(s.played,1)=1 AND COALESCE(s.minutes_seconds,0) > 0"""
                    + _regular_season_filter(c, "g") +
                    " ORDER BY s.game_date, s.game_id", (player_id,)).fetchall()
                games = history.games
                if len(lines) != len(games):
                    raise ApiError(503, "data changed while reading; retry")
                out = []
                for game, line in list(zip(games, lines))[-games_n:]:
                    out.append({
                        "date": game.date, "opponent": line["opponent"], "value": round(game.value, 2),
                        "minutes": round(game.minutes, 1), "started": game.started,
                        "points": line["points"], "rebounds": line["rebounds"], "assists": line["assists"],
                        "steals": line["steals"], "blocks": line["blocks"], "turnovers": line["turnovers"],
                        "fg": f"{line['fgm']}/{line['fga']}", "fg3": f"{line['fg3m']}/{line['fg3a']}",
                        "ft": f"{line['ftm']}/{line['fta']}",
                    })
                avg = sum(g.value for g in games) / len(games)
                return {
                    "playerId": player_id, "name": history.name, "team": history.team,
                    "format": settings.league_format, "seasonGames": len(games),
                    "seasonAverage": round(avg, 2), "games": out,
                    "dataThrough": self._data_through(c), "generatedAt": _now(),
                }
        return self._cached(key, compute)

    def _injuries(self) -> dict[str, Any]:
        def compute():
            with self._connect() as c:
                if not c.execute("SELECT 1 FROM sqlite_master WHERE name='player_injury_snapshots'").fetchone():
                    return {"snapshotDate": None, "injuries": []}
                newest = c.execute("SELECT MAX(snapshot_date) FROM player_injury_snapshots").fetchone()[0]
                if not newest:
                    return {"snapshotDate": None, "injuries": []}
                today = datetime.strptime(newest, "%Y-%m-%d").date()
                rows = c.execute(
                    "SELECT * FROM player_injury_snapshots WHERE snapshot_date = ? ORDER BY team_abbr, athlete_name",
                    (newest,)).fetchall()
                return {
                    "snapshotDate": newest,
                    "injuries": [{
                        "name": r["athlete_name"], "team": r["team_abbr"], "playerId": r["player_id"],
                        "level": r["severity"], "status": r["status"], "returnDate": r["return_date"],
                        "text": describe(r, today),
                    } for r in rows],
                }
        return self._cached("injuries", compute)


# ---------------------------------------------------------------- HTTP wrapper

def make_handler(service: Service, cors_origin: str = "*"):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CourtSignal/1.0"

        def _send(self, status: int, payload: Any) -> None:
            data = b"" if status == 204 else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            if self.command != "HEAD" and data:
                self.wfile.write(data)

        def _static(self, path: str) -> bool:
            """Serve the Flutter web build under /app/. Returns True when the request was handled."""
            root = service.web_dir
            if root is None or not (root / "index.html").exists():
                return False
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/app/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            if path == "/app":
                self.send_response(301)
                self.send_header("Location", "/app/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            if not path.startswith("/app/"):
                return False
            base = root.resolve()
            target = (base / (unquote(path[5:]) or "index.html")).resolve()
            if target != base and base not in target.parents:
                self._send(404, {"error": "not found"})
                return True
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                target = base / "index.html"           # unknown page: let the app handle it
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".wasm":
                kind = "application/wasm"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") or kind in ("application/javascript", "text/javascript", "application/json") else ""))
            self.send_header("Content-Length", str(len(data)))
            volatile = target.name in ("index.html", "flutter_service_worker.js", "flutter_bootstrap.js", "version.json", "manifest.json")
            self.send_header("Cache-Control", "no-cache" if volatile else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return True

        def _run(self, method: str) -> None:
            parsed = urlparse(self.path)
            if method == "GET" and self._static(parsed.path):
                return
            body = None
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._send(413, {"error": "body too large"})
                body = self.rfile.read(length) if length else b""
            try:
                status, payload = service.handle(
                    method, parsed.path, parse_qs(parsed.query), body, dict(self.headers.items()))
            except Exception as error:  # last resort: never leak a stack trace to clients
                status, payload = 500, {"error": "internal error", "detail": type(error).__name__}
            self._send(status, payload)

        def do_GET(self) -> None:
            self._run("GET")

        def do_POST(self) -> None:
            self._run("POST")

        def do_OPTIONS(self) -> None:
            self._send(204, {})

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}")

    return Handler


def run_web(db_path: str | Path, host: str = "127.0.0.1", port: int = 8000,
            auto_update_hours: float = 0, bootstrap_from: str | None = None) -> None:
    service = Service(db_path)
    service.web_dir = Path(db_path).parent / "web"
    from .snapshot import config_from_env, start_snapshot_refresh
    snapshot = config_from_env()
    if snapshot:
        start_snapshot_refresh(Path(db_path), snapshot, float(os.environ.get("SNAPSHOT_REFRESH_HOURS", "3")),
                               web_dir=service.web_dir)
    elif auto_update_hours > 0:
        from datetime import date as _date
        from .scheduler import start_background_updates
        start_background_updates(
            Path(db_path), auto_update_hours,
            bootstrap_from=_date.fromisoformat(bootstrap_from) if bootstrap_from else None)
    server = ThreadingHTTPServer((host, port), make_handler(service))
    guard = "API key required" if service.api_key else "no API key set"
    print(f"Court Signal API on http://{host}:{port}{PREFIX}/status  ({guard}). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
