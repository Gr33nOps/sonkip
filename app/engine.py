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
import math
import subprocess
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
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
_ARTWORK_HOST_RETRY: dict[str, float] = {}

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


def _clean_metadata_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).strip()


def _release_date(value: Any, year: Any = None) -> str:
    if isinstance(value, dict):
        release_year = _positive_int(value.get('year'))
        if release_year:
            try:
                return date(release_year, int(value['month']), int(value['day'])).isoformat()
            except (KeyError, TypeError, ValueError):
                return f'{release_year:04d}'
        value = value.get('isoString', '')
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) >= 4:
        return digits[:4]
    year_digits = re.sub(r"\D", "", str(year or ""))
    return year_digits[:4] if len(year_digits) >= 4 else ""


def _positive_int(value: Any) -> int | None:
    try:
        number = int(str(value).split("/", 1)[0])
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _artwork_url(info: dict[str, Any]) -> str:
    direct = _clean_metadata_text(info.get("artwork_url") or info.get("thumbnail"))
    if direct.startswith("https://"):
        return direct
    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in reversed(thumbnails):
            url = _clean_metadata_text(item.get("url") if isinstance(item, dict) else "")
            if url.startswith("https://"):
                return url
    video_id = _clean_metadata_text(info.get("id") or info.get("video_id"))
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if VIDEO_ID_RE.fullmatch(video_id) else ""


def resolve_music_metadata(info: dict[str, Any], source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve one stable metadata shape for search, previews, files, and storage.

    ``source`` is metadata supplied by an identified music release (for example
    a Spotify album import), so its non-empty values take priority over the
    matched video's descriptive fields.
    """
    merged = dict(info or {})
    for key, value in (source or {}).items():
        if value not in (None, "", [], {}) and value not in ("Unknown artist", "Untitled"):
            if key == "release_type" and value in ("single", "unknown") and merged.get("album") and not source.get("album"):
                continue
            if key == "track_number" and not (source.get("album") or source.get("release_id")):
                continue
            merged[key] = value
            if key == "title":
                merged["track"] = value
    artist = _clean_metadata_text(merged.get("artist") or merged.get("creator") or merged.get("uploader"))
    description = str(merged.get('description') or '')
    def credit(label):
        match = re.search(r'(?im)^\s*(?:'+label+r')\s*[:\-]\s*([^\r\n]{1,300})', description)
        return _clean_metadata_text(match[1]).strip(' -') if match else ''
    if not merged.get('track'):
        merged['track'] = credit(r'Song(?:\s+name)?|Track')
    if not merged.get('album'):
        merged['album'] = credit(r'Album(?:\s+name)?')
    if not (merged.get('artist') or merged.get('creator')):
        performer = credit(r'Singer|Artist|Vocals?')
        title_credit = re.split(r'\s+[-–—]\s+', _clean_metadata_text(merged.get('title')), maxsplit=1)
        if performer:
            artist = performer
        elif len(title_credit) == 2 and title_credit[0] and len(title_credit[0]) <= 120:
            artist = title_credit[0]
    artist = re.sub(r"\s+-\s+Topic$", "", artist, flags=re.IGNORECASE).strip() or "Unknown artist"
    title = _clean_metadata_text(merged.get("track") or merged.get("title")) or "Untitled"
    title = re.sub(
        r"^" + re.escape(artist) + r"\s*[-–—:]\s*",
        "",
        title,
        count=1,
        flags=re.IGNORECASE,
    ).strip() or title
    title = re.sub(
        r"\s*[\[(](?:official\s+)?(?:audio|video|music\s+video|lyric\s+video|lyrics)[\])]\s*",
        " ",
        title,
        flags=re.IGNORECASE,
    ).strip() or title
    album = _clean_metadata_text(merged.get("album"))
    release_date = _release_date(merged.get("release_date"), merged.get("release_year") or merged.get("year"))
    duration = merged.get("duration")
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "album_artist": _clean_metadata_text(merged.get("album_artist")) or artist,
        "artwork_url": _artwork_url(merged),
        "track_number": _positive_int(merged.get("track_number")),
        "release_date": release_date,
        "year": release_date[:4],
        "genre": _clean_metadata_text(merged.get("genre")),
        "duration": int(round(duration)) if isinstance(duration, (int, float)) and duration >= 0 else None,
        "release_id": _clean_metadata_text(merged.get("release_id") or merged.get("album_id")),
        "release_type": _clean_metadata_text(merged.get("release_type")).lower() or ("album" if album else "unknown"),
    }


def _music_details(info: dict[str, Any]) -> dict[str, Any]:
    return resolve_music_metadata(info)


def _download_artwork(video_id: str, artwork_url: str = "") -> tuple[bytes, str] | None:
    parsed = urlparse(artwork_url)
    trusted_art_hosts = {
        "i.ytimg.com", "lh3.googleusercontent.com", "i.scdn.co",
        "image-cdn-ak.spotifycdn.com", "mosaic.scdn.co", "i1.sndcdn.com", "yt3.googleusercontent.com",
    }
    trusted_art_hosts.update({"image-cdn-fa.spotifycdn.com", "image-cdn-kr.spotifycdn.com"})
    urls = [artwork_url] if parsed.scheme == "https" and parsed.hostname in trusted_art_hosts else []
    if VIDEO_ID_RE.fullmatch(video_id):
        urls.extend(f"https://i.ytimg.com/vi/{video_id}/{size}.jpg" for size in ("maxresdefault", "hqdefault"))
    for url in dict.fromkeys(urls):
        host = urlparse(url).hostname or ''
        if _ARTWORK_HOST_RETRY.get(host, 0) > time.monotonic():
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/jpeg,image/png"})
            with urllib.request.urlopen(request, timeout=5) as response:
                artwork = response.read(MAX_ARTWORK_BYTES + 1)
                content_type = str(response.headers.get("Content-Type", "image/jpeg")).split(";", 1)[0].lower()
            if artwork and len(artwork) <= MAX_ARTWORK_BYTES and content_type in ("image/jpeg", "image/png"):
                return artwork, content_type
        except (OSError, ValueError) as exc:
            if isinstance(exc, OSError) and not isinstance(exc, urllib.error.HTTPError):
                _ARTWORK_HOST_RETRY[host] = time.monotonic()+60
            continue
    return None


def _embed_music_metadata(
    path: Path,
    info: dict[str, Any],
    video_id: str,
    source_metadata: dict[str, Any] | None = None,
) -> bool:
    extension = path.suffix.lower()
    if extension not in (".m4a", ".mp4", ".mp3", ".flac", ".opus", ".ogg"):
        return False
    from mutagen import File as AudioFile
    if AudioFile(path) is None:
        return False
    details = resolve_music_metadata(info, source_metadata)
    try:
        artwork = _download_artwork(video_id, details["artwork_url"])
    except (OSError, ValueError):
        artwork = None
    if extension in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9nam"] = [details["title"]]
        audio.tags["\xa9ART"] = [details["artist"]]
        audio.tags["aART"] = [details["album_artist"]]
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
        from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
        from mutagen.mp3 import MP3

        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        for frame in ("TIT2", "TPE1", "TPE2", "TALB", "TRCK", "TDRC", "TCON"):
            audio.tags.delall(frame)
        audio.tags.add(TIT2(encoding=3, text=details["title"]))
        audio.tags.add(TPE1(encoding=3, text=details["artist"]))
        audio.tags.add(TPE2(encoding=3, text=details["album_artist"]))
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
            audio.tags.delall('APIC')
            audio.tags.add(APIC(encoding=3, mime=content_type, type=3, desc="Cover", data=data))
        audio.save(v2_version=3)
    else:
        from mutagen.flac import FLAC, Picture
        from mutagen.oggopus import OggOpus

        audio = FLAC(path) if extension == ".flac" else OggOpus(path)
        audio["title"] = [details["title"]]
        audio["artist"] = [details["artist"]]
        audio["albumartist"] = [details["album_artist"]]
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


def _prepare_tagged_audio(path: Path) -> Path:
    """Move WebM Opus packets into Ogg so standard cover/tag readers can read them.

    This is a container change: audio is copied without re-encoding.
    """
    if path.suffix.lower() not in ('.webm', '.mp4'):
        return path
    target = path.with_suffix('.opus' if path.suffix.lower() == '.webm' else '.m4a')
    try:
        if os.environ.get('SONKIP_ANDROID_TOKENS') == '1':
            from java import jclass
            extractor = jclass('io.github.gr33nops.sonkip.AndroidAudioExtractor')
            if path.suffix.lower() == '.webm':
                extractor.extractOpus(str(path), str(target))
            else:
                extractor.extractM4a(str(path), str(target))
        else:
            import imageio_ffmpeg
            subprocess.run([shutil.which('ffmpeg') or imageio_ffmpeg.get_ffmpeg_exe(),
                '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path), '-vn',
                '-c:a', 'copy', str(target)], check=True, capture_output=True, timeout=120)
        if not target.is_file() or not target.stat().st_size:
            raise RuntimeError('Audio remux produced no file')
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


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


def _search_result(item: dict[str, Any]) -> dict[str, Any] | None:
    video_id = item.get("id") or item.get("video_id")
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        return None
    metadata = resolve_music_metadata({**item, "video_id": video_id})
    title_words = _words(str(item.get("title") or ""))
    channel_words = _words(str(item.get("uploader") or item.get("channel") or ""))
    lyrics_only = bool(title_words & {"lyrics", "lyric"} or channel_words & {"lyrics", "lyric"})
    artist_words = _words(metadata["artist"])
    artist_channel = bool(artist_words and artist_words.issubset(channel_words))
    title_prefix = str(item.get("title") or "").split(" - ", 1)
    credited_artist = _words(title_prefix[0]) if len(title_prefix) == 2 else set()
    credited_artist_matches = not credited_artist or bool(credited_artist & artist_words)
    return {
        "video_id": video_id,
        **metadata,
        "thumbnail": metadata["artwork_url"],
        "channel_is_verified": bool(item.get("channel_is_verified")),
        "is_lyrics_upload": lyrics_only,
        "artist_channel": artist_channel,
        "view_count": item.get("view_count") if isinstance(item.get("view_count"), int) else None,
        "source_quality": "official" if not lyrics_only and artist_channel and credited_artist_matches and (
            item.get("channel_is_verified") or "topic" in channel_words
        ) else "community",
    }


def _rank_search_results(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_words = _words(query)
    version_words = {"live", "cover", "remix", "slowed", "instrumental", "karaoke", "nightcore", "demo", "sped", "acoustic", "making", "footnotes", "reaction", "interview", "tutorial", "explained"}
    ranked: list[tuple[float, dict[str, Any]]] = []
    for raw in items:
        result = _search_result(raw)
        if result is None:
            continue
        candidate_words = _words(result["title"] + " " + result["artist"])
        coverage = len(query_words & candidate_words) / max(1, len(query_words))
        if coverage < 0.5:
            continue
        unwanted_versions = (candidate_words & version_words) - (query_words & version_words)
        score = coverage * 1.4
        if result["channel_is_verified"]:
            score += 0.45
        if result["source_quality"] == "official":
            score += 0.35
        if result["artist_channel"]:
            score += 0.3
        if result["album"]:
            score += 0.12
        views = result.get("view_count")
        if isinstance(views, int) and views > 0:
            score += min(0.24, math.log10(views + 1) / 28)
        score -= 0.65 * len(unwanted_versions)
        if result["is_lyrics_upload"] and not query_words & {"lyric", "lyrics"}:
            score -= 0.85
        ranked.append((score, result))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    if not ranked:
        return []
    top_score = ranked[0][0]
    margin = top_score - ranked[1][0] if len(ranked) > 1 else top_score
    clear_match = top_score >= 1.65 and margin >= 0.35
    selected = ranked[:1] if clear_match else ranked[:5]
    results = []
    for index, (score, result) in enumerate(selected):
        results.append({**result, "is_best_match": index == 0, "match_score": round(score, 3)})
    return results


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
                    result = _search_result({**info, "id": vid})
                    return [{**result, "is_best_match": True}] if result else []
        except Exception:
            pass

    catalog = _catalog_search(clean)
    if catalog:
        ranked = _rank_search_results(clean, [{**t, 'uploader': t['artist']+' - Topic'} for t in catalog])
        if ranked:
            return ranked
    with YoutubeDL(opts) as ydl:
        data = ydl.extract_info(f"ytsearch15:{clean}", download=False)

    entries = [item for item in (data or {}).get("entries") or [] if isinstance(item, dict)]
    return _rank_search_results(clean, entries)


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
    album_release = playlist_id.startswith("OLAK5uy")
    album_title = _clean_metadata_text((data or {}).get("album") or (data or {}).get("title")) if album_release else ""
    album_title = re.sub(r'^Album\s*[-–—:]\s*', '', album_title, flags=re.I)
    album_artist = _clean_metadata_text((data or {}).get("album_artist") or (data or {}).get("artist")
        or (data or {}).get('uploader')) if album_release else ""
    album_artist = re.sub(r'\s+-\s+Topic$', '', album_artist, flags=re.I)
    playlist_art = _artwork_url(data or {})
    for position, item in enumerate((data or {}).get("entries") or [], 1):
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        if isinstance(video_id, str) and VIDEO_ID_RE.fullmatch(video_id) and video_id not in seen:
            seen.add(video_id)
            release = ({"album": album_title, "release_id": playlist_id, "release_type": "album",
                        "track_number": item.get("playlist_index") or position,
                        "album_artist": album_artist,
                        "artwork_url": playlist_art}
                       if album_release else {})
            result = _search_result({**item, **release, "id": video_id})
            if result:
                entries.append(result)
    if not entries:
        raise ValueError("No downloadable songs were found in that playlist")
    source_count = len(entries)
    def official_recording(entry):
        if entry.get('source_quality') == 'official':
            return entry, None
        try:
            found = _match_track(entry, cookiefile)
            if found:
                release = {key: entry[key] for key in ('album', 'album_artist', 'release_id', 'release_type', 'track_number')
                           if entry.get(key)} if entry.get('album') else {}
                metadata = resolve_music_metadata(found, release)
                return {**found, **metadata, 'thumbnail': metadata['artwork_url'],
                        'original_video_id': entry['video_id']}, None
        except Exception:
            pass
        return None, {'title': entry['title'], 'artist': entry['artist'], 'reason': 'No close official recording found'}
    with ThreadPoolExecutor(max_workers=3) as pool:
        matched = list(pool.map(official_recording, entries))
    recordings = [found for found, _ in matched if found]
    unique = list({item['video_id']: item for item in reversed(recordings)}.values())
    unique.reverse()
    if not unique:
        raise ValueError('No close official recordings were found in that playlist')
    return {"title": str((data or {}).get("title") or "Playlist"), "entries": unique,
            "artwork_url": playlist_art, 'source_count': source_count,
            'unmatched': [missing for _, missing in matched if missing],
            'duplicate_count': len(recordings)-len(unique)}


def _words(value: str) -> set[str]:
    return set(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def _request_music_catalog(query: str) -> dict:
    request = urllib.request.Request('https://music.youtube.com/youtubei/v1/search?prettyPrint=false',
        data=json.dumps({'context': {'client': {'clientName': 'WEB_REMIX',
            'clientVersion': '1.20261028.01.00', 'hl': 'en', 'gl': 'US'}},
            'query': query, 'params': 'EgWKAQIIAWoMEA4QChADEAQQCRAF'}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://music.youtube.com'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read(8 * 1024 * 1024))


def _catalog_search(query: str) -> list[dict]:
    """Read artist-delivered recordings and release metadata from YouTube Music."""
    try:
        data = _request_music_catalog(query)
    except (OSError, ValueError):
        return []
    rows = []
    def walk(value):
        if isinstance(value, dict):
            if 'musicResponsiveListItemRenderer' in value:
                rows.append(value['musicResponsiveListItemRenderer'])
            else:
                for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(data)
    results, seen = [], set()
    for row in rows:
        columns = row.get('flexColumns') or []
        if not columns:
            continue
        title_runs = columns[0].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs') or []
        watch = next((r.get('navigationEndpoint', {}).get('watchEndpoint') for r in title_runs
                      if r.get('navigationEndpoint', {}).get('watchEndpoint')), {})
        video_id = watch.get('videoId', '')
        kind = watch.get('watchEndpointMusicSupportedConfigs', {}).get('watchEndpointMusicConfig', {}).get('musicVideoType')
        if not VIDEO_ID_RE.fullmatch(video_id) or video_id in seen or kind != 'MUSIC_VIDEO_TYPE_ATV':
            continue
        artists, album, release_id, duration = [], '', '', None
        for column in columns[1:]:
            runs = column.get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs') or []
            for run in runs:
                text = run.get('text', '')
                browse_id = run.get('navigationEndpoint', {}).get('browseEndpoint', {}).get('browseId', '')
                if browse_id.startswith('UC'):
                    artists.append(text)
                elif browse_id.startswith(('MPRE', 'OLAK')):
                    album, release_id = text, browse_id
                elif re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', text):
                    duration = 0
                    for part in text.split(':'): duration = duration * 60 + int(part)
        if not artists:
            continue
        thumbnails = row.get('thumbnail', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails') or []
        artwork = thumbnails[-1].get('url', '') if thumbnails else ''
        artwork = re.sub(r'=w\d+-h\d+', '=w600-h600', artwork)
        seen.add(video_id)
        metadata = resolve_music_metadata({'title': ''.join(r.get('text', '') for r in title_runs),
            'artist': ', '.join(artists), 'album_artist': artists[0], 'album': album,
            'release_id': release_id, 'duration': duration, 'artwork_url': artwork})
        results.append({'video_id': video_id, **metadata, 'thumbnail': artwork,
            'source_quality': 'official', 'artist_channel': True, 'is_lyrics_upload': False})
    return results


def _match_track(track: dict, cookiefile: Path | None, _catalog: bool = True, _catalog_only: bool = False) -> dict | None:
    candidates = _catalog_search(f"{track['artist'].split(',', 1)[0]} {track['title']}") if _catalog else []
    catalog_candidates = bool(candidates)
    if not candidates:
        if _catalog_only:
            return None
        candidates = search_music(f"{track['artist']} {track['title']}", cookiefile)
    base_title = re.split(r'\s*[([](?:feat\.?|ft\.?|with)\s|\s+(?:feat\.?|ft\.?)\s+', track['title'], flags=re.I)[0]
    base_title = re.sub(r'\s*[-–—]\s*(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?$', '', base_title, flags=re.I)
    title_words = _words(base_title)
    artist_words = _words(track['artist'].split(',', 1)[0])
    versions = {'live', 'cover', 'remix', 'mix', 'acoustic', 'slowed', 'instrumental', 'karaoke', 'nightcore', 'demo', 'sped',
                'making', 'footnotes', 'reaction', 'interview', 'tutorial', 'explained'}
    # Search ranking intentionally shows a short list. A second, audio-specific
    # query avoids losing the recording behind an interview or a lyric upload.
    if not catalog_candidates and not any(c.get('source_quality') == 'official' and not (_words(c['title']) & versions) - title_words
               for c in candidates):
        fallback = search_music(f"{track['artist'].split(',', 1)[0]} {track['title']} official audio", cookiefile)
        candidates = list({c['video_id']: c for c in candidates + fallback}.values())
    best, best_score = None, 0
    for candidate in candidates:
        if candidate.get('source_quality') == 'community':
            continue
        words = _words(candidate['title'])
        if (candidate.get('is_lyrics_upload') or words & {'lyric', 'lyrics'}) and not title_words & {'lyric', 'lyrics'}:
            continue
        if (words & versions) - (title_words & versions):
            continue
        title_score = len(title_words & words) / max(1, len(title_words))
        artist_score = len(artist_words & _words(candidate['artist'])) / max(1, len(artist_words))
        if title_score < .8 or artist_score < .5:
            continue
        expected, actual = track.get('duration'), candidate.get('duration')
        # A music video's short edit can still identify its album for existing
        # files. Download matching retains the stricter recording-duration limit.
        if expected and actual and abs(expected - actual) > max(25, expected * (.20 if _catalog_only else .15)):
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
        if candidate.get('source_quality') == 'official':
            score += .35
        if (candidate.get('is_lyrics_upload') or words & {'lyric', 'lyrics'}) and not title_words & {'lyric', 'lyrics'}:
            score -= .85
        if score > best_score:
            best = {**candidate, 'needs_review': not (expected and actual and title_score == 1 and artist_score == 1)}
            best_score = score
    if best is None and catalog_candidates and not _catalog_only:
        return _match_track(track, cookiefile, _catalog=False)
    return best


def _spotify_album_info(uri: str, token: str) -> dict:
    body = {'operationName': 'queryAlbum', 'variables': {'uri': uri, 'offset': 0},
        'extensions': {'persistedQuery': {'version': 1,
            'sha256Hash': 'ce390dbf7ca6b61a23aec210619e1094fe9d23d7f101ff773ce1146f84d4dd10'}}}
    request = urllib.request.Request('https://api-partner.spotify.com/pathfinder/v2/query',
        data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            album = json.loads(response.read(8 * 1024 * 1024)).get('data', {}).get('albumUnion') or {}
        artists = [a.get('profile', {}).get('name', '') for a in album.get('artists', {}).get('items', [])]
        return {'album_artist': ', '.join(a for a in artists if a),
                'release_type': str(album.get('type') or '').lower(),
                'release_date': _release_date(album.get('date'))}
    except (OSError, ValueError):
        return {}


def _spotify_tracks(parsed) -> tuple[str, list[dict], str]:
    """Read public Spotify metadata, paging beyond the 100-item embed preview."""
    match = re.fullmatch(r'/(?:intl-[a-z]+/)?(playlist|album)/([A-Za-z0-9]{22})/?', parsed.path)
    if not match:
        raise ValueError('Paste a public Spotify playlist or album link')
    kind, identifier = match[1], match[2]
    with urllib.request.urlopen(f'https://open.spotify.com/embed/{kind}/{identifier}', timeout=30) as response:
        html = response.read(8 * 1024 * 1024).decode('utf-8')
    payload = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not payload:
        raise ValueError('Spotify did not expose this playlist. Check that it is public.')
    state = json.loads(payload[1]).get('props', {}).get('pageProps', {}).get('state', {})
    entity = state.get('data', {}).get('entity', {})
    title = entity.get('name') or 'Spotify playlist'
    token = state.get('settings', {}).get('session', {}).get('accessToken')
    if kind == 'playlist' and token:
        tracks, offset, visited = [], 0, set()
        while offset not in visited:
            visited.add(offset)
            body = {
                'operationName': 'queryPlaylist',
                'variables': {'uri': f'spotify:playlist:{identifier}', 'limit': 100,
                              'offset': offset, 'includeItemV3': False},
                'extensions': {'persistedQuery': {'version': 1,
                    'sha256Hash': 'c685ca91fb0019c87ff1225f84e1d85b26cd631fa6187f3f0900da182cb0953d'}},
            }
            request = urllib.request.Request('https://api-partner.spotify.com/pathfinder/v2/query',
                data=json.dumps(body).encode(), headers={
                    'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read(16 * 1024 * 1024))
            playlist = (result.get('data') or {}).get('playlistV2') or {}
            page = playlist.get('content') or {}
            items = page.get('items')
            if not isinstance(items, list):
                raise ValueError('Spotify could not load the full playlist. Please try again; no partial playlist was queued.')
            title = playlist.get('name') or title
            for wrapper in items:
                t = (wrapper.get('itemV2') or {}).get('data') or {}
                if not t.get('name') or not t.get('uri', '').startswith('spotify:track:'):
                    continue
                album = t.get('albumOfTrack') or {}
                artists = [a.get('profile', {}).get('name', '') for a in t.get('artists', {}).get('items', [])]
                covers = sorted(album.get('coverArt', {}).get('sources') or [], key=lambda c: c.get('width') or 0)
                tracks.append({'title': t['name'], 'artist': ', '.join(a for a in artists if a),
                    'album_artist': artists[0] if artists else '',
                    'duration': (t.get('duration') or {}).get('totalMilliseconds', 0) / 1000,
                    'album': album.get('name', ''), 'release_id': album.get('uri', ''),
                    'track_number': t.get('trackNumber'), 'source_track_id': t['uri'],
                    'artwork_url': covers[-1]['url'] if covers else '',
                    'release_type': str(album.get('type') or '').lower(),
                    'release_date': (album.get('date') or {}).get('isoString', '')})
            next_offset = page.get('pagingInfo', {}).get('nextOffset')
            total = page.get('totalCount')
            consumed = offset + len(items)
            if next_offset is None:
                if isinstance(total, int) and consumed < total:
                    if not items:
                        raise ValueError(f'Spotify stopped after {consumed} of {total} tracks. Try importing again.')
                    next_offset = consumed
                else:
                    break
            if not isinstance(next_offset, int) or next_offset <= offset or next_offset > 100000:
                raise ValueError('Spotify returned an invalid playlist page. Try importing again.')
            offset = next_offset
        release_ids = list(dict.fromkeys(t['release_id'] for t in tracks if t['release_id']))
        with ThreadPoolExecutor(max_workers=3) as pool:
            albums = dict(zip(release_ids, pool.map(lambda uri: _spotify_album_info(uri, token), release_ids)))
        for track in tracks:
            track.update({key: value for key, value in albums.get(track['release_id'], {}).items() if value})
        return title, tracks, 'Spotify track metadata loaded from every playlist page.'
    collection_artist = _clean_metadata_text(entity.get('subtitle') or entity.get('artist'))
    covers = sorted((entity.get('coverArt') or {}).get('sources') or [], key=lambda c: c.get('width') or 0)
    tracks = [{
        'title': t['title'], 'artist': t['subtitle'],
        'album': title if kind == 'album' else _clean_metadata_text(t.get('album')),
        'album_artist': (collection_artist or t['subtitle']) if kind == 'album' else '',
        'duration': t.get('duration', 0) / 1000,
        'track_number': index if kind == 'album' else None,
        'release_id': f'spotify:album:{identifier}' if kind == 'album' else '',
        'release_type': 'album' if kind == 'album' else '',
        'artwork_url': covers[-1]['url'] if kind == 'album' and covers else '',
    } for index, t in enumerate(entity.get('trackList', []), 1) if t.get('title') and t.get('subtitle')]
    if kind == 'playlist' and len(tracks) >= 100:
        raise ValueError('Spotify returned only its 100-song preview. Try again to load the full playlist.')
    return title, tracks, 'Spotify public release metadata.'


def _import_playlist(parsed, cookiefile: Path | None) -> dict:
    if parsed.scheme != 'https' or parsed.username or parsed.port not in (None, 443):
        raise ValueError('Use the HTTPS playlist link from the music service')
    if parsed.hostname == 'open.spotify.com':
        title, tracks, note = _spotify_tracks(parsed)
        source = 'Spotify'
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
            metadata = resolve_music_metadata(found or {}, track)
            return ({**found, **metadata, 'thumbnail': metadata['artwork_url'],
                     'matched_from': source, 'source_title': track['title']} if found else None,
                    {**track, 'reason': 'No close YouTube match found'})
        except Exception:
            return None, {**track, 'reason': 'YouTube search failed; try importing again'}
    # Initialize yt-dlp's global plugin registry before concurrent searches.
    matches = [match_one(tracks[0])]
    with ThreadPoolExecutor(max_workers=3) as pool:
        matches.extend(pool.map(match_one, tracks[1:]))
    matched = [found for found, _ in matches if found]
    entries = list({found['video_id']: found for found in reversed(matched)}.values())
    entries.reverse()
    unmatched = [missing for found, missing in matches if not found]
    if not entries:
        raise ValueError('No close YouTube matches were found. Try searching for a song by title and artist.')
    return {'title': title, 'entries': entries, 'unmatched': unmatched, 'source_count': len(tracks),
            'duplicate_count': len(matched)-len(entries),
            'source': source, 'notice': note + ' Matches may be different uploads or editions.'}


def _same_recording(saved: dict[str, Any], incoming: dict[str, Any]) -> bool:
    if not incoming or incoming.get("title") in (None, "", "Untitled"):
        return False
    left = resolve_music_metadata(saved)
    right = resolve_music_metadata(incoming)
    if left["release_id"] and right["release_id"]:
        if left["release_id"].casefold() != right["release_id"].casefold():
            return False
        if left["track_number"] is not None and right["track_number"] is not None:
            return left["track_number"] == right["track_number"]
        return (left["title"].casefold() == right["title"].casefold()
                and left["artist"].casefold() == right["artist"].casefold())
    text_matches = all(left[key].casefold() == right[key].casefold() for key in ("title", "artist", "album"))
    if not text_matches or not left["album"]:
        return False
    if left["duration"] is not None and right["duration"] is not None:
        return abs(left["duration"] - right["duration"]) <= 3
    return left["track_number"] is not None and left["track_number"] == right["track_number"]


class DownloadManager:
    def __init__(self, store: MusicStore):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sonkip-download")
        self.lock = threading.Lock()
        self.cancellations = {}
        self.futures = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.metadata_repair = {'running': False, 'total': 0, 'completed': 0, 'errors': []}
        for job in store.load_jobs():
            if job['status'] not in ('complete', 'error'):
                job.update(status='error', speed=None, eta=None, interrupted=True,
                           error='Download interrupted. Retry to continue the saved partial file.')
                store.save_job(job)
            self.jobs[job['id']] = job

    def list_jobs(self):
        with self.lock:
            for track_id in self.store.deleted_track_ids:
                self.jobs.pop(track_id, None)
            return [dict(job) for job in reversed(list(self.jobs.values()))]

    def repair_status(self):
        with self.lock:
            return {**self.metadata_repair, 'errors': list(self.metadata_repair['errors'])}

    def repair_library(self):
        with self.lock:
            if self.metadata_repair['running']:
                return dict(self.metadata_repair)
            tracks = self.store.list_tracks()
            self.metadata_repair = {'running': True, 'total': len(tracks), 'completed': 0, 'errors': []}
            self.pool.submit(self._repair_library, tracks)
            return dict(self.metadata_repair)

    def _repair_library(self, tracks):
        try:
            for track in tracks:
                try:
                    started = time.monotonic()
                    with self.lock:
                        self.metadata_repair['current'] = track['title']
                    self._repair_track(track)
                    with self.lock:
                        self.metadata_repair['completed'] += 1
                        self.metadata_repair['last_seconds'] = round(time.monotonic()-started, 2)
                except Exception as exc:
                    with self.lock:
                        self.metadata_repair['errors'].append({'id': track['id'], 'title': track['title'], 'error': str(exc)[:200]})
        finally:
            with self.lock:
                self.metadata_repair['running'] = False

    def _repair_track(self, track, source_metadata=None):
        details = resolve_music_metadata(track)
        from mutagen import File as AudioFile
        original = self.store.path_for(track)
        audio = AudioFile(original) if original.suffix.lower() not in ('.webm', '.mp4') else None
        if (not source_metadata and details['album'] and audio is not None and audio.tags
                and (audio.tags.get('covr') or audio.tags.get('metadata_block_picture')
                     or getattr(audio, 'pictures', None) or getattr(audio.tags, 'getall', lambda _: [])('APIC'))):
            return
        if not source_metadata:
            with self.lock:
                self.metadata_repair['stage'] = 'Finding release details'
            found = _match_track(details, self.store.youtube_cookies_path, _catalog_only=True)
            if not found and not details['album']:
                credit = re.split(r'\s+[-–—]\s+', details['title'], maxsplit=1)
                if len(credit) == 2:
                    hypothesis = resolve_music_metadata({'title': credit[1], 'artist': credit[0], 'duration': details['duration']})
                    found = _match_track(hypothesis, self.store.youtube_cookies_path, _catalog_only=True)
            if not found and not details['album']:
                try:
                    with YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True,
                        'ignore_no_formats_error': True, 'socket_timeout': 15, 'noplaylist': True,
                        **youtube_access_options(self.store.youtube_cookies_path)}) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={track['video_id']}", download=False)
                    if isinstance(info, dict):
                        found = resolve_music_metadata(info)
                except Exception:
                    pass
            if found:
                # Retain a known release rather than silently switching editions.
                source_metadata = found if not details['album'] else {
                    key: value for key, value in found.items() if key == 'artwork_url' and found.get('album') == details['album']}
        details = resolve_music_metadata(details, source_metadata)
        staged = self.store.tracks_dir / ('.repair-' + uuid.uuid4().hex + original.suffix)
        prepared = staged
        try:
            shutil.copyfile(original, staged)
            with self.lock:
                self.metadata_repair['stage'] = 'Preparing audio'
            prepared = _prepare_tagged_audio(staged)
            with self.lock:
                self.metadata_repair['stage'] = 'Writing details and cover'
            if not _embed_music_metadata(prepared, details, track['video_id']):
                raise ValueError('This audio format cannot store music artwork')
            with self.lock:
                self.metadata_repair['stage'] = 'Saving song'
            self.store.replace_track_audio(track['id'], prepared, details)
        finally:
            staged.unlink(missing_ok=True)
            prepared.unlink(missing_ok=True)

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
        source_metadata: dict[str, Any] | None = None,
    ):
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError("Invalid video ID")
        audio_format = normalize_audio_format(audio_format)
        job_id = uuid.uuid4().hex
        with self.lock:
            saved = next((track for track in self.store.list_tracks()
                          if track['video_id'] == video_id or _same_recording(track, source_metadata or {})), None)
            if saved:
                for stale_id, stale in list(self.jobs.items()):
                    if (stale_id != saved['id'] and stale.get('video_id') == video_id
                            and stale.get('status') == 'error'):
                        self.jobs.pop(stale_id)
                        self.store.delete_job(stale_id)
                job_id = saved['id']
                self.jobs[job_id] = {
                    'id': job_id, 'video_id': video_id, 'status': 'complete', 'percent': 100,
                    'speed': None, 'eta': None, 'error': None, 'track_id': saved['id'],
                    'created_at': datetime.now(timezone.utc).isoformat(), 'already_saved': True,
                    'title': saved['title'], 'artist': saved['artist'], 'audio_format': audio_format,
                    'embed_metadata': bool(embed_metadata),
                    'source_metadata': resolve_music_metadata(source_metadata or saved),
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
                "source_metadata": dict(source_metadata or {}),
            }
            self.store.save_job(self.jobs[job_id])
            self.cancellations[job_id] = threading.Event()
            self.futures[job_id] = self.pool.submit(
                self._run, job_id, video_id, audio_format, bool(embed_metadata), source_metadata
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
                        job.get('source_metadata'),
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
                    job.get('source_metadata'),
                ) for job in self.list_jobs()
                if job.get('interrupted') and not job.get('cancelled') and job['status'] == 'error']

    def _run(
        self,
        job_id: str,
        video_id: str,
        audio_format: str = "original",
        embed_metadata: bool = True,
        source_metadata: dict[str, Any] | None = None,
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
            fallback_applied = False
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
                if (not cancelled.is_set() and os.environ.get("SONKIP_ANDROID_TOKENS") == "1"
                        and audio_format == "m4a" and "requested format is not available" in str(first_error).lower()):
                    # Some public uploads provide Opus only. Preserve the song
                    # in its available audio format instead of failing M4A.
                    for partial in self.store.tracks_dir.glob(job_id + ".*"):
                        if partial.is_file():
                            partial.unlink()
                    self._update(job_id, status="starting", percent=0)
                    with YoutubeDL({**opts, "format": "bestaudio[acodec!=none]/best[acodec!=none]"}) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                    fallback_applied = True
                else:
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
            details = resolve_music_metadata(info, source_metadata)
            if not details['album']:
                found = _match_track(details, self.store.youtube_cookies_path, _catalog_only=True)
                if found and found.get('album'):
                    source_metadata = resolve_music_metadata(found, source_metadata)
            if cancelled.is_set():
                raise RuntimeError('Cancelled. Retry to resume.')

            matching = [p for p in self.store.tracks_dir.glob(job_id + ".*")
                        if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".tmp")
                        and '.part' not in p.name]
            if not matching:
                raise RuntimeError("Download ended without an audio file")
            path = max(matching, key=lambda p: p.stat().st_size)
            if (os.environ.get("SONKIP_ANDROID_TOKENS") == "1"
                    and audio_format == "m4a" and not fallback_applied and path.suffix.lower() != ".m4a"):
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
            metadata_error = None
            if embed_metadata:
                try:
                    original_path = path
                    path = _prepare_tagged_audio(path)
                    metadata_embedded = _embed_music_metadata(path, info, video_id, source_metadata)
                    if metadata_embedded and original_path != path:
                        original_path.unlink(missing_ok=True)
                except Exception as metadata_failure:
                    # Music details are an enhancement; a playable download should
                    # remain available if artwork or a malformed source tag fails.
                    metadata_embedded = False
                    metadata_error = 'Music details could not be saved: ' + str(metadata_failure)[:180]
            selected = (info.get("requested_downloads") or [{}])[0]
            codec = audio_format if audio_format in CONVERTED_AUDIO_FORMATS and not fallback_applied else selected.get("acodec") or info.get("acodec")
            abr = selected.get("abr") or info.get("abr")
            details = resolve_music_metadata(info, source_metadata)
            track = {
                "id": job_id,
                "video_id": video_id,
                "title": details["title"],
                "artist": details["artist"],
                "album": details["album"],
                "album_artist": details["album_artist"],
                "artwork_url": details["artwork_url"],
                "track_number": details["track_number"],
                "release_date": details["release_date"],
                "release_id": details["release_id"],
                "release_type": details["release_type"],
                "duration": details["duration"],
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
                                         metadata_embedded=metadata_embedded,
                                         metadata_error=metadata_error,
                                         format_fallback=track['extension'] if fallback_applied else None)
                self.store.save_job(self.jobs[job_id])
        except Exception as exc:
            # yt-dlp can fail due to deleted, blocked or unavailable content.
            self._update(job_id, status="error", error='Cancelled. Retry to resume.' if cancelled.is_set() else str(exc)[:350],
                         cancelled=cancelled.is_set(), speed=None, eta=None)
            # Keep partial files under the same job ID so yt-dlp can resume a retry.
