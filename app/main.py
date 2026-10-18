"""Local-only FastAPI server; audio and metadata live on your machine."""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.background import BackgroundTask

from .engine import DownloadManager, extract_playlist, get_stream_url, search_music, VIDEO_ID_RE
from .storage import MusicStore

ROOT = Path(__file__).resolve().parent.parent


class DownloadRequest(BaseModel):
    video_id: str
    audio_format: str = "m4a"
    embed_metadata: bool = True


class MusicFolderRequest(BaseModel):
    folder: str


class PlaylistRequest(BaseModel):
    url: str
    audio_format: str = "m4a"
    embed_metadata: bool = True


class DeleteTracksRequest(BaseModel):
    track_ids: list[str]


class YoutubeAuthRequest(BaseModel):
    cookies: str


def create_app(data_dir: Path | None = None) -> FastAPI:
    legacy_home = Path.home() / "Music" / "Sonora"
    default_home = legacy_home if legacy_home.exists() else Path.home() / "Music" / "Sonkip"
    home = data_dir or Path(os.getenv("LOCALMUSIC_HOME", default_home))
    store = MusicStore(home)
    manager = DownloadManager(store)
    app = FastAPI(title="sonkip. Local API", version="1.2.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.state.store = store
    app.state.manager = manager

    @app.get('/api/music-folder')
    def music_folder():
        return store.music_folder_status()

    @app.post('/api/music-folder')
    def set_music_folder(body: MusicFolderRequest):
        try:
            return store.set_music_folder(body.folder.strip())
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post('/api/music-folder/pick')
    async def pick_music_folder():
        # Run the native dialog in its own process: Tk requires its main thread.
        import subprocess
        import sys
        script = "import tkinter as t; from tkinter import filedialog; r=t.Tk(); r.withdraw(); r.attributes('-topmost',True); print(filedialog.askdirectory(title='Choose your music folder')); r.destroy()"
        try:
            result = await asyncio.to_thread(subprocess.run, [sys.executable, '-c', script], capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise ValueError('Folder picker unavailable. Enter a full folder path instead.')
            return {'folder': result.stdout.strip()}
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/health")
    def health():
        return {"ok": True, "library_path": str(store.tracks_dir)}

    @app.get("/api/auth/youtube")
    def youtube_auth_status():
        return {"connected": store.youtube_auth_connected()}

    @app.post("/api/auth/youtube")
    def connect_youtube(body: YoutubeAuthRequest):
        try:
            store.save_youtube_cookies(body.cookies)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"connected": True}

    @app.delete("/api/auth/youtube")
    def disconnect_youtube():
        store.clear_youtube_cookies()
        return {"connected": False}

    @app.get("/api/search")
    async def search(q: str = Query(min_length=2, max_length=120)):
        q = q.strip()
        if len(q) < 2:
            raise HTTPException(status_code=422, detail="Enter at least 2 characters")
        try:
            return {
                "results": await asyncio.to_thread(
                    search_music, q, store.youtube_cookies_path
                )
            }
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Search provider unavailable: {str(exc)[:220]}") from exc

    @app.get("/api/stream/{video_id}")
    async def stream_audio_preview(video_id: str):
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise HTTPException(status_code=422, detail="Invalid video ID")
        local_track = next((t for t in store.list_tracks() if t.get("video_id") == video_id), None)
        if local_track:
            return {"url": f"/api/tracks/{local_track['id']}/audio", "local": True}
        try:
            url = await asyncio.to_thread(
                get_stream_url, video_id, store.youtube_cookies_path
            )
            if not url:
                raise HTTPException(status_code=404, detail="Audio stream not found")
            return {"url": url, "local": False}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Stream extraction failed: {str(exc)[:150]}") from exc

    @app.post("/api/downloads", status_code=202)
    def download(body: DownloadRequest):
        try:
            job_id = manager.start(body.video_id, body.audio_format, body.embed_metadata)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        return {"job_id": job_id}

    @app.post("/api/playlists", status_code=202)
    async def download_playlist(body: PlaylistRequest):
        try:
            playlist = await asyncio.to_thread(
                extract_playlist, body.url, store.youtube_cookies_path
            )
            jobs = [
                {
                    **entry,
                    "job_id": manager.start(
                        entry["video_id"], body.audio_format, body.embed_metadata
                    ),
                }
                for entry in playlist["entries"]
                if not entry.get('needs_review')
            ]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Playlist provider unavailable: {str(exc)[:220]}") from exc
        return {"title": playlist["title"], "count": len(jobs), "jobs": jobs,
                "review": [entry for entry in playlist['entries'] if entry.get('needs_review')],
                "unmatched": playlist.get("unmatched", []), "notice": playlist.get("notice", ""),
                "source_count": playlist.get("source_count", len(jobs))}

    @app.get("/api/jobs")
    def list_jobs():
        return {"jobs": manager.list_jobs()}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post('/api/jobs/retry-failed')
    def retry_failed():
        return {'job_ids': manager.retry_failed()}

    @app.post('/api/jobs/resume-interrupted')
    def resume_interrupted():
        return {'job_ids': manager.resume_interrupted()}

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id: str):
        try:
            manager.cancel(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {'ok': True}

    @app.get("/api/tracks")
    def list_tracks():
        return {"tracks": store.list_tracks()}

    @app.get('/api/backup')
    def backup():
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False, dir=store.home) as output:
            path = Path(output.name)
        try:
            store.export_backup(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(path, filename='Sonkip-backup.zip', media_type='application/zip',
                            background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post('/api/backup/restore')
    async def restore_backup(request: Request):
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False, dir=store.home) as output:
            path = Path(output.name)
            try:
                async for chunk in request.stream():
                    output.write(chunk)
            except BaseException:
                output.close()
                path.unlink(missing_ok=True)
                raise
        try:
            return await asyncio.to_thread(store.import_backup, path)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(status_code=422, detail='Could not restore this Sonkip backup: ' + str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)

    def get_audio(track_id: str):
        track = store.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        path = store.path_for(track)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Audio file missing")
        return track, path

    @app.get("/api/tracks/{track_id}/audio")
    def stream_audio(track_id: str):
        _, path = get_audio(track_id)
        return FileResponse(path)

    @app.get("/api/tracks/{track_id}/file")
    def save_audio(track_id: str):
        track, path = get_audio(track_id)
        safe_title = "".join(ch if (ch.isalnum() or ch in " -_().") else "_" for ch in track["title"])[:90].strip() or "Audio"
        return FileResponse(path, filename=f"{safe_title}.{track['extension']}", media_type="application/octet-stream")

    @app.delete("/api/tracks/{track_id}")
    def delete_track(track_id: str):
        if not manager.delete_tracks([track_id]):
            raise HTTPException(status_code=404, detail="Track not found")
        return {"deleted": True}

    @app.post("/api/tracks/delete-selected")
    def delete_selected(body: DeleteTracksRequest):
        if len(body.track_ids) > 10000 or any(not re.fullmatch(r"[0-9a-f]{32}", value) for value in body.track_ids):
            raise HTTPException(status_code=422, detail="Invalid track selection")
        return {"deleted": manager.delete_tracks(body.track_ids)}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(ROOT / "static" / "index.html")

    return app


app = create_app()
