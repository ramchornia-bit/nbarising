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
import zipfile
from pathlib import Path


def _request(url: str, token: str | None, accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "court-signal"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _find_asset(repo: str, tag: str, asset: str, token: str | None, api: str) -> dict:
    with urllib.request.urlopen(_request(f"{api}/repos/{repo}/releases/tags/{tag}", token,
                                         "application/vnd.github+json"), timeout=60) as resp:
        release = json.loads(resp.read().decode("utf-8"))
    match = next((a for a in release.get("assets", []) if a.get("name") == asset), None)
    if not match:
        raise RuntimeError(f"release '{tag}' has no asset '{asset}' yet")
    return match


def _fetch(info: dict, token: str | None, path: Path) -> None:
    with urllib.request.urlopen(_request(info["url"], token, "application/octet-stream"), timeout=300) as resp, \
            open(path, "wb") as out:
        shutil.copyfileobj(resp, out)


def download_snapshot(dest: Path, repo: str, tag: str = "data", asset: str = "nba.sqlite.gz",
                      token: str | None = None, api: str = "https://api.github.com") -> int:
    """Download, unzip and atomically swap in the database. Returns its size in bytes."""
    match = _find_asset(repo, tag, asset, token, api)
    dest.parent.mkdir(parents=True, exist_ok=True)
    gz_path, tmp_path = dest.with_suffix(".download.gz"), dest.with_suffix(".download.tmp")
    try:
        _fetch(match, token, gz_path)
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


def download_web(dest_dir: Path, repo: str, tag: str = "web", asset: str = "web.zip",
                 token: str | None = None, api: str = "https://api.github.com") -> int:
    """Download the built web app (zip) and swap it in as dest_dir. Returns the number of files."""
    match = _find_asset(repo, tag, asset, token, api)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir.with_name(dest_dir.name + ".download.zip")
    new_dir = dest_dir.with_name(dest_dir.name + ".new")
    old_dir = dest_dir.with_name(dest_dir.name + ".old")
    try:
        _fetch(match, token, zip_path)
        shutil.rmtree(new_dir, ignore_errors=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(new_dir)
        if not (new_dir / "index.html").exists():
            raise RuntimeError("web package has no index.html")
        shutil.rmtree(old_dir, ignore_errors=True)
        if dest_dir.exists():
            os.replace(dest_dir, old_dir)
        os.replace(new_dir, dest_dir)
        shutil.rmtree(old_dir, ignore_errors=True)
        return sum(1 for p in dest_dir.rglob("*") if p.is_file())
    finally:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(new_dir, ignore_errors=True)


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


def start_snapshot_refresh(dest: Path, config: dict, hours: float = 3.0,
                           web_dir: Path | None = None) -> threading.Thread:
    """Download now (blocking, so the API starts with data), then refresh in the background."""
    web_config = {**config, "tag": os.environ.get("SNAPSHOT_WEB_TAG", "web"), "asset": "web.zip"}

    def once() -> None:
        try:
            size = download_snapshot(dest, **config)
            print(f"[snapshot] loaded {size / 1e6:.1f} MB", flush=True)
        except Exception:
            traceback.print_exc()
        if web_dir is not None:
            try:
                print(f"[web] loaded {download_web(web_dir, **web_config)} files", flush=True)
            except Exception as error:      # the web app is optional; the API keeps working without it
                print(f"[web] not loaded: {error}", flush=True)

    once()

    def next_wait() -> float:
        missing = not dest.exists() or (web_dir is not None and not (web_dir / "index.html").exists())
        return 300 if missing else max(hours, 0.05) * 3600

    def loop() -> None:
        while True:
            time.sleep(next_wait())
            once()

    thread = threading.Thread(target=loop, name="court-signal-snapshot", daemon=True)
    thread.start()
    return thread
