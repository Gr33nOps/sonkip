from app.engine import youtube_access_options


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
