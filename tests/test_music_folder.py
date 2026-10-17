from app.storage import MusicStore
from test_filenames import track


def test_desktop_folder_api_updates_and_reports_choice(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    app = create_app(tmp_path / 'private')
    client = TestClient(app, base_url='http://127.0.0.1')
    folder = tmp_path / 'public'
    folder.mkdir()
    response = client.post('/api/music-folder', json={'folder': str(folder)})
    assert response.status_code == 200
    assert client.get('/api/music-folder').json()['folder'] == str(folder.resolve())
    assert client.post('/api/music-folder', json={'folder': 'relative-path'}).status_code == 422


def test_folder_copies_existing_and_future_music_and_remembers_choice(tmp_path):
    store = MusicStore(tmp_path / 'private')
    store.add_track(track(store))
    folder = tmp_path / 'Music'
    folder.mkdir()
    store.set_music_folder(str(folder))
    assert (folder / 'Artist - Song.webm').read_bytes() == b'audio'
    reopened = MusicStore(store.home)
    reopened.add_track(track(reopened, key='b', title='Next'))
    assert (folder / 'Artist - Next.webm').read_bytes() == b'audio'
    assert len(reopened.list_tracks()) == 2
    reopened.set_music_folder(str(folder))
    assert len(list(folder.iterdir())) == 2


def test_folder_never_overwrites_unrelated_files_and_can_disable(tmp_path):
    store = MusicStore(tmp_path / 'private')
    folder = tmp_path / 'Music'
    folder.mkdir()
    (folder / 'Artist - Song.webm').write_bytes(b'other music')
    store.set_music_folder(str(folder))
    store.add_track(track(store))
    assert (folder / 'Artist - Song.webm').read_bytes() == b'other music'
    assert (folder / 'Artist - Song (2).webm').read_bytes() == b'audio'
    store.set_music_folder('')
    store.add_track(track(store, key='b', title='Next'))
    assert not (folder / 'Artist - Next.webm').exists()


def test_unavailable_folder_does_not_lose_internal_download(tmp_path):
    store = MusicStore(tmp_path / 'private')
    folder = tmp_path / 'Music'
    folder.mkdir()
    store.set_music_folder(str(folder))
    folder.rmdir()
    store.add_track(track(store))
    assert len(store.list_tracks()) == 1
    assert store.music_folder_status()['error']
