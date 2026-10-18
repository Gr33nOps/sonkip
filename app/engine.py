"""yt-dlp search, audio download, and optional local conversion engine."""
from __future__ import annotations

import re
import os
import base64
import shutil
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
AUDIO_FORMATS = {"original", "mp3", "m4a", "opus", "flac", "webm"}
CONVERTED_AUDIO_FORMATS = {"mp3", "m4a", "opus", "flac"}
MAX_ARTWORK_BYTES = 8 * 1024 * 1024

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


def normalize_audio_format(value: str | None) -> str:
    audio_format = (value or "original").strip().lower()
    if audio_format not in AUDIO_FORMATS:
        raise ValueError("Choose Original, MP3, M4A, Opus, or FLAC")
    return audio_format


def audio_download_options(audio_format: str) -> dict[str, Any]:
    """Return yt-dlp options which produce the requested audio container."""
    audio_format = normalize_audio_format(audio_format)
    if audio_format == "original":
        return {"format": "bestaudio/best[acodec!=none]"}
    if audio_format == "webm":
        return {"format": "bestaudio[ext=webm][acodec^=opus]/bestaudio[ext=webm]"}
    if os.environ.get("SONKIP_ANDROID_TOKENS") == "1" and audio_format == "m4a":
        return {
            "format": (
                "bestaudio[ext=m4a][acodec!=none]/"
                "bestaudio[acodec^=mp4a][ext=m4a]/"
                "best[ext=mp4][acodec^=mp4a]"
            )
        }
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError, OSError):
            pass
    if not ffmpeg:
        raise RuntimeError(
            f"{audio_format.upper()} conversion is unavailable on this device. "
            "Choose Original, or install FFmpeg and restart Sonkip."
        )
    postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
    if audio_format != "flac":
        postprocessor["preferredquality"] = "160" if audio_format == "opus" else "192"
    return {
        "format": "bestaudio/best[acodec!=none]",
        "ffmpeg_location": ffmpeg,
        "postprocessors": [postprocessor],
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


def _music_details(info: dict[str, Any]) -> dict[str, Any]:
    artist = str(info.get("artist") or info.get("uploader") or "Unknown artist").strip()
    artist = re.sub(r"\s+-\s+Topic$", "", artist, flags=re.IGNORECASE).strip() or "Unknown artist"
    title = str(info.get("track") or info.get("title") or "Untitled").strip()
    title = re.sub(
        r"^" + re.escape(artist) + r"\s*[-–—:]\s*",
        "",
        title,
        count=1,
        flags=re.IGNORECASE,
    ).strip() or title
    year = info.get("release_year")
    if not year and info.get("release_date"):
        year = str(info["release_date"])[:4]
    return {
        "title": title,
        "artist": artist,
        "album": str(info.get("album") or "").strip(),
        "track_number": info.get("track_number"),
        "year": str(year).strip() if year else "",
        "genre": str(info.get("genre") or "").strip(),
    }


def _download_artwork(video_id: str) -> tuple[bytes, str] | None:
    request = urllib.request.Request(
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        headers={"User-Agent": "Sonkip/2"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        artwork = response.read(MAX_ARTWORK_BYTES + 1)
        content_type = str(response.headers.get("Content-Type", "image/jpeg")).split(";", 1)[0].lower()
    if not artwork or len(artwork) > MAX_ARTWORK_BYTES or content_type not in ("image/jpeg", "image/png"):
        return None
    return artwork, content_type


def _embed_music_metadata(path: Path, info: dict[str, Any], video_id: str) -> bool:
    extension = path.suffix.lower()
    if extension not in (".m4a", ".mp4", ".mp3", ".flac", ".opus", ".ogg"):
        return False
    details = _music_details(info)
    try:
        artwork = _download_artwork(video_id)
    except (OSError, ValueError):
        artwork = None
    if extension in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9nam"] = [details["title"]]
        audio.tags["\xa9ART"] = [details["artist"]]
        audio.tags["aART"] = [details["artist"]]
        if details["album"]:
            audio.tags["\xa9alb"] = [details["album"]]
        if isinstance(details["track_number"], int) and details["track_number"] > 0:
            audio.tags["trkn"] = [(details["track_number"], 0)]
        if details["year"]:
            audio.tags["\xa9day"] = [details["year"]]
        if details["genre"]:
            audio.tags["\xa9gen"] = [details["genre"]]
        if artwork:
            data, content_type = artwork
            image_format = MP4Cover.FORMAT_PNG if content_type == "image/png" else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(data, imageformat=image_format)]
        audio.save()
    elif extension == ".mp3":
        from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TRCK
        from mutagen.mp3 import MP3

        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        for frame in ("TIT2", "TPE1", "TALB", "TRCK", "TDRC", "TCON", "APIC"):
            audio.tags.delall(frame)
        audio.tags.add(TIT2(encoding=3, text=details["title"]))
        audio.tags.add(TPE1(encoding=3, text=details["artist"]))
        if details["album"]:
            audio.tags.add(TALB(encoding=3, text=details["album"]))
        if isinstance(details["track_number"], int) and details["track_number"] > 0:
            audio.tags.add(TRCK(encoding=3, text=str(details["track_number"])))
        if details["year"]:
            audio.tags.add(TDRC(encoding=3, text=details["year"]))
        if details["genre"]:
            audio.tags.add(TCON(encoding=3, text=details["genre"]))
        if artwork:
            data, content_type = artwork
            audio.tags.add(APIC(encoding=3, mime=content_type, type=3, desc="Cover", data=data))
        audio.save(v2_version=3)
    else:
        from mutagen.flac import FLAC, Picture
        from mutagen.oggopus import OggOpus

        audio = FLAC(path) if extension == ".flac" else OggOpus(path)
        audio["title"] = [details["title"]]
        audio["artist"] = [details["artist"]]
        if details["album"]:
            audio["album"] = [details["album"]]
        if isinstance(details["track_number"], int) and details["track_number"] > 0:
            audio["tracknumber"] = [str(details["track_number"])]
        if details["year"]:
            audio["date"] = [details["year"]]
        if details["genre"]:
            audio["genre"] = [details["genre"]]
        if artwork:
            data, content_type = artwork
            picture = Picture()
            picture.type = 3
            picture.mime = content_type
            picture.desc = "Cover"
            picture.data = data
            if extension == ".flac":
                audio.clear_pictures()
                audio.add_picture(picture)
            else:
                audio["metadata_block_picture"] = [
                    base64.b64encode(picture.write()).decode("ascii")
                ]
        audio.save()
    return True


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
            "channel_is_verified": bool(item.get('channel_is_verified')),
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
        uploader_words = _words(candidate['artist'])
        artist_channel = artist_words.issubset(uploader_words)
        if artist_channel:
            score += .2
            if candidate.get('channel_is_verified') or 'topic' in uploader_words:
                score += .3
        if expected and actual:
            score += .1 * max(0, 1 - abs(expected - actual) / max(1, expected))
        if score > best_score:
            best = {**candidate, 'needs_review': not (expected and actual and title_score == 1 and artist_score == 1)}
            best_score = score
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
        self.cancellations = {}
        self.futures = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        for job in store.load_jobs():
            if job['status'] not in ('complete', 'error'):
                job.update(status='error', speed=None, eta=None, interrupted=True,
                           error='Download interrupted. Retry to continue the saved partial file.')
                store.save_job(job)
            self.jobs[job['id']] = job

    def list_jobs(self):
        with self.lock:
            return [dict(job) for job in reversed(list(self.jobs.values()))]

    def get_job(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def delete_tracks(self, track_ids: list[str]) -> list[str]:
        deleted = []
        for track_id in dict.fromkeys(track_ids):
            if not self.store.delete_track(track_id):
                continue
            with self.lock:
                self.jobs.pop(track_id, None)
                self.cancellations.pop(track_id, None)
                self.futures.pop(track_id, None)
            deleted.append(track_id)
        return deleted

    def _update(self, job_id: str, **changes):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(changes)
                self.store.save_job(self.jobs[job_id])

    def start(
        self,
        video_id: str,
        audio_format: str = "original",
        embed_metadata: bool = True,
    ):
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("Invalid video ID")
        audio_format = normalize_audio_format(audio_format)
        job_id = uuid.uuid4().hex
        with self.lock:
            expected_extension = audio_format if audio_format != "original" else None
            saved = next((track for track in self.store.list_tracks()
                          if track['video_id'] == video_id
                          and (expected_extension is None or track['extension'] == expected_extension)), None)
            if saved:
                job_id = saved['id']
                self.jobs[job_id] = {
                    'id': job_id, 'video_id': video_id, 'status': 'complete', 'percent': 100,
                    'speed': None, 'eta': None, 'error': None, 'track_id': saved['id'],
                    'created_at': datetime.now(timezone.utc).isoformat(), 'already_saved': True,
                    'title': saved['title'], 'artist': saved['artist'], 'audio_format': audio_format,
                    'embed_metadata': bool(embed_metadata),
                }
                self.store.save_job(self.jobs[job_id])
                return job_id
            for existing in self.jobs.values():
                if existing['video_id'] != video_id or existing.get('audio_format', 'original') != audio_format:
                    continue
                if existing['status'] not in ('error', 'complete'):
                    return existing['id']
                if existing['status'] == 'error':
                    job_id = existing['id']
                    future = self.futures.get(job_id)
                    if future is not None and not future.done():
                        raise ValueError('This download is still stopping. Please retry in a moment.')
                    break
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
                "audio_format": audio_format,
                "embed_metadata": bool(embed_metadata),
            }
            self.store.save_job(self.jobs[job_id])
            self.cancellations[job_id] = threading.Event()
            self.futures[job_id] = self.pool.submit(
                self._run, job_id, video_id, audio_format, bool(embed_metadata)
            )
        return job_id

    def cancel(self, job_id: str):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise ValueError('Download not found')
            if job['status'] == 'complete':
                return
            event = self.cancellations.get(job_id)
            if event is not None:
                event.set()
            job.update(status='error', cancelled=True, error='Cancelled. Retry to resume.', speed=None, eta=None)
            self.store.save_job(job)

    def retry_failed(self):
        retried = []
        for job in self.list_jobs():
            if job['status'] == 'error' and not job.get('cancelled'):
                try:
                    retried.append(self.start(
                        job['video_id'],
                        job.get('audio_format', 'original'),
                        job.get('embed_metadata', True),
                    ))
                except ValueError:
                    # A cancelled worker may still be returning from a network call.
                    continue
        return retried

    def resume_interrupted(self):
        return [self.start(
                    job['video_id'],
                    job.get('audio_format', 'original'),
                    job.get('embed_metadata', True),
                ) for job in self.list_jobs()
                if job.get('interrupted') and not job.get('cancelled') and job['status'] == 'error']

    def _run(
        self,
        job_id: str,
        video_id: str,
        audio_format: str = "original",
        embed_metadata: bool = True,
    ):
        cancelled = self.cancellations[job_id]
        if cancelled.is_set():
            return
        self._update(job_id, status="starting")

        def progress(info):
            if cancelled.is_set():
                raise RuntimeError('Cancelled. Retry to resume.')
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
            format_options = audio_download_options(audio_format)
            opts = {
                # Original mode may keep a combined source when no separate
                # audio stream is available; selected formats are converted.
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
                **format_options,
            }
            try:
                for attempt in range(3):
                    if cancelled.is_set():
                        raise RuntimeError('Cancelled. Retry to resume.')
                    try:
                        with YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                        break
                    except Exception as transient:
                        message = str(transient).lower()
                        retryable = any(word in message for word in (
                            'timed out', 'timeout', 'connection reset', 'connection aborted',
                            'temporary failure', 'network is unreachable', 'http error 502', 'http error 503'))
                        if cancelled.is_set() or not retryable or attempt == 2:
                            raise
                        self._update(job_id, status='starting', attempt=attempt + 2,
                                     error='Connection interrupted; retrying…', speed=None, eta=None)
                        cancelled.wait(2 ** attempt)
            except Exception as first_error:
                if cancelled.is_set() or "403" not in str(first_error) or audio_format != "original":
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
            if cancelled.is_set():
                raise RuntimeError('Cancelled. Retry to resume.')

            matching = [p for p in self.store.tracks_dir.glob(job_id + ".*")
                        if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".tmp")
                        and '.part' not in p.name]
            if not matching:
                raise RuntimeError("Download ended without an audio file")
            path = max(matching, key=lambda p: p.stat().st_size)
            if (os.environ.get("SONKIP_ANDROID_TOKENS") == "1"
                    and audio_format == "m4a" and path.suffix.lower() != ".m4a"):
                from java import jclass
                target = path.with_suffix(".m4a")
                target.unlink(missing_ok=True)
                jclass("io.github.gr33nops.sonkip.AndroidAudioExtractor").extractM4a(
                    str(path), str(target)
                )
                if not target.is_file() or target.stat().st_size == 0:
                    raise RuntimeError("Android could not extract the AAC audio track")
                path.unlink()
                path = target
            metadata_embedded = False
            if embed_metadata:
                try:
                    metadata_embedded = _embed_music_metadata(path, info, video_id)
                except Exception:
                    # Music details are an enhancement; a playable download should
                    # remain available if artwork or a malformed source tag fails.
                    metadata_embedded = False
            selected = (info.get("requested_downloads") or [{}])[0]
            codec = audio_format if audio_format in CONVERTED_AUDIO_FORMATS else selected.get("acodec") or info.get("acodec")
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
            with self.lock:
                if cancelled.is_set():
                    raise RuntimeError('Cancelled. Retry to resume.')
                self.store.add_track(track)
                self.jobs[job_id].update(status='complete', percent=100, track_id=job_id, error=None, speed=None, eta=None,
                                         title=track['title'], artist=track['artist'],
                                         metadata_embedded=metadata_embedded)
                self.store.save_job(self.jobs[job_id])
        except Exception as exc:
            # yt-dlp can fail due to deleted, blocked or unavailable content.
            self._update(job_id, status="error", error='Cancelled. Retry to resume.' if cancelled.is_set() else str(exc)[:350],
                         cancelled=cancelled.is_set(), speed=None, eta=None)
            # Keep partial files under the same job ID so yt-dlp can resume a retry.
