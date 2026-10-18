import json
import threading
import urllib.request
from pathlib import Path

from app.android_server import create_android_server
from fastapi.testclient import TestClient
from app.main import create_app
import pytest


def request_json(url: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    # Leave room for SQLite's 15-second busy timeout on a loaded build host.
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.load(response)


@pytest.mark.parametrize('platform', ['desktop', 'android'])
def test_download_actions_are_available_on_both_platforms(tmp_path, monkeypatch, platform):
    server = None
    if platform == 'android':
        server = create_android_server(tmp_path, tmp_path, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        manager = server.manager
        def post(path):
            return request_json(f'http://127.0.0.1:{server.server_port}' + path, 'POST', {})[1]
    else:
        app = create_app(tmp_path)
        client = TestClient(app, base_url='http://localhost')
        manager = app.state.manager
        def post(path):
            response = client.post(path, json={})
            assert response.status_code == 200
            return response.json()
    monkeypatch.setattr(manager, '_run', lambda *args: None)
    try:
        first = manager.start('dQw4w9WgXcQ')
        assert post(f'/api/jobs/{first}/cancel')['ok'] is True
        second = manager.start('M7lc1UVf-VE')
        manager.futures[second].result(timeout=3)
        manager._update(second, status='error', error='Connection lost')
        result = post('/api/jobs/retry-failed')
        assert result['job_ids'] == [second]
        assert manager.get_job(first)['cancelled'] is True
        assert manager.get_job(second)['status'] == 'queued'
    finally:
        manager.pool.shutdown(wait=True)
        if server:
            server.shutdown()
            server.server_close()
        else:
            client.close()


def test_android_server_serves_health_and_frontend(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>sonkip android</h1>", encoding="utf-8")
    (static_dir / "app.js").write_text("console.log('sonkip')", encoding="utf-8")

    server = create_android_server(tmp_path / "music", static_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = request_json(f"{base_url}/api/health")
        assert status == 200
        assert health["ok"] is True
        assert health["platform"] == "android"

        with urllib.request.urlopen(f"{base_url}/", timeout=3) as response:
            assert response.status == 200
            assert b"sonkip android" in response.read()

        with urllib.request.urlopen(f"{base_url}/static/app.js", timeout=3) as response:
            assert response.headers.get_content_type() == "text/javascript"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_android_server_rejects_invalid_download_id(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("sonkip", encoding="utf-8")

    server = create_android_server(tmp_path / "music", static_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            request_json(
                f"{base_url}/api/downloads",
                method="POST",
                body={"video_id": "not-valid"},
            )
        except urllib.error.HTTPError as error:
            assert error.code == 422
            payload = json.load(error)
            assert payload["detail"] == "Invalid video ID"
        else:
            raise AssertionError("invalid video ID should be rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_android_server_applies_selected_format_to_song_download(tmp_path: Path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("sonkip", encoding="utf-8")
    server = create_android_server(tmp_path / "music", static_dir, port=0)
    monkeypatch.setattr(server.manager, "_run", lambda *args: None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, payload = request_json(
            f"{base_url}/api/downloads",
            method="POST",
            body={
                "video_id": "dQw4w9WgXcQ",
                "audio_format": "m4a",
                "embed_metadata": False,
            },
        )
        server.manager.futures[payload["job_id"]].result(timeout=3)

        assert status == 202
        assert server.manager.get_job(payload["job_id"])["audio_format"] == "m4a"
        assert server.manager.get_job(payload["job_id"])["embed_metadata"] is False
    finally:
        server.manager.pool.shutdown(wait=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_android_server_applies_selected_format_to_playlist_downloads(tmp_path: Path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("sonkip", encoding="utf-8")
    server = create_android_server(tmp_path / "music", static_dir, port=0)
    monkeypatch.setattr(server.manager, "_run", lambda *args: None)
    monkeypatch.setattr(
        "app.android_server.extract_playlist",
        lambda *args: {
            "title": "Test playlist",
            "entries": [{"video_id": "dQw4w9WgXcQ", "title": "Test song"}],
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, payload = request_json(
            f"{base_url}/api/playlists",
            method="POST",
            body={
                "url": "https://example.com/playlist",
                "audio_format": "opus",
                "embed_metadata": False,
            },
        )
        job_id = payload["jobs"][0]["job_id"]
        server.manager.futures[job_id].result(timeout=3)

        assert status == 202
        assert server.manager.get_job(job_id)["audio_format"] == "opus"
        assert server.manager.get_job(job_id)["embed_metadata"] is False
    finally:
        server.manager.pool.shutdown(wait=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_android_server_accepts_android_string_paths(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("sonkip", encoding="utf-8")

    server = create_android_server(str(tmp_path / "music"), str(static_dir), port=0)
    try:
        assert server.store.tracks_dir.parent == (tmp_path / "music").resolve()
        assert server.static_dir == static_dir.resolve()
    finally:
        server.server_close()


def test_android_server_keeps_youtube_auth_local(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("sonkip", encoding="utf-8")
    server = create_android_server(tmp_path / "music", static_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    cookies = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tlocal-session\n"
    )
    try:
        assert request_json(f"{base_url}/api/auth/youtube")[1] == {"connected": False}
        assert request_json(
            f"{base_url}/api/auth/youtube", "POST", {"cookies": cookies}
        )[1] == {"connected": True}
        assert server.store.youtube_cookies_path.read_text(encoding="utf-8") == cookies
        assert request_json(f"{base_url}/api/auth/youtube", "DELETE")[1] == {
            "connected": False
        }
        assert not server.store.youtube_cookies_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
