from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from .analysis import create_form_snapshots, player_recent_summary, ranked_players, trending_players
from .api import run_server
from .webapp import run_web
from .config import load_settings
from .engine import waiver_list
from .injuries import update_injuries
from .espn import backfill_espn, parse_day
from .ingestion import backfill_player_game_logs, ingest_player_game_logs_payload
from .ingestion import ingest_todays_completed_games
from .normalizers import normalize_boxscore_advanced_v3, normalize_live_boxscore
from .storage import connect, init_db, save_boxscore
from .storage import upsert_player_game_advanced_stats


def cmd_ingest_boxscore(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    payloads = payload if isinstance(payload, list) else [payload]
    connection = connect(Path(args.db))
    init_db(connection)
    totals = {"games": 0, "teams": 0, "players": 0, "playerGameStats": 0}
    game_ids: list[str] = []
    for item in payloads:
        teams, players, game, stats_rows = normalize_live_boxscore(item)
        save_boxscore(connection, teams, players, game, stats_rows)
        totals["games"] += 1
        totals["teams"] += len(teams)
        totals["players"] += len(players)
        totals["playerGameStats"] += len(stats_rows)
        game_ids.append(game.game_id)
    print(
        json.dumps(
            {
                "gameIds": game_ids,
                **totals,
                "db": str(Path(args.db).resolve()),
            },
            indent=2,
        )
    )
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    summary = player_recent_summary(connection, args.player_id, args.window)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_trending(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    print(json.dumps({"players": trending_players(connection, args.window, args.limit)}, indent=2))
    return 0


def cmd_rankings(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    result = ranked_players(
        connection,
        direction=args.direction,
        window_games=args.window,
        limit=args.limit,
        include_obvious=args.include_obvious,
    )
    print(json.dumps({"direction": args.direction, "players": result}, indent=2))
    return 0


def cmd_create_snapshots(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    result = create_form_snapshots(connection, args.windows, args.include_obvious)
    print(json.dumps(result, indent=2))
    return 0


def cmd_ingest_advanced_fixture(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    stats_rows = normalize_boxscore_advanced_v3(payload)
    connection = connect(Path(args.db))
    init_db(connection)
    with connection:
        upsert_player_game_advanced_stats(connection, stats_rows)
    print(json.dumps({"advancedRows": len(stats_rows), "db": str(Path(args.db).resolve())}, indent=2))
    return 0


def cmd_ingest_player_game_logs_fixture(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    connection = connect(Path(args.db))
    init_db(connection)
    result = ingest_player_game_logs_payload(connection, payload)
    print(json.dumps({**result, "db": str(Path(args.db).resolve())}, indent=2))
    return 0


def cmd_backfill_player_game_logs(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    result = backfill_player_game_logs(
        connection,
        season=args.season,
        date_from=args.date_from,
        date_to=args.date_to,
        season_type=args.season_type,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_ingest_today(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    result = ingest_todays_completed_games(connection, include_advanced=args.include_advanced)
    print(json.dumps(result, indent=2))
    return 0


def cmd_backfill_espn(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    date_to = parse_day(args.date_to) if args.date_to else date.today() - timedelta(days=1)
    date_from = parse_day(args.date_from) if args.date_from else date_to - timedelta(days=args.days - 1)
    result = backfill_espn(connection, date_from, date_to, force=args.force)
    print(json.dumps({**result, "db": str(Path(args.db).resolve())}, indent=2))
    return 0


def _print_waiver_table(result: dict) -> None:
    title = {"sustained": "Sustained risers (add)", "hot": "Hot: last games (add)",
             "drop": "Drop candidates (release)"}[result["list"]]
    print(f"\n{title}  |  format: {result['format']}  |  recent {result['recentGames']} games vs "
          f"previous {result['baselineGames']}  |  {result['populationSize']} players scored")
    for note in result["notes"]:
        print(f"NOTE: {note}")
    print("Tiers found: " + ", ".join(f"{k}: {v}" for k, v in result["distribution"].items()))
    if not result["players"]:
        print("(no players reach the list threshold)")
    for number, item in enumerate(result["players"], 1):
        flags = "".join(f"  [! {f['text']}]" for f in item["flags"])
        print(f"\n{number:>2}. {item['playerName']} ({item['team']})  score {item['score']:.0f}"
              f"  {item['label'] or '-'}  season rank {item['seasonRank']}{flags}")
        print(f"    {item['reason']}")
        print(f"    last values: {item['recentValues']}  minutes {item['minutesBaseline']} -> {item['minutesRecent']}")


def cmd_waiver(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    settings = load_settings(
        args.settings, league_format=args.format, pool_cutoff=args.pool_cutoff, min_games=args.min_games,
    )
    result = waiver_list(
        connection, settings, list_name=args.list, window=args.window, limit=args.limit, show_all=args.all,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_waiver_table(result)
    return 0


def cmd_update_injuries(args: argparse.Namespace) -> int:
    connection = connect(Path(args.db))
    init_db(connection)
    settings = load_settings(args.settings)
    print(json.dumps(update_injuries(connection, settings), indent=2))
    return 0


def cmd_daily_update(args: argparse.Namespace) -> int:
    """The one command to schedule every day: recent games from ESPN, then today's injury snapshot."""
    from .scheduler import run_update
    start = date.fromisoformat(args.bootstrap_from) if args.bootstrap_from else None
    result = run_update(Path(args.db), load_settings(args.settings), args.days, start)
    print(json.dumps(result, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    run_server(Path(args.db), args.host, args.port)
    return 0


def cmd_serve_web(args: argparse.Namespace) -> int:
    run_web(Path(args.db), args.host, args.port, args.auto_update_hours, args.bootstrap_from)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NBA fantasy ingestion proof CLI")
    subparsers = parser.add_subparsers(required=True)

    ingest = subparsers.add_parser("ingest-boxscore-fixture")
    ingest.add_argument("--fixture", required=True)
    ingest.add_argument("--db", required=True)
    ingest.set_defaults(func=cmd_ingest_boxscore)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--db", required=True)
    summary.add_argument("--player-id", required=True, type=int)
    summary.add_argument("--window", default=5, type=int)
    summary.set_defaults(func=cmd_summary)

    trending = subparsers.add_parser("trending")
    trending.add_argument("--db", required=True)
    trending.add_argument("--window", default=5, type=int)
    trending.add_argument("--limit", default=20, type=int)
    trending.set_defaults(func=cmd_trending)

    rankings = subparsers.add_parser("rankings")
    rankings.add_argument("--db", required=True)
    rankings.add_argument("--direction", choices=["up", "down"], default="up")
    rankings.add_argument("--window", default=5, type=int)
    rankings.add_argument("--limit", default=20, type=int)
    rankings.add_argument("--include-obvious", action="store_true")
    rankings.set_defaults(func=cmd_rankings)

    snapshots = subparsers.add_parser("create-form-snapshots")
    snapshots.add_argument("--db", required=True)
    snapshots.add_argument("--windows", nargs="+", default=[3, 5, 10, 20], type=int)
    snapshots.add_argument("--include-obvious", action="store_true")
    snapshots.set_defaults(func=cmd_create_snapshots)

    advanced = subparsers.add_parser("ingest-advanced-fixture")
    advanced.add_argument("--fixture", required=True)
    advanced.add_argument("--db", required=True)
    advanced.set_defaults(func=cmd_ingest_advanced_fixture)

    player_logs_fixture = subparsers.add_parser("ingest-playergamelogs-fixture")
    player_logs_fixture.add_argument("--fixture", required=True)
    player_logs_fixture.add_argument("--db", required=True)
    player_logs_fixture.set_defaults(func=cmd_ingest_player_game_logs_fixture)

    backfill = subparsers.add_parser("backfill-playergamelogs")
    backfill.add_argument("--db", required=True)
    backfill.add_argument("--season", required=True)
    backfill.add_argument("--date-from", default="")
    backfill.add_argument("--date-to", default="")
    backfill.add_argument("--season-type", default="Regular Season")
    backfill.set_defaults(func=cmd_backfill_player_game_logs)

    today = subparsers.add_parser("ingest-today")
    today.add_argument("--db", required=True)
    today.add_argument("--include-advanced", action="store_true")
    today.set_defaults(func=cmd_ingest_today)

    espn = subparsers.add_parser(
        "backfill-espn",
        help="Fetch finished games from ESPN for a date range (also the daily update: run with --days 3)",
    )
    espn.add_argument("--db", required=True)
    espn.add_argument("--date-from", default="", help="YYYY-MM-DD")
    espn.add_argument("--date-to", default="", help="YYYY-MM-DD (default: yesterday)")
    espn.add_argument("--days", default=3, type=int, help="used when --date-from is omitted")
    espn.add_argument("--force", action="store_true", help="re-fetch games already stored")
    espn.set_defaults(func=cmd_backfill_espn)

    waiver = subparsers.add_parser(
        "waiver", help="Add / drop lists with scores, tiers and reasons (the Court Signal engine)"
    )
    waiver.add_argument("--db", required=True)
    waiver.add_argument("--list", choices=["sustained", "hot", "drop"], default="sustained")
    waiver.add_argument("--window", choices=["sustained", "hot"], default="sustained",
                        help="for --list drop: which window to judge decline over")
    waiver.add_argument("--format", choices=["points", "categories"], default=None)
    waiver.add_argument("--settings", default=None, help="JSON file overriding any setting")
    waiver.add_argument("--pool-cutoff", type=int, default=None, help="waiver pool = ranked below this")
    waiver.add_argument("--min-games", type=int, default=None)
    waiver.add_argument("--limit", type=int, default=20)
    waiver.add_argument("--all", action="store_true", help="also show players below the Watch threshold")
    waiver.add_argument("--json", action="store_true")
    waiver.set_defaults(func=cmd_waiver)

    inj = subparsers.add_parser("update-injuries", help="Save today's ESPN injury snapshot")
    inj.add_argument("--db", required=True)
    inj.add_argument("--settings", default=None)
    inj.set_defaults(func=cmd_update_injuries)

    daily = subparsers.add_parser("daily-update", help="Recent games + today's injuries (schedule this daily)")
    daily.add_argument("--db", required=True)
    daily.add_argument("--days", default=3, type=int)
    daily.add_argument("--settings", default=None)
    daily.add_argument("--bootstrap-from", default=None, help="only when the database is empty: load games from this date")
    daily.set_defaults(func=cmd_daily_update)

    serve = subparsers.add_parser("serve-api")
    serve.add_argument("--db", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8765, type=int)
    serve.set_defaults(func=cmd_serve)

    web = subparsers.add_parser("serve-web", help="Start the Court Signal JSON API (for the app / web page)")
    web.add_argument("--db", required=True)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8000, type=int)
    web.add_argument("--auto-update-hours", default=0, type=float, help="refresh games + injuries every N hours (0 = off)")
    web.add_argument("--bootstrap-from", default=None, help="first run only: load games from this date (YYYY-MM-DD)")
    web.set_defaults(func=cmd_serve_web)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
