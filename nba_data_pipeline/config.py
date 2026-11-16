"""User-editable settings for the waiver engine (see the Court Signal scoring design doc).

Everything a person may want to change lives here or in a JSON file passed with --settings.
Nothing in engine.py hard-codes weights, windows or tier cut-offs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

# Columns of player_game_stats that may be used as stats.
STAT_COLUMNS = {
    "points", "rebounds", "offensive_rebounds", "defensive_rebounds", "assists", "steals",
    "blocks", "turnovers", "personal_fouls", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
}
# Extra category names understood by 9-category mode (computed from attempts).
PERCENT_CATEGORIES = {"fg_pct", "ft_pct"}
# Categories where a LOWER number is better.
NEGATIVE_CATEGORIES = {"turnovers", "personal_fouls"}

DEFAULT_POINT_WEIGHTS = {
    "points": 1.0, "rebounds": 1.2, "assists": 1.5, "steals": 3.0, "blocks": 3.0, "turnovers": -1.0,
}
DEFAULT_CATEGORIES = [
    "points", "rebounds", "assists", "steals", "blocks", "fg3m", "fg_pct", "ft_pct", "turnovers",
]
# Tuned with the backtest on the first weeks of the 2026-27 season (points leagues): a change of role
# (minutes, starting) persists, a hot shooting streak does not, so role and stability weigh more and raw
# production less than in the first design (0.30 / 0.25 / 0.20 / 0.15 / 0.10). Re-check as data grows.
DEFAULT_SIGNAL_WEIGHTS = {
    "role": 0.40, "production": 0.10, "volume": 0.15, "trend": 0.15, "stability": 0.20,
}


@dataclass
class Settings:
    league_format: str = "points"  # "points" or "categories"
    points_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_POINT_WEIGHTS))
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    signal_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SIGNAL_WEIGHTS))

    # Waiver pool: players ranked BELOW this by season average (needs min_games).
    pool_cutoff: int = 100
    min_games: int = 5
    # Add lists ignore players whose recent minutes are below this (cannot help a roster).
    min_recent_minutes: float = 12.0

    # Windows: recent games compared with the baseline games before them.
    hot_recent_games: int = 3
    hot_baseline_games: int = 7
    sustained_recent_games: int = 5
    sustained_baseline_games: int = 10

    # Tier cut-offs (score 0-100).
    tier_watch: float = 70.0
    tier_add: float = 80.0
    tier_good: float = 90.0
    # A rise not backed by a real role or volume change cannot score above this (below "Consider adding").
    spike_cap: float = 79.0
    # "Backed" means at least one of these changes (recent vs baseline) is reached:
    backing_minutes_delta: float = 3.0       # minutes per game
    backing_starter_delta: float = 0.4       # share of games started (0.4 = e.g. 2 more starts in 5)
    backing_usage_delta: float = 3.0         # usage stand-in per 36 minutes (median of games)

    # Injury warning levels (ESPN gives only "Out" / "Day-To-Day" plus an estimated return date).
    injury_short_term_days: int = 14         # Out with return within this many days = short term
    injury_season_ending_days: int = 120     # Out with return further away than this = likely season-ending
    injury_max_age_days: int = 3             # ignore an injury snapshot older than this

    # List shaping.
    max_top_tier: int = 10                   # at most this many "Good catch" (or "Strong drop candidate") per list
    min_baseline_minutes: float = 12.0       # Drop list: only players who averaged this in the baseline games
    max_stash_listed: int = 10               # how many "Injured - stash only" players to list after the tiers

    # Drop list protections: a slumping established player is not a drop candidate.
    drop_protect_rank: int = 100             # ranked this high (season average OR the games before the slump) = protected
    drop_requires_role_loss: bool = True     # a decline must come with lost minutes, starting role or volume
    drop_max_baseline_rank: int = 250        # ignore players who ranked below this BEFORE their decline (nobody owns them)

    def validate(self) -> "Settings":
        if self.league_format not in {"points", "categories"}:
            raise ValueError("league_format must be 'points' or 'categories'")
        bad = [k for k in self.points_weights if k not in STAT_COLUMNS]
        if bad:
            raise ValueError(f"unknown stat in points_weights: {bad}; allowed: {sorted(STAT_COLUMNS)}")
        bad = [c for c in self.categories if c not in STAT_COLUMNS | PERCENT_CATEGORIES]
        if bad:
            raise ValueError(f"unknown category: {bad}")
        if set(self.signal_weights) != set(DEFAULT_SIGNAL_WEIGHTS):
            raise ValueError(f"signal_weights needs exactly: {sorted(DEFAULT_SIGNAL_WEIGHTS)}")
        total = sum(self.signal_weights.values())
        if total <= 0:
            raise ValueError("signal_weights must sum to more than 0")
        self.signal_weights = {k: v / total for k, v in self.signal_weights.items()}
        if self.drop_protect_rank < 0:
            raise ValueError("drop_protect_rank cannot be negative")
        if self.drop_max_baseline_rank < self.drop_protect_rank:
            raise ValueError("drop_max_baseline_rank must be at least drop_protect_rank")
        if self.max_top_tier < 1:
            raise ValueError("max_top_tier must be at least 1")
        if self.spike_cap >= self.tier_good:
            raise ValueError("spike_cap must be below tier_good")
        if not (self.tier_watch < self.tier_add < self.tier_good <= 100):
            raise ValueError("tiers must satisfy watch < add < good <= 100")
        return self


def load_settings(path: str | Path | None = None, **overrides: Any) -> Settings:
    """Defaults, then values from a JSON file, then keyword overrides (e.g. from the CLI)."""
    values: dict[str, Any] = {}
    if path:
        values.update(json.loads(Path(path).read_text(encoding="utf-8")))
    values.update({k: v for k, v in overrides.items() if v is not None})
    return settings_from_dict(values)


def settings_from_dict(values: dict[str, Any]) -> Settings:
    known = {f.name for f in fields(Settings)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"unknown setting(s): {sorted(unknown)}; known: {sorted(known)}")
    return Settings(**values).validate()


def settings_as_dict(settings: Settings) -> dict[str, Any]:
    return asdict(settings)


STASH_LABEL = "Injured - stash only"


def tier_names(direction: str) -> tuple[str, str, str]:
    if direction == "up":
        return ("Good catch", "Consider adding", "Watch closely")
    return ("Strong drop candidate", "Consider dropping", "Watch for decline")


def label_for(score: float, settings: Settings, direction: str) -> str | None:
    """Tier label for a 0-100 score. The drop side mirrors the add bands."""
    names = tier_names(direction)
    if score >= settings.tier_good:
        return names[0]
    if score >= settings.tier_add:
        return names[1]
    if score >= settings.tier_watch:
        return names[2]
    return None
