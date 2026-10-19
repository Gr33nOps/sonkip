"""Small localhost HTTP server used by the embedded Android app."""
from __future__ import annotations

import json
import mimetypes
import re
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .engine import DownloadManager, VIDEO_ID_RE, extract_playlist, get_stream_url, search_music, resolve_music_metadata
from .storage import MusicStore

TRACK_ROUTE = re.compile(r"^/api/tracks/([0-9a-f]{32})/(audio|file)$")
JOB_ROUTE = re.compile(r"^/api/jobs/([0-9a-f]{32})$")
DELETE_TRACK_ROUTE = re.compile(r"^/api/tracks/([0-9a-f]{32})$")


class AndroidServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, store: MusicStore, static_dir: Path):
        super().__init__(address, handler)
        self.store = store
        self.manager = DownloadManager(store)
        self.playlist_previews: dict[str, dict[str, Any]] = {}
        self.static_dir = static_dir.resolve()


class AndroidRequestHandler(BaseHTTPRequestHandler):
    server: AndroidServer

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _static_file(self, relative: str) -> None:
        requested = (self.server.static_dir / unquote(relative)).resolve()
        if self.server.static_dir not in requested.parents and requested != self.server.static_dir:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        if not requested.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        body = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if requested.suffix == ".js":
            content_type = "text/javascript"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _audio_file(self, track_id: str, download: bool) -> None:
        track = self.server.store.get_track(track_id)
        if not track:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Track not found"})
            return
        path = self.server.store.path_for(track)
        if not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Audio file missing"})
            return

        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = min(int(match.group(2)), size - 1)
            if start > end or start >= size:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            status = HTTPStatus.PARTIAL_CONTENT

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            safe_title = "".join(
                ch if (ch.isalnum() or ch in " -_().") else "_" for ch in track["title"]
            )[:90].strip() or "Audio"
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{safe_title}.{track["extension"]}"',
            )
        self.end_headers()
        with path.open("rb") as audio:
            audio.seek(start)
            remaining = length
            while remaining:
                chunk = audio.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "platform": "android",
                    "library_path": str(self.server.store.tracks_dir),
                },
            )
            return
        if path == "/api/auth/youtube":
            self._json(
                HTTPStatus.OK,
                {"connected": self.server.store.youtube_auth_connected()},
            )
            return
        if path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if len(query) < 2 or len(query) > 120:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "Enter at least 2 characters"})
                return
            try:
                self._json(
                    HTTPStatus.OK,
                    {
                        "results": search_music(
                            query, self.server.store.youtube_cookies_path
                        )
                    },
                )
            except Exception as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"detail": f"Search provider unavailable: {str(exc)[:220]}"})
            return
        if path == "/api/jobs":
            self._json(HTTPStatus.OK, {"jobs": self.server.manager.list_jobs()})
            return
        job_match = JOB_ROUTE.fullmatch(path)
        if job_match:
            job = self.server.manager.get_job(job_match.group(1))
            if job:
                self._json(HTTPStatus.OK, job)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "Job not found"})
            return
        if path == "/api/tracks":
            self._json(HTTPStatus.OK, {"tracks": self.server.store.list_tracks()})
            return
        track_match = TRACK_ROUTE.fullmatch(path)
        if track_match:
            self._audio_file(track_match.group(1), track_match.group(2) == "file")
            return
        if path.startswith("/api/stream/"):
            video_id = path.rsplit("/", 1)[-1]
            if not VIDEO_ID_RE.fullmatch(video_id):
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "Invalid video ID"})
                return
            local = next(
                (track for track in self.server.store.list_tracks() if track.get("video_id") == video_id),
                None,
            )
            if local:
                self._json(HTTPStatus.OK, {"url": f"/api/tracks/{local['id']}/audio", "local": True})
                return
            try:
                stream_url = get_stream_url(
                    video_id, self.server.store.youtube_cookies_path
                )
                if not stream_url:
                    self._json(HTTPStatus.NOT_FOUND, {"detail": "Audio stream not found"})
                else:
                    self._json(HTTPStatus.OK, {"url": stream_url, "local": False})
            except Exception as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"detail": f"Stream extraction failed: {str(exc)[:150]}"})
            return
        if path == "/":
            self._static_file("index.html")
            return
        if path.startswith("/static/"):
            self._static_file(path.removeprefix("/static/"))
            return
        self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._body()
        if path == '/api/jobs/resume-interrupted':
            self._json(HTTPStatus.OK, {'job_ids': self.server.manager.resume_interrupted()})
            return
        if path == '/api/jobs/retry-failed':
            self._json(HTTPStatus.OK, {'job_ids': self.server.manager.retry_failed()})
            return
        cancel_match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})/cancel', path)
        if cancel_match:
            try:
                self.server.manager.cancel(cancel_match.group(1))
                self._json(HTTPStatus.OK, {'ok': True})
            except ValueError as exc:
                self._json(HTTPStatus.NOT_FOUND, {'detail': str(exc)})
            return
        if path == "/api/downloads":
            try:
                job_id = self.server.manager.start(
                    str(body.get("video_id", "")),
                    str(body.get("audio_format", "m4a")),
                    body.get("embed_metadata", True) is not False,
                    body.get("metadata") if isinstance(body.get("metadata"), dict) else None,
                )
            except ValueError as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.TOO_MANY_REQUESTS, {"detail": str(exc)})
            else:
                self._json(HTTPStatus.ACCEPTED, {"job_id": job_id})
            return
        if path == "/api/auth/youtube":
            try:
                self.server.store.save_youtube_cookies(str(body.get("cookies", "")))
            except ValueError as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)})
            else:
                self._json(HTTPStatus.OK, {"connected": True})
            return
        if path == "/api/playlists":
            try:
                playlist = extract_playlist(
                    str(body.get("url", "")),
                    self.server.store.youtube_cookies_path,
                )
                entries = []
                for item in playlist["entries"]:
                    metadata = resolve_music_metadata(item)
                    entries.append({**item, **metadata, "thumbnail": metadata["artwork_url"], "selected": True})
                preview_id = uuid.uuid4().hex
                self.server.playlist_previews[preview_id] = {"title": playlist["title"], "entries": entries}
                while len(self.server.playlist_previews) > 20:
                    self.server.playlist_previews.pop(next(iter(self.server.playlist_previews)))
            except ValueError as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.TOO_MANY_REQUESTS, {"detail": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"detail": f"Playlist provider unavailable: {str(exc)[:220]}"})
            else:
                self._json(
                    HTTPStatus.OK,
                    {"preview_id": preview_id, "title": playlist["title"], "count": len(entries), "entries": entries,
                     "unmatched": playlist.get("unmatched", []), "notice": playlist.get("notice", ""),
                     "source_count": playlist.get("source_count", len(entries)),
                     "artwork_url": playlist.get("artwork_url", "")},
                )
            return
        if path == "/api/playlists/download":
            preview = self.server.playlist_previews.get(str(body.get("preview_id", "")))
            video_ids = body.get("video_ids")
            if preview is None:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "This playlist preview expired. Load it again."})
                return
            if (not isinstance(video_ids, list) or not video_ids or len(video_ids) > 1000
                    or any(not isinstance(value, str) or not VIDEO_ID_RE.fullmatch(value) for value in video_ids)):
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "Choose at least one valid song"})
                return
            requested = set(video_ids)
            entries = [entry for entry in preview["entries"] if entry["video_id"] in requested]
            if len(entries) != len(requested):
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "The selection does not belong to this playlist preview"})
                return
            try:
                jobs = [{**entry, "job_id": self.server.manager.start(
                    entry["video_id"], str(body.get("audio_format", "m4a")),
                    body.get("embed_metadata", True) is not False, entry
                )} for entry in entries]
            except ValueError as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.TOO_MANY_REQUESTS, {"detail": str(exc)})
            else:
                self._json(HTTPStatus.ACCEPTED, {"title": preview["title"], "count": len(jobs), "jobs": jobs})
            return
        if path == "/api/tracks/delete-selected":
            track_ids = body.get("track_ids")
            if (not isinstance(track_ids, list) or len(track_ids) > 10000
                    or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value) for value in track_ids)):
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "Invalid track selection"})
            else:
                self._json(HTTPStatus.OK, {"deleted": self.server.manager.delete_tracks(track_ids)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/auth/youtube":
            self.server.store.clear_youtube_cookies()
            self._json(HTTPStatus.OK, {"connected": False})
            return
        match = DELETE_TRACK_ROUTE.fullmatch(path)
        if not match:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        if self.server.manager.delete_tracks([match.group(1)]):
            self._json(HTTPStatus.OK, {"deleted": True})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Track not found"})


def create_android_server(
    data_dir: Path | str,
    static_dir: Path | str,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> AndroidServer:
    """Create the Android-only localhost server without starting its event loop."""
    return AndroidServer(
        (host, port),
        AndroidRequestHandler,
        MusicStore(Path(data_dir)),
        Path(static_dir),
    )
