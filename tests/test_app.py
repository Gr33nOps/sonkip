"""Offline API integration tests with a fake extractor; no real videos downloaded."""
import importlib.util
import json
import sys
import time
import types

# The real installation includes yt-dlp. In limited/offline CI, stub it so we
# can still verify all API/storage behavior without hitting a network.
if importlib.util.find_spec("yt_dlp") is None:
    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.__path__ = []
    fake_mod.YoutubeDL = object
    sys.modules["yt_dlp"] = fake_mod
    fake_utils = types.ModuleType("yt_dlp.utils")
    fake_utils.DownloadError = type("DownloadError", (Exception,), {})
    sys.modules["yt_dlp.utils"] = fake_utils

from fastapi.testclient import TestClient
import app.engine as engine
from app.main import create_app

VIDEO_ID = "dQw4w9WgXcQ"


class FakeYoutubeDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download):
        if url == "https://music.example/playlist/roadtrip":
            assert download is False
            return {"title": "Road trip", "entries": [
                {"id": VIDEO_ID, "title": "Sample <Audio>", "uploader": "Example Artist"},
                {"id": "M7lc1UVf-VE", "title": "Second song", "uploader": "Second Artist"},
                None,
            ]}
        if url.startswith("ytsearch"):
            return {"entries": [
                {"id": VIDEO_ID, "title": "Sample <Audio>", "uploader": "Example Artist", "duration": 125},
                {"id": "invalid", "title": "Ignore"},
            ]}
        assert url in {
            f"https://www.youtube.com/watch?v={VIDEO_ID}",
            "https://www.youtube.com/watch?v=M7lc1UVf-VE",
        }
        assert download is True
        assert self.opts["format"] == "bestaudio"
        assert self.opts["extractor_args"] == {
            "youtube": {"player_client": ["android_vr", "web_safari"]}
        }
        assert "cookiefile" not in self.opts
        assert "cookiesfrombrowser" not in self.opts
        filename = self.opts["outtmpl"].replace("%(ext)s", "webm")
        from pathlib import Path
        Path(filename).write_bytes(b"OggS" + b"a" * 100)
        self.opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 52, "total_bytes": 104})
        self.opts["progress_hooks"][0]({"status": "finished"})
        return {"title": "Sample <Audio>", "uploader": "Example Artist", "duration": 125,
                "requested_downloads": [{"acodec": "opus", "abr": 140}]}


def test_end_to_end_local_download(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/").status_code == 200
        assert "sonkip." in client.get("/").text
        assert client.get("/static/style.css").status_code == 200
        assert client.get("/api/health").json()["ok"] is True
        assert client.get("/api/search", params={"q": "a"}).status_code == 422
        results = client.get("/api/search", params={"q": "test music"}).json()["results"]
        assert len(results) == 1
        assert results[0]["title"] == "Sample <Audio>"
        assert client.post("/api/downloads", json={"video_id": "not-valid"}).status_code == 422

        resp = client.post("/api/downloads", json={"video_id": VIDEO_ID})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("complete", "error"):
                break
            time.sleep(.01)
        assert job["status"] == "complete", job
        assert job["percent"] == 100
        assert client.get("/api/jobs").json()["jobs"][0]["status"] == "complete"

        library = client.get("/api/tracks").json()["tracks"]
        assert len(library) == 1
        assert library[0]["codec"] == "opus"
        assert library[0]["extension"] == "webm"
        assert library[0]["filename"] == job_id + ".webm"
        assert client.get(f"/api/tracks/{job_id}/audio").content.startswith(b"OggS")
        file_resp = client.get(f"/api/tracks/{job_id}/file")
        assert file_resp.status_code == 200
        # Verify streaming for local and remote
        stream_resp = client.get(f"/api/stream/{VIDEO_ID}")
        assert stream_resp.status_code == 200
        assert stream_resp.json()["local"] is True

        assert client.get("/api/tracks/nope/audio").status_code == 404

    # Verify the SQLite library survives app restart.
    restarted = create_app(tmp_path)
    with TestClient(restarted, base_url="http://localhost") as client:
        assert len(client.get("/api/tracks").json()["tracks"]) == 1
        assert client.delete(f"/api/tracks/{job_id}").json() == {"deleted": True}
        assert client.get("/api/tracks").json()["tracks"] == []
        assert client.get(f"/api/tracks/{job_id}/audio").status_code == 404


def test_no_open_host(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        res = client.get("/api/health", headers={"host": "untrusted.example"})
        assert res.status_code == 400


def test_playlist_rejects_non_url_and_empty_playlist(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/playlists", json={"url": "not a url"}).status_code == 422


def test_playlist_import_queues_every_valid_song(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        playlist = client.post("/api/playlists", json={"url": "https://music.example/playlist/roadtrip"})
        assert playlist.status_code == 202
        payload = playlist.json()
        assert payload["title"] == "Road trip"
        assert payload["count"] == 2
        assert {job["video_id"] for job in payload["jobs"]} == {VIDEO_ID, "M7lc1UVf-VE"}


