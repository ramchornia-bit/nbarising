from __future__ import annotations

import sqlite3
from typing import Any


def fantasy_points(row: sqlite3.Row) -> float:
    return (
        (row["points"] or 0)
        + 1.2 * (row["rebounds"] or 0)
        + 1.5 * (row["assists"] or 0)
        + 3.0 * (row["steals"] or 0)
        + 3.0 * (row["blocks"] or 0)
        - 1.0 * (row["turnovers"] or 0)
    )


def slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    xs = list(range(1, len(values) + 1))
    x_mean = sum(xs) / len(xs)
    y_mean = sum(values) / len(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=True))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return 0.0 if denominator == 0 else numerator / denominator


def trend_label(value: float) -> str:
    if value >= 3:
        return "strongly_increasing"
    if value >= 1:
        return "increasing"
    if value <= -3:
        return "strongly_decreasing"
    if value <= -1:
        return "decreasing"
    return "stable"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def consistency_score(values: list[float]) -> float:
    if len(values) < 2:
        return 50.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    stdev = variance**0.5
    return clamp(100 - stdev * 4)


def _source_fantasy_points(row: sqlite3.Row) -> float:
    if row["nba_fantasy_points"] is not None:
        return float(row["nba_fantasy_points"])
    return fantasy_points(row)


def player_recent_summary(
    connection: sqlite3.Connection, player_id: int, window_games: int = 5
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT p.full_name, s.*
        FROM player_game_stats s
        JOIN players p ON p.player_id = s.player_id
        WHERE s.player_id = ? AND COALESCE(s.played, 1) = 1
        ORDER BY s.game_date DESC, s.game_id DESC
        LIMIT ?
        """,
        (player_id, window_games),
    ).fetchall()
    rows = list(reversed(rows))
    if not rows:
        raise ValueError(f"No game stats found for player_id={player_id}")

    fantasy_values = [_source_fantasy_points(row) for row in rows]
    minutes_values = [(row["minutes_seconds"] or 0) / 60 for row in rows]
    shot_values = [(row["fga"] or 0) + 0.5 * (row["fg3a"] or 0) for row in rows]
    fantasy_slope = slope(fantasy_values)
    minutes_slope = slope(minutes_values)
    shot_slope = slope(shot_values)

    return {
        "playerId": player_id,
        "playerName": rows[-1]["full_name"],
        "games": len(rows),
        "dates": [row["game_date"] for row in rows],
        "fantasyPoints": [round(value, 2) for value in fantasy_values],
        "minutes": [round(value, 2) for value in minutes_values],
        "shotVolume": [round(value, 2) for value in shot_values],
        "averageFantasyPoints": round(sum(fantasy_values) / len(fantasy_values), 2),
        "averageMinutes": round(sum(minutes_values) / len(minutes_values), 2),
        "fantasySlope": round(fantasy_slope, 2),
        "minutesSlope": round(minutes_slope, 2),
        "shotVolumeSlope": round(shot_slope, 2),
        "trend": trend_label(fantasy_slope),
        "explanation": (
            f"{rows[-1]['full_name']} last {len(rows)} games: fantasy production "
            f"slope {fantasy_slope:.2f}, minutes slope {minutes_slope:.2f}, "
            f"shot-volume slope {shot_slope:.2f}."
        ),
    }


def score_summary(summary: dict[str, Any]) -> dict[str, Any]:
    fantasy_slope = float(summary["fantasySlope"])
    minutes_slope = float(summary["minutesSlope"])
    shot_slope = float(summary["shotVolumeSlope"])
    avg_fantasy = float(summary["averageFantasyPoints"])
    fantasy_values = [float(value) for value in summary["fantasyPoints"]]

    consistency = consistency_score(fantasy_values)
    trend_score = clamp(50 + fantasy_slope * 6)
    opportunity_score = clamp(50 + minutes_slope * 8 + shot_slope * 5)
    production_level = clamp(avg_fantasy * 1.6)
    breakout_score = clamp(trend_score * 0.4 + opportunity_score * 0.4 + production_level * 0.2)
    drop_risk = clamp(50 - fantasy_slope * 7 - minutes_slope * 6 - shot_slope * 4)
    waiver_score = clamp(
        breakout_score * 0.55 + opportunity_score * 0.25 + consistency * 0.1 + production_level * 0.1
    )
    profile = "obvious_rostered" if avg_fantasy >= 45 and summary["games"] >= 5 else "waiver_research"

    reasons = []
    if fantasy_slope >= 1:
        reasons.append(f"fantasy production is rising by {fantasy_slope:.2f} per game")
    elif fantasy_slope <= -1:
        reasons.append(f"fantasy production is falling by {abs(fantasy_slope):.2f} per game")
    if minutes_slope >= 1:
        reasons.append(f"minutes are rising by {minutes_slope:.2f} per game")
    elif minutes_slope <= -1:
        reasons.append(f"minutes are falling by {abs(minutes_slope):.2f} per game")
    if shot_slope >= 1:
        reasons.append(f"shot volume is rising by {shot_slope:.2f} per game")
    elif shot_slope <= -1:
        reasons.append(f"shot volume is falling by {abs(shot_slope):.2f} per game")
    if not reasons:
        reasons.append("recent role and production are mostly stable")

    return {
        **summary,
        "trendScore": round(trend_score, 2),
        "opportunityScore": round(opportunity_score, 2),
        "consistencyScore": round(consistency, 2),
        "breakoutScore": round(breakout_score, 2),
        "dropRisk": round(drop_risk, 2),
        "waiverScore": round(waiver_score, 2),
        "profile": profile,
        "rankingExplanation": f"{summary['playerName']}: " + "; ".join(reasons) + ".",
    }


def trending_players(
    connection: sqlite3.Connection, window_games: int = 5, limit: int = 20
) -> list[dict[str, Any]]:
    player_ids = connection.execute(
        """
        SELECT player_id
        FROM player_game_stats
        WHERE COALESCE(played, 1) = 1
        GROUP BY player_id
        HAVING COUNT(*) >= ?
        """,
        (window_games,),
    ).fetchall()
    summaries = [
        player_recent_summary(connection, row["player_id"], window_games) for row in player_ids
    ]
    summaries.sort(
        key=lambda item: (
            item["fantasySlope"],
            item["minutesSlope"],
            item["shotVolumeSlope"],
            item["averageFantasyPoints"],
        ),
        reverse=True,
    )
    return summaries[:limit]


def ranked_players(
    connection: sqlite3.Connection,
    direction: str = "up",
    window_games: int = 5,
    limit: int = 20,
    include_obvious: bool = False,
) -> list[dict[str, Any]]:
    player_ids = connection.execute(
        """
        SELECT player_id
        FROM player_game_stats
        WHERE COALESCE(played, 1) = 1
        GROUP BY player_id
        HAVING COUNT(*) >= ?
        """,
        (window_games,),
    ).fetchall()
    scored = [
        score_summary(player_recent_summary(connection, row["player_id"], window_games))
        for row in player_ids
    ]
    if not include_obvious:
        scored = [item for item in scored if item["profile"] != "obvious_rostered"]
    if direction == "down":
        scored.sort(
            key=lambda item: (
                item["dropRisk"],
                -item["fantasySlope"],
                -item["minutesSlope"],
                -item["shotVolumeSlope"],
            ),
            reverse=True,
        )
    else:
        scored.sort(
            key=lambda item: (
                item["waiverScore"],
                item["breakoutScore"],
                item["opportunityScore"],
                item["fantasySlope"],
            ),
            reverse=True,
        )
    return scored[:limit]


def create_form_snapshots(
    connection: sqlite3.Connection,
    windows: list[int] | None = None,
    include_obvious: bool = True,
) -> dict[str, Any]:
    windows = windows or [3, 5, 10, 20]
    inserted = 0
    snapshot_dates = set()
    with connection:
        for window in windows:
            for summary in ranked_players(connection, "up", window, 10_000, include_obvious):
                as_of_date = summary["dates"][-1]
                snapshot_dates.add(as_of_date)
                connection.execute(
                    """
                    INSERT INTO player_form_snapshots (
                        player_id, as_of_date, window_games, player_name, avg_fantasy_points,
                        avg_minutes, avg_shot_volume, fantasy_points_slope, minutes_slope,
                        shot_volume_slope, consistency_score, opportunity_score, breakout_score,
                        drop_risk, waiver_score, profile, explanation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(player_id, as_of_date, window_games) DO UPDATE SET
                        player_name = excluded.player_name,
                        avg_fantasy_points = excluded.avg_fantasy_points,
                        avg_minutes = excluded.avg_minutes,
                        avg_shot_volume = excluded.avg_shot_volume,
                        fantasy_points_slope = excluded.fantasy_points_slope,
                        minutes_slope = excluded.minutes_slope,
                        shot_volume_slope = excluded.shot_volume_slope,
                        consistency_score = excluded.consistency_score,
                        opportunity_score = excluded.opportunity_score,
                        breakout_score = excluded.breakout_score,
                        drop_risk = excluded.drop_risk,
                        waiver_score = excluded.waiver_score,
                        profile = excluded.profile,
                        explanation = excluded.explanation
                    """,
                    (
                        summary["playerId"],
                        as_of_date,
                        window,
                        summary["playerName"],
                        summary["averageFantasyPoints"],
                        summary["averageMinutes"],
                        sum(summary["shotVolume"]) / len(summary["shotVolume"]),
                        summary["fantasySlope"],
                        summary["minutesSlope"],
                        summary["shotVolumeSlope"],
                        summary["consistencyScore"],
                        summary["opportunityScore"],
                        summary["breakoutScore"],
                        summary["dropRisk"],
                        summary["waiverScore"],
                        summary["profile"],
                        summary["rankingExplanation"],
                    ),
                )
                inserted += 1
    return {"windows": windows, "snapshotsProcessed": inserted, "asOfDates": sorted(snapshot_dates)}
