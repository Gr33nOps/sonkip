"""Local-only FastAPI server; audio and metadata live on your machine."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .engine import DownloadManager, extract_playlist, get_stream_url, search_music, VIDEO_ID_RE
from .storage import MusicStore

ROOT = Path(__file__).resolve().parent.parent


class DownloadRequest(BaseModel):
    video_id: str


class PlaylistRequest(BaseModel):
    url: str


def create_app(data_dir: Path | None = None) -> FastAPI:
    legacy_home = Path.home() / "Music" / "Sonora"
    default_home = legacy_home if legacy_home.exists() else Path.home() / "Music" / "Sonkip"
    home = data_dir or Path(os.getenv("LOCALMUSIC_HOME", default_home))
    store = MusicStore(home)
    manager = DownloadManager(store)
    app = FastAPI(title="sonkip. Local API", version="1.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.state.store = store
    app.state.manager = manager

    @app.get("/api/health")
    def health():
        return {"ok": True, "library_path": str(store.tracks_dir)}

    @app.get("/api/search")
    async def search(q: str = Query(min_length=2, max_length=120)):
        q = q.strip()
        if len(q) < 2:
            raise HTTPException(status_code=422, detail="Enter at least 2 characters")
        try:
            return {"results": await asyncio.to_thread(search_music, q)}
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
            url = await asyncio.to_thread(get_stream_url, video_id)
            if not url:
                raise HTTPException(status_code=404, detail="Audio stream not found")
            return {"url": url, "local": False}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Stream extraction failed: {str(exc)[:150]}") from exc

    @app.post("/api/downloads", status_code=202)
    def download(body: DownloadRequest):
        try:
            job_id = manager.start(body.video_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        return {"job_id": job_id}

    @app.post("/api/playlists", status_code=202)
    async def download_playlist(body: PlaylistRequest):
        try:
            playlist = await asyncio.to_thread(extract_playlist, body.url)
            jobs = [
                {**entry, "job_id": manager.start(entry["video_id"])}
                for entry in playlist["entries"]
            ]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Playlist provider unavailable: {str(exc)[:220]}") from exc
        return {"title": playlist["title"], "count": len(jobs), "jobs": jobs}

    @app.get("/api/jobs")
    def list_jobs():
        return {"jobs": manager.list_jobs()}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/api/tracks")
    def list_tracks():
        return {"tracks": store.list_tracks()}

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
        if not store.delete_track(track_id):
            raise HTTPException(status_code=404, detail="Track not found")
        return {"deleted": True}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(ROOT / "static" / "index.html")

    return app


app = create_app()
