"""Injury snapshots from ESPN's league-wide injury list.

What the probe showed (5 Nov 2026):
  * Endpoint  {BASE}/injuries : ~90 entries, grouped by team.
  * status is only "Out" or "Day-To-Day"; details give body part, side, a detail word
    (Surgery, Soreness, Bruise...) and an ESTIMATED returnDate.
  * It is a snapshot of TODAY. Even a game summary from 2025 returns today's injuries, so there is
    no history to backfill: we save one snapshot per day and build our own history.
  * Entries in the league list carry no obvious athlete id, so players are matched by id when one
    is present, else by (name, team), else by a unique name.

Severity levels (all limits are settings):
  day_to_day     status Day-To-Day
  out_short      Out, estimated return within injury_short_term_days
  out_long       Out, return further away
  season_ending  Out, comments say so, or return more than injury_season_ending_days away
  out_unknown    Out with no return date
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from typing import Any

from .config import Settings
from .espn import BASE, EspnProvider
from .names import NameIndex, normalize_name  # noqa: F401  (normalize_name re-exported)

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_injury_snapshots (
    snapshot_date TEXT NOT NULL,
    athlete_name TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    team_abbr TEXT,
    player_id INTEGER,
    status TEXT,
    severity TEXT,
    body_part TEXT,
    side TEXT,
    detail TEXT,
    return_date TEXT,
    short_comment TEXT,
    updated_at TEXT,
    PRIMARY KEY (snapshot_date, athlete_name, team_id)
);
CREATE INDEX IF NOT EXISTS idx_injury_player ON player_injury_snapshots (player_id, snapshot_date DESC);
"""

LABELS = {
    "day_to_day": "Day-to-day",
    "out_short": "Out (short term)",
    "out_long": "Out (long term)",
    "season_ending": "Out (likely season-ending)",
    "out_unknown": "Out (return date unknown)",
}
SEASON_TEXT = re.compile(
    r"season[- ]ending|out for (?:the )?(?:rest of the |remainder of the )?(?:season|year)|"
    r"(?:rest|remainder) of the (?:season|year)|miss(?:es)? the (?:rest of the )?season",
    re.I,
)
ATHLETE_ID_IN_LINK = re.compile(r"/id/(\d+)")


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def _return_date(text: Any) -> date | None:
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def classify(
    status: str, return_date: date | None, comments: str, today: date, settings: Settings
) -> str:
    if (status or "").lower().startswith("day"):
        return "day_to_day"
    if SEASON_TEXT.search(comments or ""):
        return "season_ending"
    if return_date is None:
        return "out_unknown"
    days = (return_date - today).days
    if days > settings.injury_season_ending_days:
        return "season_ending"
    if days > settings.injury_short_term_days:
        return "out_long"
    return "out_short"


def parse_entries(payload: dict[str, Any], today: date, settings: Settings) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for group in payload.get("injuries", []):
        for item in group.get("injuries", []):
            athlete = item.get("athlete") or {}
            team = athlete.get("team") or group.get("team") or {}
            if "id" not in team and group.get("id"):
                team = {**team, "id": group["id"]}
            name = athlete.get("displayName") or athlete.get("fullName")
            if not name or "id" not in team:
                continue
            athlete_id = athlete.get("id")
            if athlete_id is None:
                for link in athlete.get("links", []) or []:
                    found = ATHLETE_ID_IN_LINK.search(str(link.get("href", "")))
                    if found:
                        athlete_id = found.group(1)
                        break
            details = item.get("details") or {}
            comments = f"{item.get('shortComment') or ''} {item.get('longComment') or ''}"
            status = str(item.get("status") or (item.get("type") or {}).get("description") or "")
            ret = _return_date(details.get("returnDate"))
            entries.append({
                "athlete_name": name,
                "athlete_id": int(athlete_id) if athlete_id and str(athlete_id).isdigit() else None,
                "team_id": int(team["id"]),
                "team_abbr": team.get("abbreviation"),
                "status": status,
                "severity": classify(status, ret, comments, today, settings),
                "body_part": details.get("type"),
                "side": details.get("side"),
                "detail": details.get("detail"),
                "return_date": ret.isoformat() if ret else None,
                "short_comment": (item.get("shortComment") or "")[:300],
                "updated_at": item.get("date"),
            })
    return entries


def _match_players(connection: sqlite3.Connection, entries: list[dict[str, Any]]) -> None:
    index = NameIndex(connection)
    for entry in entries:
        if entry["athlete_id"] in index.names:
            entry["player_id"] = entry["athlete_id"]
        else:
            entry["player_id"] = index.resolve(entry["athlete_name"], entry["team_id"]).player_id


def update_injuries(
    connection: sqlite3.Connection,
    settings: Settings,
    provider: EspnProvider | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    ensure_schema(connection)
    provider = provider or EspnProvider()
    today = today or date.today()
    payload = provider._get(f"{BASE}/injuries")
    entries = parse_entries(payload, today, settings)
    _match_players(connection, entries)
    with connection:
        connection.execute("DELETE FROM player_injury_snapshots WHERE snapshot_date = ?", (today.isoformat(),))
        connection.executemany(
            """
            INSERT OR REPLACE INTO player_injury_snapshots
              (snapshot_date, athlete_name, team_id, team_abbr, player_id, status, severity,
               body_part, side, detail, return_date, short_comment, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (today.isoformat(), e["athlete_name"], e["team_id"], e["team_abbr"], e["player_id"],
                 e["status"], e["severity"], e["body_part"], e["side"], e["detail"], e["return_date"],
                 e["short_comment"], e["updated_at"])
                for e in entries
            ],
        )
    severities: dict[str, int] = {}
    for e in entries:
        severities[e["severity"]] = severities.get(e["severity"], 0) + 1
    unmatched = sorted(e["athlete_name"] for e in entries if e["player_id"] is None)
    return {
        "snapshotDate": today.isoformat(),
        "entries": len(entries),
        "matchedToPlayersInDb": len(entries) - len(unmatched),
        "notInDb": len(unmatched),
        "notInDbExamples": unmatched[:12],
        "bySeverity": severities,
    }


def describe(row: sqlite3.Row, today: date) -> str:
    label = LABELS.get(row["severity"], row["status"] or "Injured")
    what = " ".join(p for p in (row["side"], (row["body_part"] or "").lower()) if p)
    if row["detail"]:
        what = f"{what}, {str(row['detail']).lower()}" if what else str(row["detail"]).lower()
    text = f"{label}: {what}" if what else label
    ret = _return_date(row["return_date"])
    if ret and row["severity"] != "day_to_day" and ret >= today:
        text += f"; est. return {ret.isoformat()}"
    return text


def latest_injury_flags(
    connection: sqlite3.Connection, settings: Settings, today: date | None = None
) -> dict[int, dict[str, Any]]:
    """player_id -> warning flag, from the newest snapshot (ignored if older than injury_max_age_days)."""
    ensure_schema(connection)
    today = today or date.today()
    newest = connection.execute("SELECT MAX(snapshot_date) FROM player_injury_snapshots").fetchone()[0]
    if not newest:
        return {}
    age = (today - datetime.strptime(newest, "%Y-%m-%d").date()).days
    if age > settings.injury_max_age_days:
        return {}
    flags: dict[int, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT * FROM player_injury_snapshots WHERE snapshot_date = ? AND player_id IS NOT NULL", (newest,)
    ):
        flags[row["player_id"]] = {
            "level": row["severity"],
            "text": describe(row, today),
            "returnDate": row["return_date"],
            "snapshotDate": newest,
        }
    return flags
