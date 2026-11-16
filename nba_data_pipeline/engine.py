"""Waiver engine: game value -> signals -> percentile score -> tiers -> reasons.

Independent of the data provider: it only reads player_game_stats / players / teams / games.
Design: see the "Court Signal - Scoring Design" doc.

Signals (each compares RECENT games with the BASELINE games just before them):
  role        minutes change, plus starter-share change (becoming a starter = 6 minutes' worth)
  production  recent game value (level) and game value per 36 minutes
  volume      (FGA + 0.5*3PA + 0.44*FTA + TO) per 36 minutes (median of games), a usage stand-in
  trend       change in game value vs baseline, with the slope as a second opinion
  stability   share of recent games at/above his baseline, minus a variability penalty
Each signal becomes a percentile within the population; the weighted mix is percentile-ranked
again to give the 0-100 score. A rise (or decline) not backed by a real role or volume change is capped (spike rule).
"""
from __future__ import annotations

import math
import sqlite3
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, Callable

from .analysis import slope
from .config import (
    NEGATIVE_CATEGORIES, PERCENT_CATEGORIES, STASH_LABEL, Settings, label_for, settings_as_dict, tier_names,
)
from .injuries import latest_injury_flags

STARTER_MINUTES_EQUIVALENT = 6.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile_map(values: dict[int, float]) -> dict[int, float]:
    """Mid-rank percentile (0-100) of each value among all values."""
    ordered = sorted(values.values())
    n = len(ordered)
    out: dict[int, float] = {}
    for key, value in values.items():
        below = bisect_left(ordered, value)
        through = bisect_right(ordered, value)
        out[key] = 100.0 * (below + 0.5 * (through - below)) / n
    return out


# ---------------------------------------------------------------- game value

def build_game_value(settings: Settings, rows: list[sqlite3.Row]) -> Callable[[sqlite3.Row], float]:
    if settings.league_format == "points":
        weights = settings.points_weights
        return lambda row: sum(w * (row[col] or 0) for col, w in weights.items())

    # 9-category style: sum of per-game z-scores against all player-games in the database.
    def val(row: sqlite3.Row, col: str) -> float:
        return float(row[col] or 0)

    totals = {c: sum(val(r, c) for r in rows) for c in ("fgm", "fga", "ftm", "fta")}
    lg_fg = totals["fgm"] / totals["fga"] if totals["fga"] else 0.0
    lg_ft = totals["ftm"] / totals["fta"] if totals["fta"] else 0.0

    def quantity(row: sqlite3.Row, cat: str) -> float:
        if cat == "fg_pct":
            return val(row, "fgm") - lg_fg * val(row, "fga")
        if cat == "ft_pct":
            return val(row, "ftm") - lg_ft * val(row, "fta")
        return val(row, cat)

    stats = {}
    for cat in settings.categories:
        series = [quantity(r, cat) for r in rows]
        stats[cat] = (_mean(series), _std(series))

    def game_value(row: sqlite3.Row) -> float:
        total = 0.0
        for cat in settings.categories:
            mean, std = stats[cat]
            if std == 0:
                continue
            z = (quantity(row, cat) - (0.0 if cat in PERCENT_CATEGORIES else mean)) / std
            total += -z if cat in NEGATIVE_CATEGORIES else z
        return total

    return game_value


# ---------------------------------------------------------------- histories

@dataclass
class Game:
    date: str
    value: float
    minutes: float
    started: bool
    usage: float  # raw usage stand-in for this game


@dataclass
class History:
    player_id: int
    name: str
    team_id: int
    team: str
    games: list[Game]


def load_histories(
    connection: sqlite3.Connection, settings: Settings, as_of: str | None = None
) -> tuple[dict[int, History], float]:
    """as_of (YYYY-MM-DD): use only games up to and including that day (for backtesting)."""
    rows = connection.execute(
        """
        SELECT s.*, p.full_name, COALESCE(t.abbreviation, '') AS team_abbr
        FROM player_game_stats s
        JOIN players p ON p.player_id = s.player_id
        LEFT JOIN teams t ON t.team_id = s.team_id
        WHERE COALESCE(s.played, 1) = 1 AND COALESCE(s.minutes_seconds, 0) > 0
          AND (? IS NULL OR s.game_date <= ?)
        ORDER BY s.game_date, s.game_id
        """,
        (as_of, as_of),
    ).fetchall()
    game_value = build_game_value(settings, rows)
    histories: dict[int, History] = {}
    all_values: list[float] = []
    for row in rows:
        value = game_value(row)
        all_values.append(value)
        usage = (
            (row["fga"] or 0) + 0.5 * (row["fg3a"] or 0) + 0.44 * (row["fta"] or 0) + (row["turnovers"] or 0)
        )
        game = Game(row["game_date"], value, row["minutes_seconds"] / 60.0, bool(row["started"]), usage)
        history = histories.get(row["player_id"])
        if history is None:
            history = histories[row["player_id"]] = History(
                row["player_id"], row["full_name"], row["team_id"], row["team_abbr"], []
            )
        history.games.append(game)
        history.team_id, history.team = row["team_id"], row["team_abbr"]  # latest team wins
    return histories, _std(all_values)


# ---------------------------------------------------------------- signals

def _per36(games: list[Game], attribute: str) -> float:
    minutes = sum(g.minutes for g in games)
    return sum(getattr(g, attribute) for g in games) / minutes * 36.0 if minutes else 0.0


def compute_signals(
    history: History, recent_n: int, baseline_n: int, pop_std: float
) -> dict[str, Any] | None:
    games = history.games
    if len(games) < recent_n + 2:
        return None
    recent = games[-recent_n:]
    base = games[-(recent_n + baseline_n):-recent_n]
    window = games[-(recent_n + baseline_n):]
    values_recent = [g.value for g in recent]
    values_base = [g.value for g in base]
    start_recent = _mean([1.0 if g.started else 0.0 for g in recent])
    start_base = _mean([1.0 if g.started else 0.0 for g in base])
    min_recent, min_base = _mean([g.minutes for g in recent]), _mean([g.minutes for g in base])
    val_recent, val_base = _mean(values_recent), _mean(values_base)
    above = sum(1 for v in values_recent if v >= val_base)
    window_std = _std([g.value for g in window])
    slope_value = slope([g.value for g in window])
    # Median of per-game usage per 36 min: one huge game cannot fake a volume increase.
    usage_recent = _median([g.usage / g.minutes * 36.0 for g in recent])
    usage_base = _median([g.usage / g.minutes * 36.0 for g in base])
    return {
        "role": (min_recent - min_base) + STARTER_MINUTES_EQUIVALENT * (start_recent - start_base),
        "level": val_recent,
        "per36": _per36(recent, "value"),
        "volume": usage_recent - usage_base,
        "trend": 0.6 * (val_recent - val_base) + 0.4 * slope_value * recent_n,
        "stability": above / len(recent) - (0.5 * window_std / pop_std if pop_std else 0.0),
        "detail": {
            "recentGames": len(recent), "baselineGames": len(base),
            "minutesRecent": min_recent, "minutesBaseline": min_base,
            "startsRecent": sum(1 for g in recent if g.started),
            "startShareRecent": start_recent, "startShareBaseline": start_base,
            "usagePer36Recent": usage_recent, "usagePer36Baseline": usage_base,
            "valueRecent": val_recent, "valueBaseline": val_base,
            "gamesAboveBaseline": above,
            "valueRecentList": [round(v, 1) for v in values_recent],
        },
    }


def backed_by_role_or_volume(signals: dict[str, Any], settings: Settings, direction: str = "up") -> bool:
    """True when minutes, starting role or volume really moved in the direction being scored."""
    d = signals["detail"]
    sign = 1.0 if direction == "up" else -1.0
    return (
        sign * (d["minutesRecent"] - d["minutesBaseline"]) >= settings.backing_minutes_delta
        or sign * (d["startShareRecent"] - d["startShareBaseline"]) >= settings.backing_starter_delta
        or sign * (d["usagePer36Recent"] - d["usagePer36Baseline"]) >= settings.backing_usage_delta
    )


def reasons_for(signals: dict[str, Any], direction: str, unit: str, capped: bool, settings: Settings) -> str:
    d = signals["detail"]
    sign = 1 if direction == "up" else -1
    parts: list[str] = []
    delta_min = d["minutesRecent"] - d["minutesBaseline"]
    if sign * delta_min >= settings.backing_minutes_delta:
        word = "up" if delta_min > 0 else "down"
        parts.append(f"minutes {word} from {d['minutesBaseline']:.0f} to {d['minutesRecent']:.0f}")
    delta_start = d["startShareRecent"] - d["startShareBaseline"]
    if sign * delta_start >= settings.backing_starter_delta:
        if delta_start > 0:
            parts.append(f"now starting ({d['startsRecent']} of last {d['recentGames']})")
        else:
            parts.append("lost his starting spot")
    delta_usage = d["usagePer36Recent"] - d["usagePer36Baseline"]
    if sign * delta_usage >= settings.backing_usage_delta:
        word = "up" if delta_usage > 0 else "down"
        parts.append(f"shot/usage volume {word} {abs(delta_usage):.1f} per 36 min")
    delta_value = d["valueRecent"] - d["valueBaseline"]
    if sign * delta_value > 0:
        parts.append(f"{unit} {d['valueBaseline']:.1f} to {d['valueRecent']:.1f} per game")
    if direction == "up" and d["gamesAboveBaseline"] >= max(2, d["recentGames"] - 1):
        parts.append(f"above his baseline in {d['gamesAboveBaseline']} of last {d['recentGames']}")
    if direction == "down" and d["gamesAboveBaseline"] <= 1 and d["recentGames"] >= 3:
        parts.append(f"below his baseline in {d['recentGames'] - d['gamesAboveBaseline']} of last {d['recentGames']}")
    text = "; ".join(parts) if parts else "no clear change in role or production"
    if capped:
        noun = "rise" if direction == "up" else "decline"
        text += f" (score capped: the {noun} is not backed by minutes, starting role or volume)"
    return text[0].upper() + text[1:] + "."


# ---------------------------------------------------------------- scoring

def score_population(
    histories: dict[int, History],
    ids: list[int],
    direction: str,
    recent_n: int,
    baseline_n: int,
    settings: Settings,
    pop_std: float,
) -> list[dict[str, Any]]:
    signals = {}
    for pid in ids:
        s = compute_signals(histories[pid], recent_n, baseline_n, pop_std)
        if s:
            signals[pid] = s
    if not signals:
        return []
    sign = 1.0 if direction == "up" else -1.0
    maps = {name: {pid: sign * s[name] for pid, s in signals.items()}
            for name in ("role", "level", "per36", "volume", "trend", "stability")}
    pct = {name: percentile_map(values) for name, values in maps.items()}
    weights = settings.signal_weights
    composite: dict[int, float] = {}
    parts: dict[int, dict[str, float]] = {}
    for pid in signals:
        p = {
            "role": pct["role"][pid],
            "production": 0.5 * (pct["level"][pid] + pct["per36"][pid]),
            "volume": pct["volume"][pid],
            "trend": pct["trend"][pid],
            "stability": pct["stability"][pid],
        }
        parts[pid] = p
        composite[pid] = sum(weights[name] * p[name] for name in weights)
    final = percentile_map(composite)
    unit = "fantasy points" if settings.league_format == "points" else "category value"
    out = []
    for pid, s in signals.items():
        score = final[pid]
        capped = False
        backed = backed_by_role_or_volume(s, settings, direction)
        suppress = False
        if not backed:
            if score > settings.spike_cap:
                score, capped = settings.spike_cap, True
            suppress = direction == "down" and settings.drop_requires_role_loss
        out.append({
            "playerId": pid,
            "playerName": histories[pid].name,
            "team": histories[pid].team,
            "score": round(score, 1),
            "label": None if suppress else label_for(score, settings, direction),
            "signalPercentiles": {k: round(v, 1) for k, v in parts[pid].items()},
            "recentValues": s["detail"]["valueRecentList"],
            "minutesRecent": round(s["detail"]["minutesRecent"], 1),
            "minutesBaseline": round(s["detail"]["minutesBaseline"], 1),
            "reason": reasons_for(s, direction, unit, capped, settings),
            "capped": capped,
        })
    return out


def absence_flag(connection: sqlite3.Connection, history: History,
                 as_of: str | None = None) -> dict[str, Any] | None:
    """Recent absence: team games played since his last game with minutes. Needs no injury feed."""
    last_played = history.games[-1].date
    missed = connection.execute(
        """
        SELECT COUNT(*) FROM games
        WHERE (home_team_id = ? OR away_team_id = ?) AND game_date > ?
          AND (? IS NULL OR game_date <= ?)
        """,
        (history.team_id, history.team_id, last_played, as_of, as_of),
    ).fetchone()[0]
    if missed <= 0:
        return None
    return {"level": "recent_absence", "text": f"Missed his team's last {missed} game{'s' if missed != 1 else ''}"}


STASH_LEVELS = {"out_long", "season_ending"}


def _baseline_minutes(history: History, recent_n: int, baseline_n: int) -> float:
    return _mean([g.minutes for g in history.games[-(recent_n + baseline_n):-recent_n]])


def _apply_tiers(
    scored: list[dict[str, Any]], direction: str, settings: Settings, injury_flags: dict[int, dict[str, Any]]
) -> None:
    """In place, on a list sorted by score: stash-only relabel (add lists), then the top-tier cap."""
    top, second, _ = tier_names(direction)
    for item in scored:
        item["stash"] = False
        item["tierCapped"] = False
        level = injury_flags.get(item["playerId"], {}).get("level")
        if direction == "up" and item["label"] and level in STASH_LEVELS:
            item["label"], item["stash"] = STASH_LABEL, True
    kept = 0
    for item in scored:
        if item["label"] == top:
            kept += 1
            if kept > settings.max_top_tier:
                item["label"], item["tierCapped"] = second, True


def waiver_list(
    connection: sqlite3.Connection,
    settings: Settings,
    list_name: str = "sustained",
    window: str = "sustained",
    limit: int = 20,
    show_all: bool = False,
    as_of: str | None = None,
) -> dict[str, Any]:
    """list_name: 'sustained' | 'hot' (add lists) | 'drop' (uses `window`: 'sustained' | 'hot').

    as_of: rebuild the list as it would have looked at the end of that day (injury feed is not
    available historically, so injury flags are skipped)."""
    if list_name not in {"sustained", "hot", "drop"}:
        raise ValueError("list must be sustained, hot or drop")
    histories, pop_std = load_histories(connection, settings, as_of)
    eligible = [pid for pid, h in histories.items() if len(h.games) >= settings.min_games]
    season_avg = {pid: _mean([g.value for g in histories[pid].games]) for pid in eligible}
    ranked = sorted(eligible, key=lambda pid: season_avg[pid], reverse=True)
    rank = {pid: i + 1 for i, pid in enumerate(ranked)}

    which = window if list_name == "drop" else list_name
    if which == "hot":
        recent_n, baseline_n = settings.hot_recent_games, settings.hot_baseline_games
    else:
        recent_n, baseline_n = settings.sustained_recent_games, settings.sustained_baseline_games

    notes: list[str] = []
    protected_count = 0
    if list_name == "drop":
        direction = "down"
        # Rank by the games BEFORE the recent window too, so a star's slump cannot pull him out of protection.
        baseline_value = {
            pid: _mean([g.value for g in histories[pid].games[-(recent_n + baseline_n):-recent_n]])
            for pid in eligible
        }
        baseline_rank = {pid: i + 1 for i, pid in enumerate(sorted(eligible, key=lambda p: baseline_value[p], reverse=True))}
        protected = {
            pid for pid in eligible
            if rank[pid] <= settings.drop_protect_rank or baseline_rank[pid] <= settings.drop_protect_rank
        }
        population = [
            pid for pid in eligible
            if pid not in protected
            and baseline_rank[pid] <= settings.drop_max_baseline_rank
            and _baseline_minutes(histories[pid], recent_n, baseline_n) >= settings.min_baseline_minutes
        ]
        protected_count = len(protected)
    else:
        direction = "up"
        population = [
            pid for pid in eligible
            if rank[pid] > settings.pool_cutoff
            and _mean([g.minutes for g in histories[pid].games[-recent_n:]]) >= settings.min_recent_minutes
        ]
    scored = score_population(histories, population, direction, recent_n, baseline_n, settings, pop_std)
    scored.sort(key=lambda item: item["score"], reverse=True)
    injury_flags = {} if as_of else latest_injury_flags(connection, settings)
    _apply_tiers(scored, direction, settings, injury_flags)

    distribution: dict[str, int] = {}
    for item in scored:
        key = item["label"] or "Below list threshold"
        distribution[key] = distribution.get(key, 0) + 1
    capped = sum(1 for item in scored if item["tierCapped"])
    if capped:
        top, second, _ = tier_names(direction)
        notes.append(f"{capped} more player(s) scored in the top band and are shown as '{second}' "
                     f"(limit of {settings.max_top_tier} '{top}' per list).")
    if direction == "down":
        notes.append(f"{protected_count} established players (top {settings.drop_protect_rank} by season average "
                     f"or before their recent games) are protected and never listed; players who ranked below "
                     f"{settings.drop_max_baseline_rank} before their decline are ignored as not roster-worthy.")

    stash = [item for item in scored if item["stash"]]
    others = [item for item in scored if not item["stash"]]
    tiered = others if show_all else [item for item in others if item["label"]]
    shown = tiered[:limit] + stash[:settings.max_stash_listed]
    for item in shown:
        history = histories[item["playerId"]]
        item["seasonRank"] = rank[item["playerId"]]
        item["gamesPlayed"] = len(history.games)
        flags = []
        if item["playerId"] in injury_flags:
            flags.append(injury_flags[item["playerId"]])
        absence = absence_flag(connection, history, as_of)
        if absence:
            flags.append(absence)
        item["flags"] = flags
    if direction == "up" and len(eligible) <= settings.pool_cutoff:
        notes.append(f"Only {len(eligible)} players have {settings.min_games}+ games, so the waiver pool "
                     f"(ranked below {settings.pool_cutoff}) is empty. Lower pool_cutoff or collect more games.")
    return {
        "list": list_name,
        "window": which,
        "format": settings.league_format,
        "recentGames": recent_n,
        "baselineGames": baseline_n,
        "playersWithEnoughGames": len(eligible),
        "populationSize": len(population),
        "notes": notes,
        "distribution": distribution,
        "players": shown,
        "settings": settings_as_dict(settings),
    }
