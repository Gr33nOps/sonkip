"""Offline API integration tests with a fake extractor; no real videos downloaded."""
import importlib.util
from html.parser import HTMLParser
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


class _HomepageSemantics(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_homepage_exposes_navigation_and_live_status_semantics(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = client.get("/")
    assert response.status_code == 200
    parser = _HomepageSemantics()
    parser.feed(response.text)
    assert ("a", {"class": "skip-link", "href": "#main-content"}) in parser.elements
    assert any(tag == "main" and attrs.get("id") == "main-content" for tag, attrs in parser.elements)
    assert any(
        attrs.get("id") == "status-message"
        and attrs.get("role") == "status"
        and attrs.get("aria-live") == "polite"
        for _, attrs in parser.elements
    )
    assert any(
        attrs.get("class") == "mode-switch"
        and attrs.get("role") == "group"
        for _, attrs in parser.elements
    )


def test_playlist_preview_never_starts_downloads(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(engine.DownloadManager, '_run', lambda *a: None)
    monkeypatch.setattr(main, 'extract_playlist', lambda *a: {
        'title':'Imported mix', 'entries':[{'video_id':VIDEO_ID,'title':'Possible match','needs_review':True}]
    })
    with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
        result=client.post('/api/playlists',json={'url':'https://open.spotify.com/playlist/example'}).json()
        assert result['count'] == 1
        assert result['entries'][0]['video_id'] == VIDEO_ID
        assert result['entries'][0]['selected'] is True
        assert client.get('/api/jobs').json()['jobs'] == []


def test_playlist_download_starts_only_the_confirmed_selection(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(engine.DownloadManager, '_run', lambda *a: None)
    monkeypatch.setattr(main, 'extract_playlist', lambda *a: {
        'title': 'Album',
        'entries': [
            {'video_id': VIDEO_ID, 'title': 'First', 'artist': 'Artist', 'album': 'Album'},
            {'video_id': 'M7lc1UVf-VE', 'title': 'Second', 'artist': 'Artist', 'album': 'Album'},
        ],
    })
    with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
        preview = client.post('/api/playlists', json={'url': 'https://music.youtube.com/playlist?list=PLroadtrip'}).json()
        response = client.post('/api/playlists/download', json={
            'preview_id': preview['preview_id'],
            'video_ids': ['M7lc1UVf-VE'],
            'audio_format': 'flac',
            'embed_metadata': True,
        })
        assert response.status_code == 202
        assert [job['video_id'] for job in response.json()['jobs']] == ['M7lc1UVf-VE']
        jobs = client.get('/api/jobs').json()['jobs']
        assert len(jobs) == 1
        assert jobs[0]['source_metadata']['album'] == 'Album'


def test_same_release_track_is_not_downloaded_again_from_another_upload(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    manager = app.state.manager
    source = manager.store.tracks_dir / ('a' * 32 + '.m4a')
    source.write_bytes(b'audio')
    manager.store.add_track({
        'id': 'a' * 32, 'video_id': VIDEO_ID, 'title': 'First', 'artist': 'Artist',
        'album': 'Album', 'album_artist': 'Artist', 'release_id': 'release-1',
        'track_number': 1, 'duration': 180, 'filename': source.name,
        'bytes': 5, 'extension': 'm4a', 'codec': 'aac', 'abr': 128,
    })
    monkeypatch.setattr(manager, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('download started')))
    job_id = manager.start('M7lc1UVf-VE', 'm4a', True, {
        'title': 'First', 'artist': 'Artist', 'album': 'Album',
        'release_id': 'release-1', 'track_number': 1, 'duration': 180,
    })
    assert job_id == 'a' * 32
    assert manager.get_job(job_id)['already_saved'] is True
    manager.pool.shutdown(wait=True)


def test_saved_song_is_reused_when_new_format_differs(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    manager = app.state.manager
    source = manager.store.tracks_dir / ('b' * 32 + '.m4a')
    source.write_bytes(b'audio')
    manager.store.add_track({
        'id': 'b' * 32, 'video_id': VIDEO_ID, 'title': 'First', 'artist': 'Artist',
        'duration': 180, 'filename': source.name, 'bytes': 5,
        'extension': 'm4a', 'codec': 'aac', 'abr': 128,
    })
    monkeypatch.setattr(manager, '_run', lambda *args: (_ for _ in ()).throw(AssertionError('download started')))
    job_id = manager.start(VIDEO_ID, 'webm')
    assert job_id == 'b' * 32
    assert manager.get_job(job_id)['already_saved'] is True
    manager.pool.shutdown(wait=True)


def test_reusing_saved_song_clears_older_failed_download_entry(tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    source = manager.store.tracks_dir / ('c' * 32 + '.webm')
    source.write_bytes(b'audio')
    manager.store.add_track({
        'id': 'c' * 32, 'video_id': VIDEO_ID, 'title': 'Song', 'artist': 'Artist',
        'duration': 180, 'filename': source.name, 'bytes': 5,
        'extension': 'webm', 'codec': 'opus', 'abr': 128,
    })
    failed = {'id': 'd' * 32, 'video_id': VIDEO_ID, 'status': 'error', 'audio_format': 'm4a',
              'error': 'Requested format is not available'}
    manager.jobs[failed['id']] = failed
    manager.store.save_job(failed)
    try:
        assert manager.start(VIDEO_ID, 'm4a') == 'c' * 32
        assert [job['id'] for job in manager.list_jobs() if job['video_id'] == VIDEO_ID] == ['c' * 32]
        assert [job['id'] for job in manager.store.load_jobs() if job['video_id'] == VIDEO_ID] == ['c' * 32]
    finally:
        manager.pool.shutdown(wait=True)


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


class FakeMp3YoutubeDL(FakeYoutubeDL):
    def extract_info(self, url, download):
        assert download is True
        assert self.opts["postprocessors"] == [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        filename = self.opts["outtmpl"].replace("%(ext)s", "mp3")
        from pathlib import Path
        Path(filename).write_bytes(b"ID3" + b"a" * 100)
        self.opts["progress_hooks"][0]({"status": "finished"})
        return {"title": "Sample Audio", "uploader": "Example Artist", "duration": 125,
                "requested_downloads": [{"acodec": "mp3", "abr": 192}]}


def test_end_to_end_local_download(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeYoutubeDL)
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/").status_code == 200
        assert "sonkip." in client.get("/").text
        assert client.get("/static/style.css").status_code == 200
        assert client.get("/api/health").json()["ok"] is True
        assert client.get("/api/search", params={"q": "a"}).status_code == 422
        results = client.get("/api/search", params={"q": "Sample Audio"}).json()["results"]
        assert len(results) == 1
        assert results[0]["title"] == "Sample <Audio>"
        assert client.post("/api/downloads", json={"video_id": "not-valid"}).status_code == 422

        resp = client.post("/api/downloads", json={"video_id": VIDEO_ID, "audio_format": "original"})
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
        assert client.get("/api/jobs").json()["jobs"] == []
        assert client.get(f"/api/tracks/{job_id}/audio").status_code == 404


def test_delete_selected_removes_tracks_and_their_download_history(monkeypatch, tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    monkeypatch.setattr(manager, "_run", lambda *args: None)
    track_ids = []
    for video_id, title in ((VIDEO_ID, "First"), ("M7lc1UVf-VE", "Second")):
        track_id = manager.start(video_id, "m4a")
        manager.futures[track_id].result(timeout=3)
        source = manager.store.tracks_dir / f"{track_id}.m4a"
        source.write_bytes(b"audio")
        manager.store.add_track({
            "id": track_id,
            "video_id": video_id,
            "title": title,
            "artist": "Artist",
            "duration": 10,
            "filename": source.name,
            "bytes": source.stat().st_size,
            "extension": "m4a",
            "codec": "aac",
            "abr": 128,
        })
        manager._update(track_id, status="complete", track_id=track_id)
        track_ids.append(track_id)

    with TestClient(app, base_url="http://localhost") as client:
        response = client.post("/api/tracks/delete-selected", json={"track_ids": track_ids})
        assert response.status_code == 200
        assert response.json() == {"deleted": track_ids}
        assert client.get("/api/tracks").json()["tracks"] == []
        assert client.get("/api/jobs").json()["jobs"] == []
    manager.pool.shutdown(wait=True)


def test_unspecified_download_format_defaults_to_compatible_m4a(monkeypatch, tmp_path):
    app = create_app(tmp_path)
    manager = app.state.manager
    monkeypatch.setattr(manager, "_run", lambda *args: None)
    with TestClient(app, base_url="http://localhost") as client:
        job_id = client.post("/api/downloads", json={"video_id": VIDEO_ID}).json()["job_id"]
        manager.futures[job_id].result(timeout=3)
        assert client.get(f"/api/jobs/{job_id}").json()["audio_format"] == "m4a"
    manager.pool.shutdown(wait=True)


def test_download_converts_to_requested_mp3_format(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "YoutubeDL", FakeMp3YoutubeDL)
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = client.post("/api/downloads", json={"video_id": VIDEO_ID, "audio_format": "mp3"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("complete", "error"):
                break
            time.sleep(.01)
        assert job["status"] == "complete", job
        assert job["audio_format"] == "mp3"
        track = client.get("/api/tracks").json()["tracks"][0]
        assert track["extension"] == "mp3"
        assert track["filename"] == "Example Artist - Sample Audio.mp3"


def test_download_rejects_unknown_audio_format(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = client.post("/api/downloads", json={"video_id": VIDEO_ID, "audio_format": "exe"})
        assert response.status_code == 422
        assert client.get("/api/jobs").json()["jobs"] == []


def test_playlist_applies_format_and_metadata_preference_to_every_job(monkeypatch, tmp_path):
    import app.main as main
    monkeypatch.setattr(engine.DownloadManager, "_run", lambda *args: None)
    monkeypatch.setattr(main, "extract_playlist", lambda *args: {
        "title": "Road trip",
        "entries": [
            {"video_id": VIDEO_ID, "title": "First"},
            {"video_id": "M7lc1UVf-VE", "title": "Second"},
        ],
    })
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        preview = client.post("/api/playlists", json={
            "url": "https://music.youtube.com/playlist?list=PLroadtrip",
        }).json()
        response = client.post("/api/playlists/download", json={
            "preview_id": preview["preview_id"],
            "video_ids": [VIDEO_ID, "M7lc1UVf-VE"],
            "audio_format": "flac",
            "embed_metadata": False,
        })
        assert response.status_code == 202
        assert {job["audio_format"] for job in client.get("/api/jobs").json()["jobs"]} == {"flac"}
        assert {job["embed_metadata"] for job in client.get("/api/jobs").json()["jobs"]} == {False}


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
    jobs = [manager.start(f'{index:011d}') for index in range(125)]
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
        assert playlist.status_code == 200
        preview = playlist.json()
        assert client.get("/api/jobs").json()["jobs"] == []
        playlist = client.post("/api/playlists/download", json={
            "preview_id": preview["preview_id"],
            "video_ids": [VIDEO_ID, "M7lc1UVf-VE"],
        })
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
        job_id = client.post("/api/downloads", json={"video_id": VIDEO_ID, "audio_format": "original"}).json()["job_id"]
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


