"""Music metadata is embedded in the audio file other players receive."""
import base64
import shutil
import subprocess
import time

import imageio_ffmpeg
import pytest
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus

import app.engine as engine
from app.storage import MusicStore


JPEG_1PX = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABAf/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPxB//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPxB//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxB//9k="
)


def make_m4a(path):
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.1",
            "-c:a", "aac", "-y", str(path),
        ],
        check=True,
    )


def make_audio(path):
    codec = {
        ".mp3": ["-c:a", "libmp3lame"],
        ".flac": ["-c:a", "flac"],
        ".opus": ["-c:a", "libopus"],
    }[path.suffix]
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.1",
            *codec, "-y", str(path),
        ],
        check=True,
    )


def wait_for(manager, job_id):
    for _ in range(200):
        job = manager.get_job(job_id)
        if job["status"] in ("complete", "error"):
            return job
        time.sleep(0.01)
    raise AssertionError("download did not finish")


def downloader_for(fixture, info):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            target = self.options["outtmpl"].replace("%(ext)s", fixture.suffix.lstrip("."))
            shutil.copyfile(fixture, target)
            self.options["progress_hooks"][0]({"status": "finished"})
            return dict(info)

    return FakeYoutubeDL


class ArtworkResponse:
    headers = {"Content-Type": "image/jpeg"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size=-1):
        return JPEG_1PX


def test_new_m4a_downloads_contain_music_tags_and_cover_by_default(tmp_path, monkeypatch):
    fixture = tmp_path / "source.m4a"
    make_m4a(fixture)

    info = {
        "track": "Afterglow",
        "title": "Example Artist - Afterglow",
        "artist": "Example Artist",
        "album": "Night Drive",
        "track_number": 3,
        "release_year": 2026,
        "genre": "Electronic",
        "duration": 30,
        "requested_downloads": [{"acodec": "mp4a.40.2", "abr": 128}],
    }
    monkeypatch.setattr(engine, "YoutubeDL", downloader_for(fixture, info))
    monkeypatch.setattr(engine.urllib.request, "urlopen", lambda *args, **kwargs: ArtworkResponse())
    manager = engine.DownloadManager(MusicStore(tmp_path / "library"))
    try:
        job_id = manager.start("NMRhx71bGo4", "m4a")
        job = wait_for(manager, job_id)

        assert job["status"] == "complete", job
        track = manager.store.get_track(job_id)
        tags = MP4(manager.store.path_for(track)).tags
        assert tags["\xa9nam"] == ["Afterglow"]
        assert tags["\xa9ART"] == ["Example Artist"]
        assert tags["aART"] == ["Example Artist"]
        assert tags["\xa9alb"] == ["Night Drive"]
        assert tags["trkn"] == [(3, 0)]
        assert tags["\xa9day"] == ["2026"]
        assert tags["\xa9gen"] == ["Electronic"]
        assert bytes(tags["covr"][0]) == JPEG_1PX
    finally:
        manager.pool.shutdown(wait=True)


@pytest.mark.parametrize(
    ("audio_format", "extension"),
    [("mp3", ".mp3"), ("flac", ".flac"), ("opus", ".opus")],
)
def test_desktop_formats_contain_standard_music_tags_and_cover(
    audio_format, extension, tmp_path, monkeypatch
):
    fixture = tmp_path / ("source" + extension)
    make_audio(fixture)
    info = {
        "track": "Afterglow",
        "artist": "Example Artist",
        "album": "Night Drive",
        "duration": 30,
        "requested_downloads": [{"acodec": audio_format, "abr": 160}],
    }
    monkeypatch.setattr(engine, "YoutubeDL", downloader_for(fixture, info))
    monkeypatch.setattr(engine.urllib.request, "urlopen", lambda *args, **kwargs: ArtworkResponse())
    manager = engine.DownloadManager(MusicStore(tmp_path / "library"))
    try:
        job_id = manager.start("NMRhx71bGo4", audio_format)
        job = wait_for(manager, job_id)
        assert job["status"] == "complete", job
        assert job["metadata_embedded"] is True
        path = manager.store.path_for(manager.store.get_track(job_id))
        if audio_format == "mp3":
            tags = MP3(path).tags
            assert tags.getall("TIT2")[0].text == ["Afterglow"]
            assert tags.getall("TPE1")[0].text == ["Example Artist"]
            assert tags.getall("TALB")[0].text == ["Night Drive"]
            assert bytes(tags.getall("APIC")[0].data) == JPEG_1PX
        elif audio_format == "flac":
            audio = FLAC(path)
            assert audio["title"] == ["Afterglow"]
            assert audio["artist"] == ["Example Artist"]
            assert audio["album"] == ["Night Drive"]
            assert bytes(audio.pictures[0].data) == JPEG_1PX
        else:
            audio = OggOpus(path)
            assert audio["title"] == ["Afterglow"]
            assert audio["artist"] == ["Example Artist"]
            assert audio["album"] == ["Night Drive"]
            assert "metadata_block_picture" in audio
    finally:
        manager.pool.shutdown(wait=True)


def test_music_tags_and_artwork_can_be_disabled_for_a_download(tmp_path, monkeypatch):
    fixture = tmp_path / "source.m4a"
    make_m4a(fixture)
    info = {
        "track": "Afterglow",
        "artist": "Example Artist",
        "duration": 30,
        "requested_downloads": [{"acodec": "mp4a.40.2", "abr": 128}],
    }
    monkeypatch.setattr(engine, "YoutubeDL", downloader_for(fixture, info))
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("artwork was requested")),
    )
    manager = engine.DownloadManager(MusicStore(tmp_path / "library"))
    try:
        job_id = manager.start("NMRhx71bGo4", "m4a", embed_metadata=False)
        job = wait_for(manager, job_id)

        assert job["status"] == "complete", job
        assert job["embed_metadata"] is False
        assert job["metadata_embedded"] is False
        track = manager.store.get_track(job_id)
        tags = MP4(manager.store.path_for(track)).tags
        assert "\xa9nam" not in tags
        assert "covr" not in tags
    finally:
        manager.pool.shutdown(wait=True)


def test_text_tags_survive_when_cover_art_is_unavailable(tmp_path, monkeypatch):
    fixture = tmp_path / "source.m4a"
    make_m4a(fixture)
    info = {
        "track": "Afterglow",
        "artist": "Example Artist",
        "duration": 30,
        "requested_downloads": [{"acodec": "mp4a.40.2", "abr": 128}],
    }
    monkeypatch.setattr(engine, "YoutubeDL", downloader_for(fixture, info))
    monkeypatch.setattr(
        engine.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    manager = engine.DownloadManager(MusicStore(tmp_path / "library"))
    try:
        job_id = manager.start("NMRhx71bGo4", "m4a")
        job = wait_for(manager, job_id)

        assert job["status"] == "complete", job
        assert job["metadata_embedded"] is True
        tags = MP4(manager.store.path_for(manager.store.get_track(job_id))).tags
        assert tags["\xa9nam"] == ["Afterglow"]
        assert tags["\xa9ART"] == ["Example Artist"]
        assert "covr" not in tags
    finally:
        manager.pool.shutdown(wait=True)
