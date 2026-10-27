from app.engine import audio_download_options, youtube_access_options


def test_android_m4a_can_fall_back_to_an_aac_mp4_stream(monkeypatch):
    monkeypatch.setenv('SONKIP_ANDROID_TOKENS', '1')

    options = audio_download_options('m4a')

    assert options['format'] == (
        'bestaudio[ext=m4a][acodec!=none]/'
        'bestaudio[acodec^=mp4a][ext=m4a]/'
        'best[ext=mp4][acodec^=mp4a]'
    )


def test_android_m4a_fallback_extracts_audio_from_mp4(monkeypatch, tmp_path):
    import shutil
    import sys
    import time
    import types
    from pathlib import Path
    import app.engine as engine
    from app.storage import MusicStore

    extracted = []

    class Browser:
        @staticmethod
        def awaitReady():
            return None

    class AudioExtractor:
        @staticmethod
        def extractM4a(source, target):
            extracted.append((source, target))
            shutil.copyfile(source, target)

    def java_class(name):
        if name.endswith('PublicTokenProvider'):
            return Browser
        if name.endswith('AndroidAudioExtractor'):
            return AudioExtractor
        raise AssertionError(name)

    class Mp4YoutubeDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download):
            assert download is True
            output = Path(self.options['outtmpl'].replace('%(ext)s', 'mp4'))
            output.write_bytes(b'mp4-with-aac')
            self.options['progress_hooks'][0]({'status': 'finished'})
            return {
                'title': 'AAC fallback', 'uploader': 'Example Artist', 'duration': 12,
                'requested_downloads': [{'acodec': 'mp4a.40.2'}],
            }

    monkeypatch.setenv('SONKIP_ANDROID_TOKENS', '1')
    monkeypatch.setitem(sys.modules, 'java', types.SimpleNamespace(jclass=java_class))
    monkeypatch.setattr(engine, 'YoutubeDL', Mp4YoutubeDL)
    manager = engine.DownloadManager(MusicStore(tmp_path))
    try:
        job_id = manager.start('K3Qzzggn--s', 'm4a')
        for _ in range(100):
            job = manager.get_job(job_id)
            if job['status'] in ('complete', 'error'):
                break
            time.sleep(.01)
        assert job['status'] == 'complete', job
        track = manager.store.get_track(job_id)
        assert track['extension'] == 'm4a'
        assert extracted == [
            (str(tmp_path / 'tracks' / f'{job_id}.mp4'), str(tmp_path / 'tracks' / f'{job_id}.m4a'))
        ]
        assert not (tmp_path / 'tracks' / f'{job_id}.mp4').exists()
    finally:
        manager.pool.shutdown(wait=True)


def test_android_m4a_without_aac_saves_available_original_audio(monkeypatch, tmp_path):
    import sys
    import time
    import types
    from pathlib import Path
    import app.engine as engine
    from app.storage import MusicStore

    class Browser:
        @staticmethod
        def awaitReady(): pass

    class Extractor:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download):
            if 'ext=m4a' in self.options['format']:
                raise RuntimeError('Requested format is not available')
            Path(self.options['outtmpl'].replace('%(ext)s', 'webm')).write_bytes(b'opus-audio')
            return {'title': 'Song', 'artist': 'Artist', 'duration': 200,
                    'requested_downloads': [{'acodec': 'opus'}]}

    monkeypatch.setenv('SONKIP_ANDROID_TOKENS', '1')
    monkeypatch.setitem(sys.modules, 'java', types.SimpleNamespace(jclass=lambda _: Browser))
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)
    manager = engine.DownloadManager(MusicStore(tmp_path))
    try:
        job_id = manager.start('K3Qzzggn--s', 'm4a')
        for _ in range(100):
            job = manager.get_job(job_id)
            if job['status'] in ('complete', 'error'): break
            time.sleep(.01)
        assert job['status'] == 'complete', job
        assert job['format_fallback'] == 'webm'
        assert manager.store.get_track(job_id)['extension'] == 'webm'
    finally:
        manager.pool.shutdown(wait=True)


def test_android_browser_startup_failure_finishes_job_with_retryable_error(monkeypatch, tmp_path):
    import sys
    import types
    import time
    import app.engine as engine
    from app.storage import MusicStore

    class UnavailableBrowser:
        @staticmethod
        def awaitReady():
            raise RuntimeError('YouTube connection could not start. Tap Retry.')

    class UnexpectedExtractor:
        def __init__(self, options):
            raise RuntimeError('Extraction started before the browser was ready')

    monkeypatch.setenv('SONKIP_ANDROID_TOKENS', '1')
    monkeypatch.setitem(sys.modules, 'java', types.SimpleNamespace(jclass=lambda name: UnavailableBrowser))
    monkeypatch.setattr(engine, 'YoutubeDL', UnexpectedExtractor)
    manager = engine.DownloadManager(MusicStore(tmp_path))
    try:
        job_id = manager.start('K3Qzzggn--s')
        for _ in range(100):
            job = manager.get_job(job_id)
            if job['status'] == 'error':
                break
            time.sleep(.01)
        assert job['status'] == 'error'
        assert job['error'] == 'YouTube connection could not start. Tap Retry.'
        assert manager.store.list_tracks() == []
    finally:
        manager.pool.shutdown(wait=True)


def test_android_token_provider_uses_mobile_web_without_cookies(monkeypatch):
    monkeypatch.setenv('SONKIP_QUICKJS', '/native/libqjs.so')
    monkeypatch.setenv('SONKIP_ANDROID_TOKENS', '1')
    options = youtube_access_options()
    assert options['extractor_args']['youtube']['player_client'] == ['mweb']
    assert options['js_runtimes']['quickjs']['path'] == '/native/libqjs.so'
    assert 'cookiefile' not in options
