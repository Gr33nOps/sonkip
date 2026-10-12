"""yt-dlp search and non-transcoding audio download engine."""
from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from yt_dlp import YoutubeDL

from .storage import MusicStore

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

# These clients expose ordinary public streams without importing browser
# cookies. android_vr is the most reliable cookie-free option; web_safari is
# retained as a fallback for videos which that client doesn't expose.
COOKIE_FREE_YOUTUBE_ARGS = {
    "youtube": {"player_client": ["android_vr", "web_safari"]},
}


def get_stream_url(video_id: str) -> str | None:
    """Extract direct audio stream URL for preview playback."""
    if not VIDEO_ID_RE.fullmatch(video_id):
        return None
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "skip_download": True,
        "socket_timeout": 15,
        "noplaylist": True,
        "extractor_args": COOKIE_FREE_YOUTUBE_ARGS,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        return info.get("url") if isinstance(info, dict) else None


def search_music(query: str) -> list[dict[str, Any]]:
    """Search YouTube by song name or direct link; no download occurs here."""
    clean = query.strip()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
        "playlistend": 15,
        "socket_timeout": 20,
        "noplaylist": False,
        "extractor_args": COOKIE_FREE_YOUTUBE_ARGS,
    }

    yt_match = re.search(r"(?:v=|\/|youtu\.be\/|^)([A-Za-z0-9_-]{11})(?:[&?]|$)", clean)
    if yt_match and ("http" in clean or "youtu" in clean or VIDEO_ID_RE.fullmatch(clean)):
        vid = yt_match.group(1)
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                if info and isinstance(info, dict):
                    duration = info.get("duration")
                    return [{
                        "video_id": vid,
                        "title": str(info.get("title") or "Untitled"),
                        "artist": str(info.get("uploader") or info.get("channel") or "Unknown artist"),
                        "duration": int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None,
                        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    }]
        except Exception:
            pass

    with YoutubeDL(opts) as ydl:
        data = ydl.extract_info(f"ytsearch15:{clean}", download=False)

    results = []
    for item in (data or {}).get("entries") or []:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
            continue
        duration = item.get("duration")
        results.append({
            "video_id": video_id,
            "title": str(item.get("title") or "Untitled"),
            "artist": str(item.get("uploader") or item.get("channel") or "Unknown artist"),
            "duration": int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        })
    return results


def extract_playlist(url: str) -> dict[str, Any]:
    """Return downloadable entries from any playlist URL supported by yt-dlp."""
    clean = url.strip()
    if not URL_RE.fullmatch(clean):
        raise ValueError("Enter a valid playlist URL")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "extractor_args": COOKIE_FREE_YOUTUBE_ARGS,
    }
    with YoutubeDL(opts) as ydl:
        data = ydl.extract_info(clean, download=False)
    entries = []
    for item in (data or {}).get("entries") or []:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        if isinstance(video_id, str) and VIDEO_ID_RE.fullmatch(video_id):
            entries.append({
                "video_id": video_id,
                "title": str(item.get("title") or "Untitled"),
                "artist": str(item.get("uploader") or item.get("channel") or "Unknown artist"),
            })
    if not entries:
        raise ValueError("No downloadable songs were found in that playlist")
    return {"title": str((data or {}).get("title") or "Playlist"), "entries": entries}


class DownloadManager:
    def __init__(self, store: MusicStore):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sonkip-download")
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, Any]] = {}

    def list_jobs(self):
        with self.lock:
            return [dict(job) for job in reversed(list(self.jobs.values()))]

    def get_job(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def _update(self, job_id: str, **changes):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(changes)

    def start(self, video_id: str):
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("Invalid video ID")
        job_id = uuid.uuid4().hex
        with self.lock:
            # Keep only the most recent completed/failed tasks in memory.
            for key, job in list(self.jobs.items()):
                if len(self.jobs) < 60:
                    break
                if job["status"] in ("complete", "error"):
                    del self.jobs[key]
            if len(self.jobs) >= 60:
                raise RuntimeError("Too many active jobs; retry later")
            self.jobs[job_id] = {
                "id": job_id,
                "video_id": video_id,
                "status": "queued",
                "percent": 0,
                "speed": None,
                "eta": None,
                "error": None,
                "track_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        self.pool.submit(self._run, job_id, video_id)
        return job_id

    def _run(self, job_id: str, video_id: str):
        self._update(job_id, status="starting")

        def progress(info):
            if info.get("status") == "finished":
                self._update(job_id, status="processing", percent=100)
            elif info.get("status") == "downloading":
                done = info.get("downloaded_bytes") or 0
                total = info.get("total_bytes") or info.get("total_bytes_estimate") or 0
                pct = min(99.9, round(done / total * 100, 1)) if total else 0
                self._update(job_id, status="downloading", percent=pct,
                             speed=info.get("speed"), eta=info.get("eta"))

        try:
            opts = {
                "format": "bestaudio",  # never transcode or downgrade the audio
                "outtmpl": str(self.store.tracks_dir / f"{job_id}.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "retries": 3,
                "fragment_retries": 3,
                "socket_timeout": 30,
                "progress_hooks": [progress],
                "restrictfilenames": True,
                "overwrites": False,
                "extractor_args": COOKIE_FREE_YOUTUBE_ARGS,
            }
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            if not info:
                raise RuntimeError("No audio information was returned")

            matching = [p for p in self.store.tracks_dir.glob(job_id + ".*")
                        if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".tmp")
                        and not p.name.endswith(".part-Frag0")]
            if not matching:
                raise RuntimeError("Download ended without an audio file")
            path = max(matching, key=lambda p: p.stat().st_size)
            selected = (info.get("requested_downloads") or [{}])[0]
            codec = selected.get("acodec") or info.get("acodec")
            abr = selected.get("abr") or info.get("abr")
            track = {
                "id": job_id,
                "video_id": video_id,
                "title": str(info.get("track") or info.get("title") or "Untitled"),
                "artist": str(info.get("artist") or info.get("uploader") or "Unknown artist"),
                "duration": info.get("duration"),
                "filename": path.name,
                "bytes": path.stat().st_size,
                "extension": path.suffix.lstrip(".").lower(),
                "codec": str(codec) if codec else None,
                "abr": float(abr) if isinstance(abr, (float, int)) else None,
            }
            self.store.add_track(track)
            self._update(job_id, status="complete", percent=100, track_id=job_id)
        except Exception as exc:
            # yt-dlp can fail due to deleted, blocked or unavailable content.
            self._update(job_id, status="error", error=str(exc)[:350])
            # Remove only this job's unfinished files; do not touch completed tracks.
            for path in self.store.tracks_dir.glob(job_id + ".*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
