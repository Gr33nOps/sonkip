import json
import pytest
from app import engine


def test_spotify_metadata_is_matched_to_youtube(monkeypatch):
    import urllib.request
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args):
            data={'props': {'pageProps': {'state': {'data': {'entity': {
                'name': 'My playlist', 'trackList': [
                    {'title': 'Let It Happen', 'subtitle': 'Tame Impala', 'duration': 468000},
                    {'title': 'Unknown song', 'subtitle': 'Someone', 'duration': 100000}
                ]}}}}}}
            return ('<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>').encode()
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: Response())
    monkeypatch.setattr(engine, 'search_music', lambda query, cookiefile=None: [
        {'video_id': 'NMRhx71bGo4', 'title': 'Let It Happen', 'artist': 'Tame Impala', 'duration': 468}
    ] if 'Let It Happen' in query else [])
    result=engine.extract_playlist('https://open.spotify.com/playlist/1OVBwZJ6f0NBnELz4l2vo7?si=ignored')
    assert result['entries'][0]['video_id']=='NMRhx71bGo4'
    assert result['entries'][0]['matched_from']=='Spotify'
    assert result['unmatched'][0]['title']=='Unknown song'
    assert result['source_count']==2


def test_soundcloud_import_uses_full_track_metadata_not_preview_duration(monkeypatch):
    class Extractor:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def extract_info(self,url,download):
            assert download is False
            return {'title':'Album','entries':[{'title':'Retina Show (Unreleased Demo)', 'uploader':'Tame Impala','duration':30}]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)
    monkeypatch.setattr(engine, 'search_music', lambda *a: [
        {'video_id':'abcdefghijk','title':'Tame Impala - Retina Show (Unreleased Demo)','artist':'Tame Impala','duration':305}])
    result=engine.extract_playlist('https://soundcloud.com/tame-impala/sets/lonerism-10-year-anniversary')
    assert result['entries'][0]['video_id']=='abcdefghijk'
    assert result['entries'][0]['matched_from']=='SoundCloud'


@pytest.mark.parametrize('url', ['https://open.spotify.com.evil.test/playlist/abc', 'http://127.0.0.1/playlist/abc'])
def test_untrusted_playlist_hosts_are_rejected(url):
    with pytest.raises(ValueError): engine.extract_playlist(url)


@pytest.mark.parametrize('candidate', [
    {'video_id':'abcdefghijk','title':'Let It Happen (live)','artist':'Tame Impala','duration':468},
    {'video_id':'abcdefghijk','title':'Let It Happen','artist':'Someone else','duration':468},
    {'video_id':'abcdefghijk','title':'Let It Happen','artist':'Tame Impala','duration':30},
])
def test_matching_rejects_wrong_version_artist_and_preview(monkeypatch, candidate):
    monkeypatch.setattr(engine, 'search_music', lambda *a: [candidate])
    assert engine._match_track({'title':'Let It Happen','artist':'Tame Impala','duration':468}, None) is None
