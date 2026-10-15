import sqlite3
import pytest
from app.storage import MusicStore


def track(store, key='a', title='Song', artist='Artist'):
    row = dict(id=key * 32, video_id='abcdefghijk', title=title, artist=artist,
               duration=10, filename=key * 32 + '.webm', bytes=5,
               extension='webm', codec='opus', abr=128)
    (store.tracks_dir / row['filename']).write_bytes(b'audio')
    return row


def test_saved_files_have_readable_names_and_duplicates_are_preserved(tmp_path):
    store = MusicStore(tmp_path)
    for key in ('a', 'b'):
        store.add_track(track(store, key))
    rows = store.list_tracks()
    assert {r['filename'] for r in rows} == {'Artist - Song.webm', 'Artist - Song (2).webm'}
    assert all(store.path_for(r).read_bytes() == b'audio' for r in rows)


def test_migration_works_when_android_denies_hard_links(tmp_path, monkeypatch):
    import os
    def denied(*args, **kwargs):
        raise PermissionError(13, 'Permission denied')
    monkeypatch.setattr(os, 'link', denied)
    store = MusicStore(tmp_path)
    store.add_track(track(store))
    saved = store.list_tracks()[0]
    assert saved['filename'] == 'Artist - Song.webm'
    assert store.path_for(saved).read_bytes() == b'audio'


def test_existing_uuid_library_migrates_without_changing_ids(tmp_path):
    store = MusicStore(tmp_path)
    row = track(store, title='夜 / Song:?', artist='Artist')
    with sqlite3.connect(store.db_path) as db:
        db.execute('INSERT INTO tracks (id,video_id,title,artist,duration,filename,bytes,extension,codec,abr) VALUES (?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
    reopened = MusicStore(tmp_path)
    saved = reopened.get_track(row['id'])
    assert saved['filename'] == 'Artist - 夜 _ Song__.webm'
    assert reopened.path_for(saved).read_bytes() == b'audio'
    assert not (store.tracks_dir / row['filename']).exists()


@pytest.mark.parametrize('filename', ['../escape.webm', 'a/b.webm', 'a\\b.webm', 'C:escape.webm'])
def test_readable_names_still_reject_path_traversal(tmp_path, filename):
    with pytest.raises(ValueError):
        MusicStore(tmp_path).path_for({'filename': filename})
