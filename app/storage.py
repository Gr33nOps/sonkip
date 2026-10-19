"""Persistent SQLite library of locally downloaded audio."""
from __future__ import annotations

import re
import os
import shutil
import sqlite3
import json
import uuid
import zipfile
import threading
from pathlib import Path
from typing import Any

FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9]+$")


class MusicStore:
    def __init__(self, home: Path):
        self.home = home.expanduser().resolve()
        self.folder_lock = threading.RLock()
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
            db.execute('CREATE TABLE IF NOT EXISTS download_jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS folder_copies (folder TEXT, track_id TEXT, filename TEXT, PRIMARY KEY(folder, track_id))')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(tracks)').fetchall()}
            for name, sql_type in {
                'album': 'TEXT', 'album_artist': 'TEXT', 'artwork_url': 'TEXT',
                'track_number': 'INTEGER', 'release_date': 'TEXT',
                'release_id': 'TEXT', 'release_type': 'TEXT',
            }.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE tracks ADD COLUMN {name} {sql_type}')
        for track in self.list_tracks():
            repeated = f"{track['artist']} - {track['artist']} - ".casefold()
            if FILENAME_RE.fullmatch(track['filename']) or track['filename'].casefold().startswith(repeated):
                self._name_audio(track)

    def music_folder_status(self):
        with self._connect() as db:
            settings = dict(db.execute('SELECT key,value FROM settings').fetchall())
        return {'folder': settings.get('music_folder', ''), 'error': settings.get('folder_error', '')}

    def set_music_folder(self, folder: str):
        with self.folder_lock:
            if folder:
                path = Path(folder).expanduser()
                if not path.is_absolute() or not path.is_dir():
                    raise ValueError('Choose an existing absolute folder path')
                folder = str(path.resolve())
            with self._connect() as db:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('music_folder', folder))
            self.sync_music_folder()
        return self.music_folder_status()

    def sync_music_folder(self):
        with self.folder_lock:
            folder = self.music_folder_status()['folder']
            error = ''
            try:
                if folder:
                    destination = Path(folder)
                    if not destination.is_dir():
                        raise OSError('Selected folder is unavailable. Reconnect it and retry.')
                    for track in self.list_tracks():
                        source = self.path_for(track)
                        if destination.resolve() == self.tracks_dir.resolve():
                            continue
                        with self._connect() as db:
                            previous = db.execute('SELECT filename FROM folder_copies WHERE folder=? AND track_id=?', (folder, track['id'])).fetchone()
                        if previous and (destination / previous['filename']).is_file():
                            continue
                        target = destination / source.name
                        suffix = 2
                        while True:
                            try:
                                output = target.open('xb')
                                break
                            except FileExistsError:
                                target = destination / f'{source.stem} ({suffix}){source.suffix}'
                                suffix += 1
                        try:
                            with output, source.open('rb') as audio:
                                shutil.copyfileobj(audio, output, 1024 * 1024)
                            with self._connect() as db:
                                db.execute('INSERT OR REPLACE INTO folder_copies VALUES (?,?,?)', (folder, track['id'], target.name))
                        except Exception:
                            target.unlink(missing_ok=True)
                            raise
            except (OSError, ValueError) as exc:
                error = str(exc)
            with self._connect() as db:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('folder_error', error))

    def save_job(self, job: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO download_jobs (id, payload) VALUES (?, ?)',
                       (job['id'], json.dumps(job)))

    def export_backup(self, destination: Path, playlists=None) -> None:
        tracks = self.list_tracks()
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr('sonkip.json', json.dumps({'version': 1, 'tracks': tracks, 'playlists': playlists or []}, ensure_ascii=False))
            for track in tracks:
                archive.write(self.path_for(track), 'tracks/' + track['filename'])

    def import_backup(self, source: Path) -> dict:
        with zipfile.ZipFile(source) as archive:
            if archive.getinfo('sonkip.json').file_size > 16 * 1024 * 1024:
                raise ValueError('Backup metadata is too large')
            manifest = json.loads(archive.read('sonkip.json'))
            if manifest.get('version') != 1 or not isinstance(manifest.get('tracks'), list):
                raise ValueError('Choose a Sonkip backup ZIP')
            playlists = manifest.get('playlists', [])
            if not isinstance(playlists, list):
                raise ValueError('Invalid playlists in backup')
            for playlist in playlists:
                if (not isinstance(playlist, dict) or not isinstance(playlist.get('id'), str)
                    or not isinstance(playlist.get('name'), str) or not 1 <= len(playlist['name'].strip()) <= 80
                    or not isinstance(playlist.get('tracks'), list)
                    or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value) for value in playlist['tracks'])):
                    raise ValueError('Invalid playlist in backup')
            seen = set()
            total = 0
            for track in manifest['tracks']:
                if (not isinstance(track, dict) or not re.fullmatch('[0-9a-f]{32}', str(track.get('id', '')))
                    or not re.fullmatch('[A-Za-z0-9_-]{11}', str(track.get('video_id', '')))
                    or not re.fullmatch('[a-zA-Z0-9]{1,8}', str(track.get('extension', '')))
                    or not isinstance(track.get('title'), str) or not isinstance(track.get('artist'), str)):
                    raise ValueError('Invalid song in backup')
                self.path_for(track)  # Validate names before writing any audio.
                if track['id'] in seen:
                    raise ValueError('Duplicate song ID in backup')
                seen.add(track['id'])
                info = archive.getinfo('tracks/' + track['filename'])
                if info.file_size > 4 * 1024 ** 3 or info.file_size <= 0:
                    raise ValueError('Invalid audio size in backup')
                total += info.file_size
                existing = self.get_track(track['id'])
                if existing and existing['video_id'] != track['video_id']:
                    raise ValueError('Backup song ID conflicts with this library')
            if total > shutil.disk_usage(self.home).free:
                raise ValueError('Not enough free space to restore this backup')
            imported = 0
            for original in manifest['tracks']:
                if self.get_track(original['id']):
                    continue
                track = dict(original)
                target = self.tracks_dir / (uuid.uuid4().hex + '.' + track['extension'])
                try:
                    with archive.open('tracks/' + track['filename']) as audio, target.open('xb') as output:
                        shutil.copyfileobj(audio, output, 1024 * 1024)
                    track.update(filename=target.name, bytes=target.stat().st_size)
                    self.add_track(track)
                    if isinstance(track.get('created_at'), str):
                        with self._connect() as db:
                            db.execute('UPDATE tracks SET created_at=? WHERE id=?', (track['created_at'], track['id']))
                    imported += 1
                finally:
                    target.unlink(missing_ok=True)
        return {'imported': imported, 'playlists': playlists}

    def load_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute('SELECT payload FROM download_jobs ORDER BY rowid').fetchall()
        return sorted((json.loads(row['payload']) for row in rows), key=lambda job: job['created_at'])

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
        if not isinstance(filename, str) or not filename or re.search(r'[\\/:\x00-\x1f]', filename) or filename in ('.', '..'):
            raise ValueError("Invalid stored audio filename")
        path = self.tracks_dir / filename
        if path.resolve().parent != self.tracks_dir.resolve():
            raise ValueError("Audio file is outside the library")
        return path

    def _name_audio(self, track: dict[str, Any]) -> None:
        source = self.path_for(track)
        if not source.is_file():
            return
        title = str(track.get('title') or 'Untitled')
        artist = str(track.get('artist') or 'Unknown artist')
        title = re.sub(r'^' + re.escape(artist) + r'\s*[-–—:]\s*', '', title, count=1, flags=re.IGNORECASE).strip() or title
        stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', artist + ' - ' + title)
        stem = ' '.join(stem.split()).strip(' .')
        stem = stem.encode('utf-8')[:170].decode('utf-8', errors='ignore').rstrip(' .') or 'Untitled'
        target = None
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                number = 1
                while True:
                    suffix = '' if number == 1 else f' ({number})'
                    candidate = self.tracks_dir / (stem + suffix + source.suffix.lower())
                    try:
                        # Exclusive creation prevents overwriting another song.
                        with candidate.open('xb') as output:
                            target = candidate
                            with source.open('rb') as original:
                                shutil.copyfileobj(original, output, 1024 * 1024)
                            output.flush()
                            os.fsync(output.fileno())
                        break
                    except FileExistsError:
                        number += 1
                db.execute('UPDATE tracks SET filename = ? WHERE id = ?', (target.name, track['id']))
        except Exception:
            if target is not None:
                target.unlink(missing_ok=True)
            raise
        # The database commit precedes removal, so a failed commit keeps the old file.
        source.unlink()
        track['filename'] = target.name

    def add_track(self, track: dict[str, Any]) -> None:
        fields = (
            "id", "video_id", "title", "artist", "album", "album_artist",
            "artwork_url", "track_number", "release_date", "release_id", "release_type",
            "duration", "filename", "bytes", "extension", "codec", "abr",
        )
        with self._connect() as db:
            db.execute(
                f"INSERT INTO tracks ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                tuple(track.get(f) for f in fields),
            )
        self._name_audio(track)
        self.sync_music_folder()

    def delete_track(self, track_id: str) -> bool:
        track = self.get_track(track_id)
        if track is None:
            return False
        path = self.path_for(track)
        path.unlink(missing_ok=True)
        with self._connect() as db:
            db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
            db.execute("DELETE FROM download_jobs WHERE id = ?", (track_id,))
            db.execute("DELETE FROM folder_copies WHERE track_id = ?", (track_id,))
        return True
