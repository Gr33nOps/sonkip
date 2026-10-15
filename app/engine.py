"""yt-dlp search and non-transcoding audio download engine."""
from __future__ import annotations

import re
import os
import threading
import uuid
import json
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL

from .storage import MusicStore

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

# Android does not bundle the desktop browser-based token provider.
COOKIE_FREE_YOUTUBE_ARGS = {
    "youtube": {"player_client": ["android_vr", "web_safari"]},
}
AUTHENTICATED_YOUTUBE_ARGS = {
    "youtube": {"player_client": ["web_safari", "mweb"]},
}
DESKTOP_YOUTUBE_ARGS = {
    "youtube": {"player_client": ["mweb"]},
}


def youtube_access_options(cookiefile: Path | None = None) -> dict[str, Any]:
    runtime = os.environ.get("SONKIP_QUICKJS")
    options = {"js_runtimes": {"quickjs": {"path": runtime}}} if runtime else {}
    if os.environ.get("SONKIP_ANDROID_TOKENS") == "1":
        return {
            **options,
            **({"cookiefile": str(cookiefile)} if cookiefile and cookiefile.is_file() else {}),
            "extractor_args": DESKTOP_YOUTUBE_ARGS,
        }
    if cookiefile and cookiefile.is_file():
        return {
            **options,
            "cookiefile": str(cookiefile),
            "extractor_args": AUTHENTICATED_YOUTUBE_ARGS if runtime else DESKTOP_YOUTUBE_ARGS,
        }
    # mweb exposes direct audio streams with a per-video PO token generated
    # automatically by the installed local browser provider. Safari may offer
    # only obsolete direct URLs (403), even when it generates a valid token.
    return {**options, "extractor_args": COOKIE_FREE_YOUTUBE_ARGS if runtime else DESKTOP_YOUTUBE_ARGS}


def get_stream_url(video_id: str, cookiefile: Path | None = None) -> str | None:
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
        **youtube_access_options(cookiefile),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        return info.get("url") if isinstance(info, dict) else None


def search_music(query: str, cookiefile: Path | None = None) -> list[dict[str, Any]]:
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
        **youtube_access_options(cookiefile),
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


def extract_playlist(url: str, cookiefile: Path | None = None) -> dict[str, Any]:
    """Return video entries from a YouTube or YouTube Music playlist."""
    clean = url.strip()
    if not URL_RE.fullmatch(clean):
        raise ValueError("Enter a valid playlist URL")
    parsed = urlparse(clean)
    if parsed.hostname in ('open.spotify.com', 'soundcloud.com', 'www.soundcloud.com'):
        return _import_playlist(parsed, cookiefile)
    if parsed.hostname not in ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be"):
        raise ValueError("Use a public YouTube, Spotify, or SoundCloud playlist link. Other services are not supported yet.")
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if not playlist_id:
        raise ValueError("This link has no playlist. Open the playlist in YouTube, choose Share, and copy its link.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", playlist_id):
        raise ValueError("Invalid playlist link")
    clean = f"https://www.youtube.com/playlist?list={playlist_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": False,
        "socket_timeout": 30,
        **youtube_access_options(cookiefile),
    }
    with YoutubeDL(opts) as ydl:
        data = ydl.extract_info(clean, download=False)
    entries = []
    seen = set()
    for item in (data or {}).get("entries") or []:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        if isinstance(video_id, str) and VIDEO_ID_RE.fullmatch(video_id) and video_id not in seen:
            seen.add(video_id)
            entries.append({
                "video_id": video_id,
                "title": str(item.get("title") or "Untitled"),
                "artist": str(item.get("uploader") or item.get("channel") or "Unknown artist"),
            })
    if not entries:
        raise ValueError("No downloadable songs were found in that playlist")
    return {"title": str((data or {}).get("title") or "Playlist"), "entries": entries}


def _words(value: str) -> set[str]:
    return set(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def _match_track(track: dict, cookiefile: Path | None) -> dict | None:
    candidates = search_music(f"{track['artist']} {track['title']}", cookiefile)
    title_words, artist_words = _words(track['title']), _words(track['artist'])
    versions = {'live', 'cover', 'remix', 'slowed', 'instrumental', 'karaoke', 'nightcore', 'demo', 'sped'}
    best, best_score = None, 0
    for candidate in candidates:
        words = _words(candidate['title'])
        if (words & versions) - (title_words & versions):
            continue
        title_score = len(title_words & words) / max(1, len(title_words))
        artist_score = len(artist_words & (words | _words(candidate['artist']))) / max(1, len(artist_words))
        if title_score < .8 or artist_score < .5:
            continue
        expected, actual = track.get('duration'), candidate.get('duration')
        if expected and actual and abs(expected - actual) > max(25, expected * .15):
            continue
        score = title_score + artist_score
        if score > best_score:
            best, best_score = candidate, score
    return best


def _import_playlist(parsed, cookiefile: Path | None) -> dict:
    if parsed.scheme != 'https' or parsed.username or parsed.port not in (None, 443):
        raise ValueError('Use the HTTPS playlist link from the music service')
    if parsed.hostname == 'open.spotify.com':
        match = re.fullmatch(r'/(?:intl-[a-z]+/)?(playlist|album)/([A-Za-z0-9]{22})/?', parsed.path)
        if not match:
            raise ValueError('Paste a public Spotify playlist or album link')
        url = f'https://open.spotify.com/embed/{match[1]}/{match[2]}'
        with urllib.request.urlopen(url, timeout=30) as response:
            html = response.read(8 * 1024 * 1024).decode('utf-8')
        payload = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not payload:
            raise ValueError('Spotify did not expose this playlist. Check that it is public.')
        entity = json.loads(payload[1]).get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
        source, title = 'Spotify', entity.get('name') or 'Spotify playlist'
        tracks = [{'title': t['title'], 'artist': t['subtitle'], 'duration': t.get('duration', 0) / 1000}
                  for t in entity.get('trackList', []) if t.get('title') and t.get('subtitle')]
        note = 'Spotify imports the tracks exposed by its public embed; large playlists may be incomplete.'
    else:
        if not re.fullmatch(r'/[\w-]+/sets/[\w-]+/?', parsed.path):
            raise ValueError('Paste a public SoundCloud set or album link')
        with YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True,
                        'socket_timeout': 25, 'extract_flat': False, 'ignoreerrors': False}) as ydl:
            data = ydl.extract_info('https://soundcloud.com' + parsed.path, download=False)
        source, title = 'SoundCloud', data.get('title') or 'SoundCloud playlist'
        # SoundCloud may report a 30-second preview duration, not the full song.
        tracks = [{'title': t.get('track') or t['title'], 'artist': t.get('artist') or t.get('uploader') or ''}
                  for t in data.get('entries', []) if t and t.get('title')]
        note = 'SoundCloud supplies track names only; audio is matched on YouTube.'
    if not tracks:
        raise ValueError('No public track names were found in this playlist')
    def match_one(track):
        try:
            found = _match_track(track, cookiefile)
            return ({**found, 'matched_from': source, 'source_title': track['title']} if found else None,
                    {**track, 'reason': 'No close YouTube match found'})
        except Exception:
            return None, {**track, 'reason': 'YouTube search failed; try importing again'}
    # Initialize yt-dlp's global plugin registry before concurrent searches.
    matches = [match_one(tracks[0])]
    with ThreadPoolExecutor(max_workers=3) as pool:
        matches.extend(pool.map(match_one, tracks[1:]))
    entries = [found for found, _ in matches if found]
    unmatched = [missing for found, missing in matches if not found]
    if not entries:
        raise ValueError('No close YouTube matches were found. Try searching for a song by title and artist.')
    return {'title': title, 'entries': entries, 'unmatched': unmatched, 'source_count': len(tracks),
            'source': source, 'notice': note + ' Matches may be different uploads or editions.'}


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
            # Keep terminal jobs for the lifetime of the process so playlist
            # clients can poll every result, including large batches.
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
            if os.environ.get("SONKIP_ANDROID_TOKENS") == "1":
                # Fail before extraction, rather than repeating a failed browser
                # startup for every token context and leaving jobs "starting".
                from java import jclass
                jclass("io.github.gr33nops.sonkip.PublicTokenProvider").awaitReady()
            opts = {
                # Some public clients expose only combined audio/video. Keep
                # that original file rather than failing or requiring FFmpeg.
                "format": "bestaudio/best[acodec!=none]",
                "hls_prefer_native": True,
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
                **youtube_access_options(self.store.youtube_cookies_path),
            }
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            except Exception as first_error:
                if "403" not in str(first_error):
                    raise
                # A listed direct stream can expire or reject this client while
                # the same video's public HLS stream is still available.
                for partial in self.store.tracks_dir.glob(job_id + ".*"):
                    if partial.is_file():
                        partial.unlink()
                self._update(job_id, status="starting", percent=0)
                try:
                    with YoutubeDL({**opts, "format": "best[protocol^=m3u8][acodec!=none]"}) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                except Exception:
                    raise RuntimeError(
                        "YouTube rejected this download and no working public alternative was available. "
                        "Try again later, or use Access for media your account is allowed to download."
                    ) from first_error
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
