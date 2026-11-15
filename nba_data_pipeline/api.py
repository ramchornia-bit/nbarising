from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analysis import player_recent_summary, ranked_players, trending_players
from .storage import connect, init_db


class NbaFantasyApiHandler(BaseHTTPRequestHandler):
    db_path: Path

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            connection = connect(self.db_path)
            init_db(connection)
            if parsed.path == "/health":
                self._json({"ok": True})
                return
            if parsed.path == "/players/trending":
                limit = int(query.get("limit", ["20"])[0])
                window = int(query.get("window", ["5"])[0])
                self._json({"players": trending_players(connection, window, limit)})
                return
            if parsed.path == "/players/rankings":
                limit = int(query.get("limit", ["20"])[0])
                window = int(query.get("window", ["5"])[0])
                direction = query.get("direction", ["up"])[0]
                include_obvious = query.get("includeObvious", ["false"])[0].lower() == "true"
                self._json(
                    {
                        "direction": direction,
                        "players": ranked_players(
                            connection, direction, window, limit, include_obvious
                        ),
                    }
                )
                return
            if parsed.path.startswith("/players/") and parsed.path.endswith("/summary"):
                player_id_text = parsed.path.split("/")[2]
                window = int(query.get("window", ["5"])[0])
                self._json(player_recent_summary(connection, int(player_id_text), window))
                return
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except (sqlite3.Error, ValueError, IndexError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        return


def run_server(db_path: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(NbaFantasyApiHandler):
        pass

    Handler.db_path = db_path
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving NBA fantasy API on http://{host}:{port}")
    server.serve_forever()
