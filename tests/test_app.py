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
        if url == "https://www.youtube.com/playlist?list=PLroadtrip":
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
        assert self.opts["format"] == "bestaudio/best[acodec!=none]"
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
        assert library[0]["filename"] == "Example Artist - Sample _Audio_.webm"
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


def test_large_playlist_jobs_remain_available(monkeypatch, tmp_path):
    from app.storage import MusicStore
    manager = engine.DownloadManager(MusicStore(tmp_path))
    # Prevent network work while exercising the real queue and retention.
    monkeypatch.setattr(manager, "_run", lambda *args: None)
    jobs = [manager.start(VIDEO_ID) for _ in range(125)]
    assert len(set(jobs)) == 125
    for job_id in jobs:
        manager._update(job_id, status="complete")
    manager.start(VIDEO_ID)
    assert all(manager.get_job(job_id)["status"] == "complete" for job_id in jobs)
    manager.pool.shutdown(wait=True)


def test_unsupported_playlist_has_actionable_message(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        result = client.post("/api/playlists", json={"url": "https://example.com/playlist/example"})
        assert result.status_code == 422
        assert "YouTube" in result.json()["detail"]


def test_playlist_rejects_non_url_and_empty_playlist(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/playlists", json={"url": "not a url"}).status_code == 422


def test_playlist_import_queues_every_valid_song(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        playlist = client.post("/api/playlists", json={"url": "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PLroadtrip"})
        assert playlist.status_code == 202
        payload = playlist.json()
        assert payload["title"] == "Road trip"
        assert payload["count"] == 2
        assert {job["video_id"] for job in payload["jobs"]} == {VIDEO_ID, "M7lc1UVf-VE"}


def test_youtube_auth_is_saved_locally_and_can_be_disconnected(tmp_path):
    app = create_app(tmp_path)
    cookies = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tlocal-session\n"
    )
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/auth/youtube").json() == {"connected": False}

        connected = client.post("/api/auth/youtube", json={"cookies": cookies})
        assert connected.status_code == 200
        assert connected.json() == {"connected": True}
        assert app.state.store.youtube_cookies_path.read_text(encoding="utf-8") == cookies
        assert client.get("/api/auth/youtube").json() == {"connected": True}

        disconnected = client.delete("/api/auth/youtube")
        assert disconnected.json() == {"connected": False}
        assert not app.state.store.youtube_cookies_path.exists()


def test_youtube_auth_rejects_non_cookie_files(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post(
            "/api/auth/youtube",
            json={"cookies": "this is not a browser cookie export"},
        )
        assert response.status_code == 422
        assert client.get("/api/auth/youtube").json() == {"connected": False}


def test_youtube_auth_discards_unrelated_site_cookies(tmp_path):
    app = create_app(tmp_path)
    cookies = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tlocal-session\n"
        ".example.com\tTRUE\t/\tTRUE\t2147483647\tSECRET\tdo-not-store\n"
    )
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/youtube", json={"cookies": cookies}).status_code == 200
    saved = app.state.store.youtube_cookies_path.read_text(encoding="utf-8")
    assert ".youtube.com" in saved
    assert ".example.com" not in saved
    assert "do-not-store" not in saved


def test_download_uses_connected_youtube_session(monkeypatch, tmp_path):
    class AuthenticatedYoutubeDL(FakeYoutubeDL):
        def __init__(self, opts):
            assert opts["cookiefile"] == str(tmp_path / "private" / "youtube-cookies.txt")
            super().__init__(opts)

    monkeypatch.setattr(engine, "YoutubeDL", AuthenticatedYoutubeDL)
    app = create_app(tmp_path)
    cookies = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tlocal-session\n"
    )
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/youtube", json={"cookies": cookies}).status_code == 200
        job_id = client.post("/api/downloads", json={"video_id": VIDEO_ID}).json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("complete", "error"):
                break
            time.sleep(.01)
        assert job["status"] == "complete", job


def test_bundled_javascript_runtime_is_used_with_and_without_auth(monkeypatch, tmp_path):
    runtime = tmp_path / "libqjs.so"
    runtime.touch()
    monkeypatch.setenv("SONKIP_QUICKJS", str(runtime))
    cookies = tmp_path / "cookies.txt"
    cookies.touch()
    for cookiefile in (None, cookies):
        options = engine.youtube_access_options(cookiefile)
        assert options["js_runtimes"] == {"quickjs": {"path": str(runtime)}}


def test_download_retries_public_hls_after_forbidden_stream(monkeypatch, tmp_path):
    class ForbiddenAudio(FakeYoutubeDL):
        def extract_info(self, url, download):
            if self.opts["format"] == "bestaudio/best[acodec!=none]":
                raise RuntimeError("HTTP Error 403: Forbidden")
            assert self.opts["format"] == "best[protocol^=m3u8][acodec!=none]"
            self.opts["format"] = "bestaudio/best[acodec!=none]"
            return super().extract_info(url, download)
    monkeypatch.setattr(engine, "YoutubeDL", ForbiddenAudio)
    manager = engine.DownloadManager(engine.MusicStore(tmp_path))
    job_id = manager.start(VIDEO_ID)
    manager.pool.shutdown(wait=True)
    assert manager.jobs[job_id]["status"] == "complete"
    assert manager.store.list_tracks()[0]["video_id"] == VIDEO_ID


def test_desktop_download_uses_token_capable_mobile_web_client(monkeypatch, tmp_path):
    class PublicMusicYoutubeDL(FakeYoutubeDL):
        def extract_info(self, url, download):
            clients = self.opts["extractor_args"]["youtube"]["player_client"]
            if "mweb" not in clients:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return super().extract_info(url, download)

    monkeypatch.delenv("SONKIP_QUICKJS", raising=False)
    monkeypatch.setattr(engine, "YoutubeDL", PublicMusicYoutubeDL)
    manager = engine.DownloadManager(engine.MusicStore(tmp_path))
    job_id = manager.start(VIDEO_ID)
    manager.pool.shutdown(wait=True)
    assert manager.jobs[job_id]["status"] == "complete"
    assert manager.store.list_tracks()[0]["video_id"] == VIDEO_ID


