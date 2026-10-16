import json
import zipfile
import pytest
from app.storage import MusicStore


def test_backup_contains_readable_audio_and_playlists_but_no_auth(tmp_path):
    store = MusicStore(tmp_path / 'library')
    (store.tracks_dir / 'original.webm').write_bytes(b'OggS audio')
    store.add_track(dict(id='a'*32, video_id='abcdefghijk', title='Song', artist='Artist',
                         duration=120, filename='original.webm', bytes=10, extension='webm', codec='opus', abr=128))
    store.youtube_cookies_path.parent.mkdir()
    store.youtube_cookies_path.write_text('private authentication')
    assert hasattr(store, 'export_backup'), 'Library needs a portable backup'
    target=tmp_path/'backup.zip'
    store.export_backup(target, [{'id':'mix','name':'My mix','tracks':['a'*32]}])
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {'sonkip.json','tracks/Artist - Song.webm'}
        assert archive.read('tracks/Artist - Song.webm') == b'OggS audio'
        manifest=json.loads(archive.read('sonkip.json'))
        assert manifest['playlists'][0]['name'] == 'My mix'
        assert manifest['tracks'][0]['id'] == 'a'*32
    restored=MusicStore(tmp_path/'restored')
    result=restored.import_backup(target)
    assert result['playlists'][0]['tracks'] == ['a'*32]
    assert restored.list_tracks()[0]['title'] == 'Song'
    assert restored.path_for(restored.list_tracks()[0]).read_bytes() == b'OggS audio'
    restored.import_backup(target)
    assert len(restored.list_tracks()) == 1


def test_restore_rejects_unsafe_names_before_writing_audio(tmp_path):
    store=MusicStore(tmp_path/'library')
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as output:
        output.writestr('sonkip.json',json.dumps({'version':1,'playlists':[], 'tracks':[{
            'id':'b'*32,'video_id':'abcdefghijk','title':'Song','artist':'Artist','filename':'../../outside.webm',
            'bytes':4,'extension':'webm','duration':1,'codec':'opus','abr':128}]}))
        output.writestr('tracks/../../outside.webm',b'data')
    assert hasattr(store, 'import_backup'), 'Library needs safe backup restore'
    with pytest.raises(ValueError):store.import_backup(archive)
    assert store.list_tracks() == []
    assert not (tmp_path/'outside.webm').exists()


def test_desktop_backup_download_and_restore(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from io import BytesIO
    with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
        response=client.get('/api/backup')
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            assert json.loads(archive.read('sonkip.json'))['tracks'] == []
        restored=client.post('/api/backup/restore', content=response.content, headers={'Content-Type':'application/zip'})
        assert restored.status_code == 200
        assert restored.json()['imported'] == 0
        assert client.post('/api/backup/restore', content=b'not a zip').status_code == 422
