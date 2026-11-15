"""Fetch the database snapshot that the daily GitHub Action publishes (for hosts with no persistent disk).

Environment (all read by serve-web):
  SNAPSHOT_REPO    owner/name of the GitHub repo holding the release   (required to enable)
  SNAPSHOT_TAG     release tag, default "data"
  SNAPSHOT_ASSET   asset file name, default "nba.sqlite.gz"
  SNAPSHOT_TOKEN   GitHub token with read access (needed for a private repo)
  SNAPSHOT_API     API base, default https://api.github.com
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import threading
import time
import traceback
import urllib.request
from pathlib import Path


def _request(url: str, token: str | None, accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "court-signal"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def download_snapshot(dest: Path, repo: str, tag: str = "data", asset: str = "nba.sqlite.gz",
                      token: str | None = None, api: str = "https://api.github.com") -> int:
    """Download, unzip and atomically swap in the database. Returns its size in bytes."""
    with urllib.request.urlopen(_request(f"{api}/repos/{repo}/releases/tags/{tag}", token,
                                         "application/vnd.github+json"), timeout=60) as resp:
        release = json.loads(resp.read().decode("utf-8"))
    match = next((a for a in release.get("assets", []) if a.get("name") == asset), None)
    if not match:
        raise RuntimeError(f"release '{tag}' has no asset '{asset}' yet")
    dest.parent.mkdir(parents=True, exist_ok=True)
    gz_path, tmp_path = dest.with_suffix(".download.gz"), dest.with_suffix(".download.tmp")
    try:
        with urllib.request.urlopen(_request(match["url"], token, "application/octet-stream"), timeout=300) as resp, \
                open(gz_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        with gzip.open(gz_path, "rb") as src, open(tmp_path, "wb") as out:
            shutil.copyfileobj(src, out)
        check = sqlite3.connect(tmp_path)           # refuse a corrupt file before it replaces a good one
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("downloaded database failed integrity check")
        finally:
            check.close()
        os.replace(tmp_path, dest)
        return dest.stat().st_size
    finally:
        for path in (gz_path, tmp_path):
            path.unlink(missing_ok=True)


def config_from_env() -> dict | None:
    repo = os.environ.get("SNAPSHOT_REPO")
    if not repo:
        return None
    return {
        "repo": repo,
        "tag": os.environ.get("SNAPSHOT_TAG", "data"),
        "asset": os.environ.get("SNAPSHOT_ASSET", "nba.sqlite.gz"),
        "token": os.environ.get("SNAPSHOT_TOKEN") or None,
        "api": os.environ.get("SNAPSHOT_API", "https://api.github.com"),
    }


def start_snapshot_refresh(dest: Path, config: dict, hours: float = 3.0) -> threading.Thread:
    """Download now (blocking, so the API starts with data), then refresh in the background."""
    def once() -> None:
        try:
            size = download_snapshot(dest, **config)
            print(f"[snapshot] loaded {size / 1e6:.1f} MB", flush=True)
        except Exception:
            traceback.print_exc()

    once()

    def loop() -> None:
        wait = 300 if not dest.exists() else max(hours, 0.05) * 3600
        while True:
            time.sleep(wait)
            once()
            wait = 300 if not dest.exists() else max(hours, 0.05) * 3600

    thread = threading.Thread(target=loop, name="court-signal-snapshot", daemon=True)
    thread.start()
    return thread
