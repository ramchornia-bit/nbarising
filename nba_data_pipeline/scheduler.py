"""Background updater for the hosted service: first-run backfill, then recent games + injuries on a timer."""
from __future__ import annotations

import threading
import time
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .espn import backfill_espn, backfill_season_types
from .injuries import update_injuries
from .storage import connect, init_db


def run_update(db_path: Path, settings: Settings, days: int = 3, bootstrap_from: date | None = None) -> dict[str, Any]:
    connection = connect(db_path)
    try:
        init_db(connection)
        yesterday = date.today() - timedelta(days=1)
        have = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        start = bootstrap_from if (have == 0 and bootstrap_from) else yesterday - timedelta(days=days - 1)
        games = backfill_espn(connection, start, yesterday)
        season_types = backfill_season_types(connection)
        injuries = update_injuries(connection, settings)
        return {"from": start.isoformat(), "to": yesterday.isoformat(), "games": games, "seasonTypes": season_types, "injuries": injuries}
    finally:
        connection.close()


def start_background_updates(db_path: Path, hours: float = 6.0, days: int = 3,
                             bootstrap_from: date | None = None, settings: Settings | None = None) -> threading.Thread:
    settings = settings or load_settings()
    connection = connect(db_path)          # make sure the file exists before the API opens it read-only
    init_db(connection)
    connection.close()

    def loop() -> None:
        while True:
            try:
                print("[update] start", flush=True)
                print("[update] done", run_update(db_path, settings, days, bootstrap_from), flush=True)
            except Exception:
                traceback.print_exc()
            time.sleep(max(hours, 0.05) * 3600)

    thread = threading.Thread(target=loop, name="court-signal-updater", daemon=True)
    thread.start()
    return thread
