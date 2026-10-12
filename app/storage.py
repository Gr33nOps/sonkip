"""Persistent SQLite library of locally downloaded audio."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9]+$")


class MusicStore:
    def __init__(self, home: Path):
        self.home = home.expanduser().resolve()
        self.tracks_dir = self.home / "tracks"
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "library.sqlite3"
        self.youtube_cookies_path = self.home / "private" / "youtube-cookies.txt"
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    duration INTEGER,
                    filename TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    extension TEXT NOT NULL,
                    codec TEXT,
                    abr REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def youtube_auth_connected(self) -> bool:
        return self.youtube_cookies_path.is_file()

    def save_youtube_cookies(self, content: str) -> None:
        if len(content.encode("utf-8")) > 1024 * 1024:
            raise ValueError("That sign-in file is too large")
        if not content.startswith(("# Netscape HTTP Cookie File", "# HTTP Cookie File")):
            raise ValueError("Choose a Netscape cookies.txt file")
        youtube_lines = []
        for line in content.splitlines():
            row_text = line.removeprefix("#HttpOnly_")
            row = row_text.split("\t")
            if len(row) == 7 and row[0].lstrip(".").endswith("youtube.com"):
                youtube_lines.append(line)
        if not youtube_lines:
            raise ValueError("That file does not contain a YouTube sign-in")
        safe_content = "# Netscape HTTP Cookie File\n" + "\n".join(youtube_lines) + "\n"
        self.youtube_cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_cookies_path.write_text(safe_content, encoding="utf-8")
        self.youtube_cookies_path.chmod(0o600)

    def clear_youtube_cookies(self) -> None:
        self.youtube_cookies_path.unlink(missing_ok=True)

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def list_tracks(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM tracks ORDER BY created_at DESC, rowid DESC").fetchall()
        return [dict(row) for row in rows if self.path_for(dict(row)).is_file()]

    def get_track(self, track_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return self._to_dict(row)

    def path_for(self, track: dict[str, Any]) -> Path:
        filename = track["filename"]
        if not FILENAME_RE.fullmatch(filename):
            raise ValueError("Invalid stored audio filename")
        return self.tracks_dir / filename

    def add_track(self, track: dict[str, Any]) -> None:
        fields = ("id", "video_id", "title", "artist", "duration", "filename", "bytes", "extension", "codec", "abr")
        with self._connect() as db:
            db.execute(
                f"INSERT INTO tracks ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                tuple(track.get(f) for f in fields),
            )

    def delete_track(self, track_id: str) -> bool:
        track = self.get_track(track_id)
        if track is None:
            return False
        path = self.path_for(track)
        path.unlink(missing_ok=True)
        with self._connect() as db:
            db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        return True
