"""Tolerant player-name matching, shared by the injury import and the roster feature.

ESPN formats names consistently within one feed, but a person typing a roster (or a second feed)
may write "TJ McConnell" for "T.J. McConnell", drop an accent, or omit "Jr.".
"""
from __future__ import annotations

import difflib
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[.'’`]", "", text)          # T.J. -> tj, De'Andre -> deandre
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())


def base_name(normalized: str) -> str:
    parts = normalized.split()
    while len(parts) > 1 and parts[-1] in SUFFIXES:
        parts.pop()
    return " ".join(parts)


@dataclass
class Resolution:
    player_id: int | None
    status: str                       # "matched" | "ambiguous" | "none"
    suggestions: list[str] = field(default_factory=list)


class NameIndex:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.names: dict[int, str] = {}
        self.team: dict[int, int | None] = {}
        self.by_key: dict[str, list[int]] = {}
        self.by_base: dict[str, list[int]] = {}
        for row in connection.execute("SELECT player_id, full_name, current_team_id FROM players"):
            pid = row["player_id"]
            self.names[pid] = row["full_name"]
            self.team[pid] = row["current_team_id"]
            key = normalize_name(row["full_name"])
            self.by_key.setdefault(key, []).append(pid)
            self.by_base.setdefault(base_name(key), []).append(pid)

    def _pick(self, candidates: list[int], team_id: int | None) -> Resolution | None:
        if len(candidates) == 1:
            return Resolution(candidates[0], "matched")
        if len(candidates) > 1:
            if team_id is not None:
                same_team = [c for c in candidates if self.team.get(c) == team_id]
                if len(same_team) == 1:
                    return Resolution(same_team[0], "matched")
            return Resolution(None, "ambiguous", [self.names[c] for c in candidates][:4])
        return None

    def resolve(self, name: str, team_id: int | None = None) -> Resolution:
        key = normalize_name(name)
        for index, lookup in ((self.by_key, key), (self.by_base, base_name(key))):
            found = self._pick(index.get(lookup, []), team_id)
            if found:
                return found
        close = difflib.get_close_matches(key, list(self.by_key), n=3, cutoff=0.7)
        return Resolution(None, "none", [self.names[self.by_key[c][0]] for c in close])
