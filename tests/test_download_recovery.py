from concurrent.futures import ThreadPoolExecutor
import threading

from app.engine import DownloadManager
from app.storage import MusicStore
from test_app import FakeYoutubeDL
import app.engine as engine


def test_concurrent_requests_share_one_download(tmp_path, monkeypatch):
    gate = threading.Event()
    manager = DownloadManager(MusicStore(tmp_path))
    monkeypatch.setattr(manager, '_run', lambda *args: gate.wait(5))
    try:
        with ThreadPoolExecutor(max_workers=8) as callers:
            ids = list(callers.map(lambda _: manager.start('dQw4w9WgXcQ'), range(20)))
        assert len(set(ids)) == 1
        assert len(manager.list_jobs()) == 1
    finally:
        gate.set()
        manager.pool.shutdown(wait=True)


def test_interrupted_job_keeps_identity_on_retry(tmp_path, monkeypatch):
    manager = DownloadManager(MusicStore(tmp_path))
    monkeypatch.setattr(manager, '_run', lambda *args: None)
    job_id = manager.start('dQw4w9WgXcQ')
    manager.pool.shutdown(wait=True)
    manager._update(job_id, status='downloading', percent=42)
    partial = manager.store.tracks_dir / (job_id + '.webm.part')
    partial.write_bytes(b'partial audio')
    restored = DownloadManager(MusicStore(tmp_path))
    monkeypatch.setattr(restored, '_run', lambda *args: None)
    try:
        job = restored.get_job(job_id)
        assert job is not None
        assert job['status'] == 'error'
        assert job['percent'] == 42
        assert restored.start('dQw4w9WgXcQ') == job_id
        assert partial.read_bytes() == b'partial audio'
    finally:
        restored.pool.shutdown(wait=True)


def test_saved_song_is_reused_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'YoutubeDL', FakeYoutubeDL)
    manager = DownloadManager(MusicStore(tmp_path))
    original = manager.start('dQw4w9WgXcQ')
    manager.pool.shutdown(wait=True)
    restored = DownloadManager(MusicStore(tmp_path))
    try:
        result = restored.start('dQw4w9WgXcQ')
        assert restored.get_job(result)['status'] == 'complete'
        assert restored.get_job(result)['track_id'] == original
        assert restored.get_job(result)['title'] == 'Sample <Audio>'
    finally:
        restored.pool.shutdown(wait=True)
    assert len(restored.store.list_tracks()) == 1


def test_failed_download_preserves_partial_for_retry(tmp_path, monkeypatch):
    class Interrupted(FakeYoutubeDL):
        def extract_info(self, url, download):
            from pathlib import Path
            Path(self.opts['outtmpl'].replace('%(ext)s', 'webm.part')).write_bytes(b'partial')
            raise RuntimeError('connection reset')
    monkeypatch.setattr(engine, 'YoutubeDL', Interrupted)
    manager = DownloadManager(MusicStore(tmp_path))
    job = manager.start('dQw4w9WgXcQ')
    manager.pool.shutdown(wait=True)
    assert manager.get_job(job)['status'] == 'error'
    assert (manager.store.tracks_dir / (job + '.webm.part')).read_bytes() == b'partial'


def test_transient_failure_recovers_without_another_tap(tmp_path, monkeypatch):
    class Unstable(FakeYoutubeDL):
        attempts = 0
        def extract_info(self, url, download):
            Unstable.attempts += 1
            if Unstable.attempts < 3:
                raise RuntimeError('connection reset by peer')
            return super().extract_info(url, download)
    monkeypatch.setattr(engine, 'YoutubeDL', Unstable)
    manager = DownloadManager(MusicStore(tmp_path))
    job = manager.start('dQw4w9WgXcQ')
    manager.pool.shutdown(wait=True)
    assert manager.get_job(job)['status'] == 'complete'
    assert len(manager.store.list_tracks()) == 1


def test_cancelled_queue_does_not_download(tmp_path, monkeypatch):
    gate = threading.Event()
    manager = DownloadManager(MusicStore(tmp_path))
    manager.pool.submit(gate.wait, 5)
    manager.pool.submit(gate.wait, 5)
    monkeypatch.setattr(engine, 'YoutubeDL', FakeYoutubeDL)
    job = manager.start('dQw4w9WgXcQ')
    try:
        assert hasattr(manager, 'cancel'), 'Download queue needs cancellation'
        manager.cancel(job)
    finally:
        gate.set()
        manager.pool.shutdown(wait=True)
    assert manager.get_job(job)['cancelled'] is True
    assert manager.store.list_tracks() == []


def test_reopening_resumes_only_interrupted_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(DownloadManager, '_run', lambda *args: None)
    first = DownloadManager(MusicStore(tmp_path))
    interrupted = first.start('dQw4w9WgXcQ')
    failed = first.start('M7lc1UVf-VE')
    first.pool.shutdown(wait=True)
    first._update(failed, status='error', error='Private video')
    reopened = DownloadManager(MusicStore(tmp_path))
    try:
        assert hasattr(reopened, 'resume_interrupted'), 'Reopening must resume interrupted work'
        assert reopened.resume_interrupted() == [interrupted]
        assert reopened.get_job(failed)['status'] == 'error'
    finally:
        reopened.pool.shutdown(wait=True)


def test_fragment_is_never_mistaken_for_finished_audio(tmp_path, monkeypatch):
    class FragmentOnly(FakeYoutubeDL):
        def extract_info(self,url,download):
            from pathlib import Path
            Path(self.opts['outtmpl'].replace('%(ext)s','webm.part-Frag1')).write_bytes(b'incomplete')
            return {'title':'Song','uploader':'Artist'}
    monkeypatch.setattr(engine,'YoutubeDL',FragmentOnly)
    manager=DownloadManager(MusicStore(tmp_path))
    job=manager.start('dQw4w9WgXcQ')
    manager.pool.shutdown(wait=True)
    assert manager.get_job(job)['status'] == 'error'
    assert manager.store.list_tracks() == []
