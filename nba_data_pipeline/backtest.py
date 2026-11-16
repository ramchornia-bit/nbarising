"""Track record: how did past picks perform AFTER they were listed?

For a series of past days D the lists are rebuilt using only games up to D (no peeking). Then the next
`forward_games` games of every player are compared with his own season average at D.

  avgChange   mean of (next games average - season average at D), in game-value units
  hitRate     share of players who beat (adds) / fell below (drops) their season average afterwards
  lift        avgChange of the tier minus avgChange of the control group (players in the same pool
              that were NOT listed). This removes the general drift of the pool.
  minutesKept mean of (next games minutes - minutes in the recent window at D)

Injuries are not part of the backtest (the feed only has today's snapshot), so these numbers are, if
anything, a little pessimistic for the add lists.
"""
from __future__ import annotations

import sqlite3
import statistics
from typing import Any

from .config import Settings, tier_names
from .engine import load_histories, waiver_list

MIN_SAMPLE = 15  # below this a tier's numbers are shown but flagged as too few to conclude


def _stats(records: list[dict[str, float]], direction: str) -> dict[str, Any]:
    if not records:
        return {"picks": 0, "players": 0}
    deltas = [r["delta"] for r in records]
    hits = sum(1 for d in deltas if (d > 0 if direction == "up" else d < 0))
    return {
        "picks": len(records),
        "players": len({int(r["id"]) for r in records}),
        "avgChange": round(statistics.fmean(deltas), 2),
        "medianChange": round(statistics.median(deltas), 2),
        "hitRate": round(100.0 * hits / len(records), 1),
        "avgFuture": round(statistics.fmean(r["future"] for r in records), 2),
        "avgSeasonAtListing": round(statistics.fmean(r["season"] for r in records), 2),
        "minutesKept": round(statistics.fmean(r["minutesDelta"] for r in records), 2),
        "enough": len(records) >= MIN_SAMPLE,
    }


def run_backtest(
    connection: sqlite3.Connection,
    settings: Settings,
    forward_games: int = 5,
    step_dates: int = 3,
    min_future_games: int = 3,
    warmup_dates: int = 10,
    list_names: tuple[str, ...] = ("sustained", "hot", "drop"),
) -> dict[str, Any]:
    full, _ = load_histories(connection, settings)       # one consistent value scale for outcomes
    dates = sorted({g.date for h in full.values() for g in h.games})
    candidates = dates[warmup_dates:-1:step_dates] if len(dates) > warmup_dates + 1 else []
    result: dict[str, Any] = {
        "format": settings.league_format,
        "forwardGames": forward_games,
        "asOfDates": candidates,
        "minSample": MIN_SAMPLE,
        "lists": {},
        "notes": [],
    }
    if not candidates:
        result["notes"].append(
            f"Not enough history yet: needs more than {warmup_dates + 1} game days (have {len(dates)}).")
        return result

    for name in list_names:
        direction = "down" if name == "drop" else "up"
        tiers = tier_names(direction)
        groups: dict[str, list[dict[str, float]]] = {}
        for as_of in candidates:
            listing = waiver_list(connection, settings, list_name=name, window="sustained",
                                  limit=100000, show_all=True, as_of=as_of)
            for item in listing["players"]:
                if item["stash"]:
                    continue
                history = full.get(item["playerId"])
                if history is None:
                    continue
                past = [g for g in history.games if g.date <= as_of]
                future = [g for g in history.games if g.date > as_of][:forward_games]
                if len(future) < min_future_games or not past:
                    continue
                recent_n = listing["recentGames"]
                season = statistics.fmean(g.value for g in past)
                future_avg = statistics.fmean(g.value for g in future)
                recent_minutes = statistics.fmean(g.minutes for g in past[-recent_n:])
                label = item["label"] or "Not listed (control)"
                groups.setdefault(label, []).append({
                    "id": item["playerId"],
                    "delta": future_avg - season,
                    "future": future_avg,
                    "season": season,
                    "minutesDelta": statistics.fmean(g.minutes for g in future) - recent_minutes,
                })
        control = _stats(groups.get("Not listed (control)", []), direction)
        out_tiers: dict[str, Any] = {}
        for label in (*tiers, "Not listed (control)"):
            stats = _stats(groups.get(label, []), direction)
            if label != "Not listed (control)" and stats["picks"] and control["picks"]:
                stats["lift"] = round(stats["avgChange"] - control["avgChange"], 2)
            out_tiers[label] = stats
        result["lists"][name] = {"direction": direction, "tiers": out_tiers,
                                 "summary": _summary(name, direction, out_tiers, tiers, forward_games)}
    result["notes"].append(
        "Each pick is judged on his own next games against his own season average, so it cannot be "
        "explained by who the player is. Overlapping days count the same player more than once.")
    return result


def _summary(name: str, direction: str, tiers: dict[str, Any], names: tuple[str, ...], k: int) -> str:
    top = tiers.get(names[0], {})
    listed = [tiers[n] for n in names if tiers.get(n, {}).get("picks")]
    if not listed:
        return "No picks yet in this period."
    picks = sum(t["picks"] for t in listed)
    avg = sum(t["avgChange"] * t["picks"] for t in listed) / picks
    hits = sum(t["hitRate"] * t["picks"] for t in listed) / picks
    control = tiers.get("Not listed (control)", {})
    verb = "rose" if direction == "up" else "fell"
    text = (f"Over the next {k} games, listed players averaged {avg:+.1f} against their season average; "
            f"{hits:.0f}% of picks {verb}")
    if control.get("picks"):
        text += f" (players not listed: {control['avgChange']:+.1f})"
    text += "."
    if picks < MIN_SAMPLE or not top.get("enough", False):
        text += " Small sample: treat as a first look, not proof."
    return text
