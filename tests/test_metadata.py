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


def test_failed_primary_artwork_falls_back_to_youtube_cover(tmp_path, monkeypatch):
    fixture = tmp_path / 'song.m4a'
    make_m4a(fixture)
    def fetch(request, **kwargs):
        if request.full_url.startswith('https://i.scdn.co/'):
            raise OSError('Artwork CDN unavailable')
        return ArtworkResponse()
    monkeypatch.setattr(engine.urllib.request, 'urlopen', fetch)
    assert engine._embed_music_metadata(fixture, {'title': 'Song', 'artist': 'Artist',
        'artwork_url': 'https://i.scdn.co/image/missing'}, 'NMRhx71bGo4')
    assert bytes(MP4(fixture).tags['covr'][0]) == JPEG_1PX


def test_playlist_placeholder_cannot_turn_a_known_album_into_a_single():
    details = engine.resolve_music_metadata({'title': 'Song', 'artist': 'Artist', 'album': 'Real Album'},
        {'title': 'Song', 'release_type': 'single', 'track_number': 92})
    assert details['album'] == 'Real Album'
    assert details['release_type'] == 'album'
    # A playlist position does not identify a track's position within its album.
    assert details['track_number'] is None


def test_original_webm_download_preserves_opus_audio_and_embeds_album_cover(tmp_path, monkeypatch):
    fixture = tmp_path / 'source.webm'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3', '-c:a', 'libopus', '-y', str(fixture)], check=True)
    monkeypatch.setattr(engine, 'YoutubeDL', downloader_for(fixture, {
        'track': 'Song', 'artist': 'Artist', 'album': 'Album', 'duration': 1, 'acodec': 'opus'}))
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **kw: ArtworkResponse())
    manager = engine.DownloadManager(MusicStore(tmp_path / 'library'))
    try:
        job_id = manager.start('NMRhx71bGo4', 'original')
        manager.pool.shutdown(wait=True)
        job = manager.get_job(job_id)
        assert job['status'] == 'complete', job
        song = manager.store.get_track(job_id)
        assert song['extension'] == 'opus'
        audio = OggOpus(manager.store.path_for(song))
        assert audio['album'] == ['Album']
        assert 'metadata_block_picture' in audio
        assert song['codec'] == 'opus'
    finally:
        manager.pool.shutdown(wait=True)


def test_repair_adds_missing_album_and_art_to_existing_song_without_redownload(tmp_path, monkeypatch):
    store = MusicStore(tmp_path / 'library')
    fixture = store.tracks_dir / ('a'*32 + '.m4a')
    make_m4a(fixture)
    store.add_track({'id': 'a'*32, 'video_id': 'NMRhx71bGo4', 'title': 'Artist - Song (Audio)',
        'artist': 'Artist', 'duration': 200, 'filename': fixture.name, 'extension': 'm4a',
        'bytes': fixture.stat().st_size})
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [
        {'video_id': 'abcdefghijk', 'title': 'Song', 'artist': 'Artist', 'album_artist': 'Artist',
         'album': 'Real Album', 'duration': 200, 'release_id': 'MPREb_release', 'source_quality': 'official'}])
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **kw: ArtworkResponse())
    monkeypatch.setattr(engine, 'YoutubeDL', lambda *a: pytest.fail('Repair must reuse saved audio'))
    manager = engine.DownloadManager(store)
    try:
        manager.repair_library()
        manager.pool.shutdown(wait=True)
        song = store.get_track('a'*32)
        assert song['title'] == 'Song'
        assert song['album'] == 'Real Album'
        assert bytes(MP4(store.path_for(song)).tags['covr'][0]) == JPEG_1PX
        assert manager.repair_status()['completed'] == 1
    finally:
        manager.pool.shutdown(wait=True)


def test_original_mp4_audio_is_saved_in_a_player_readable_m4a_container(tmp_path, monkeypatch):
    fixture = tmp_path / 'source.mp4'
    make_m4a(fixture)
    monkeypatch.setattr(engine, 'YoutubeDL', downloader_for(fixture, {
        'track': 'Song', 'artist': 'Artist', 'album': 'Album', 'acodec': 'mp4a.40.2'}))
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **kw: ArtworkResponse())
    manager = engine.DownloadManager(MusicStore(tmp_path / 'library'))
    try:
        job_id = manager.start('NMRhx71bGo4', 'original')
        manager.pool.shutdown(wait=True)
        assert manager.get_job(job_id)['status'] == 'complete'
        song = manager.store.get_track(job_id)
        assert song['extension'] == 'm4a'
        assert bytes(MP4(manager.store.path_for(song)).tags['covr'][0]) == JPEG_1PX
    finally:
        manager.pool.shutdown(wait=True)


def test_label_channel_name_is_not_used_as_the_credited_performer():
    details = engine.resolve_music_metadata({'title': 'Joji - Glimpse of Us (Official Audio)', 'uploader': '88rising'})
    assert details['artist'] == 'Joji'
    assert details['title'] == 'Glimpse of Us'


def test_repair_can_correct_legacy_label_artist_using_a_confirmed_catalog_match(tmp_path, monkeypatch):
    store = MusicStore(tmp_path / 'library')
    fixture = store.tracks_dir / ('a'*32 + '.m4a')
    make_m4a(fixture)
    store.add_track({'id': 'a'*32, 'video_id': 'NMRhx71bGo4', 'title': 'Joji - Glimpse of Us',
        'artist': '88rising', 'duration': 200, 'filename': fixture.name, 'extension': 'm4a',
        'bytes': fixture.stat().st_size})
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [
        {'video_id': 'abcdefghijk', 'title': 'Glimpse of Us', 'artist': 'Joji', 'album': 'SMITHEREENS',
         'duration': 200, 'source_quality': 'official'}])
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **kw: ArtworkResponse())
    manager = engine.DownloadManager(store)
    try:
        manager.repair_library();manager.pool.shutdown(wait=True)
        song = store.get_track('a'*32)
        assert song['artist'] == 'Joji'
        assert song['album'] == 'SMITHEREENS'
    finally:
        manager.pool.shutdown(wait=True)


def test_refreshing_mp3_tags_keeps_existing_cover_if_the_cdn_is_offline(tmp_path, monkeypatch):
    path = tmp_path / 'song.mp3';make_audio(path)
    monkeypatch.setattr(engine, '_download_artwork', lambda *a: (JPEG_1PX, 'image/jpeg'))
    assert engine._embed_music_metadata(path, {'title': 'Song', 'artist': 'Artist'}, 'NMRhx71bGo4')
    monkeypatch.setattr(engine, '_download_artwork', lambda *a: None)
    assert engine._embed_music_metadata(path, {'title': 'Song', 'artist': 'Artist', 'album': 'Album'}, 'NMRhx71bGo4')
    assert bytes(MP3(path).tags.getall('APIC')[0].data) == JPEG_1PX


def test_spotify_structured_release_date_becomes_a_real_year_and_date():
    details = engine.resolve_music_metadata({'title': 'Nights', 'artist': 'Frank Ocean',
        'album': 'Blonde', 'release_date': {'day': 20, 'month': 8, 'year': 2016}})
    assert details['release_date'] == '2016-08-20'
    assert details['year'] == '2016'


def test_explicit_song_and_singer_credits_take_priority_over_a_label_channel():
    details = engine.resolve_music_metadata({'title': 'Afreen Afreen with lyrics and translations',
        'uploader': 'Saregama Music', 'description': 'Song: Afreen Afreen\nSinger: Ustad Nusrat Fateh Ali Khan\n'})
    assert details['artist'] == 'Ustad Nusrat Fateh Ali Khan'
    assert details['title'] == 'Afreen Afreen'
    assert details['album'] == ''


def test_repair_reads_source_credits_when_the_catalog_cannot_identify_a_release(tmp_path, monkeypatch):
    store = MusicStore(tmp_path / 'library');fixture = store.tracks_dir / ('a'*32 + '.m4a');make_m4a(fixture)
    store.add_track({'id': 'a'*32, 'video_id': 'NMRhx71bGo4', 'title': 'Afreen Afreen with lyrics',
        'artist': 'Saregama Music', 'duration': 361, 'filename': fixture.name, 'extension': 'm4a', 'bytes': fixture.stat().st_size})
    class MetadataOnly:
        def __init__(self, _options): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, _url, download):
            assert download is False
            return {'title': 'Afreen Afreen with lyrics', 'uploader': 'Saregama Music',
                'description': 'Song: Afreen Afreen\nSinger: Ustad Nusrat Fateh Ali Khan\n', 'duration': 361}
    monkeypatch.setattr(engine, 'YoutubeDL', MetadataOnly)
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **kw: ArtworkResponse())
    manager = engine.DownloadManager(store)
    try:
        manager.repair_library();manager.pool.shutdown(wait=True)
        song = store.get_track('a'*32)
        assert song['artist'] == 'Ustad Nusrat Fateh Ali Khan'
        assert song['title'] == 'Afreen Afreen'
        assert not song['album']
    finally:
        manager.pool.shutdown(wait=True)
