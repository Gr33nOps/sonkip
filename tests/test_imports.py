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


def test_matching_prefers_verified_artist_over_reupload(monkeypatch):
    monkeypatch.setattr(engine, 'search_music', lambda *a: [
        {'video_id':'abcdefghijk','title':'Tame Impala - Let It Happen','artist':'Music archive','duration':468},
        {'video_id':'NMRhx71bGo4','title':'Let It Happen (Official Audio)','artist':'Tame Impala','duration':468,'channel_is_verified':True},
    ])
    result = engine._match_track({'title':'Let It Happen','artist':'Tame Impala','duration':468}, None)
    assert result['video_id'] == 'NMRhx71bGo4'


def test_matching_flags_missing_duration_for_review(monkeypatch):
    monkeypatch.setattr(engine, 'search_music', lambda *a: [
        {'video_id':'abcdefghijk','title':'Let It Happen','artist':'Tame Impala','duration':None},
    ])
    result = engine._match_track({'title':'Let It Happen','artist':'Tame Impala','duration':468}, None)
    assert result.get('needs_review') is True


def test_search_ranking_prefers_official_exact_match_and_hides_weak_results():
    items = [
        {'id': 'abcdefghijk', 'title': 'Song cover', 'uploader': 'Small channel', 'duration': 200, 'view_count': 100},
        {'id': 'NMRhx71bGo4', 'title': 'Artist - Song (Official Audio)', 'uploader': 'Artist - Topic',
         'duration': 201, 'view_count': 500000, 'channel_is_verified': True, 'album': 'Real Album'},
        {'id': 'M7lc1UVf-VE', 'title': 'Unrelated upload', 'uploader': 'Archive', 'duration': 120, 'view_count': 20},
    ]
    results = engine._rank_search_results('Artist Song', items)
    assert [item['video_id'] for item in results] == ['NMRhx71bGo4']
    assert results[0]['album'] == 'Real Album'
    assert results[0]['is_best_match'] is True


def test_metadata_normalization_keeps_release_identity_consistent_without_inventing_album():
    first = engine.resolve_music_metadata({
        'track': '  First\u00a0Song ', 'artist': 'Artist - Topic', 'album': '  Night   Drive ',
        'album_artist': 'Artist', 'track_number': '1', 'release_date': '20261002',
        'duration': 200.8, 'release_id': ' release-1 ',
    })
    second = engine.resolve_music_metadata({
        'track': 'Second Song', 'artist': 'Artist', 'album': 'Night Drive',
        'album_artist': 'Artist', 'track_number': 2, 'release_date': '2026-10-02',
        'duration': 204,
    }, {'release_id': 'release-1'})
    single = engine.resolve_music_metadata({'track': 'Standalone', 'artist': 'Artist'})
    official = engine.resolve_music_metadata({'title': 'Artist - Song (Official Audio)', 'artist': 'Artist - Topic'})
    assert first['album'] == second['album'] == 'Night Drive'
    assert first['artist'] == second['artist'] == 'Artist'
    assert first['release_id'] == second['release_id'] == 'release-1'
    assert first['track_number'] == 1
    assert first['release_date'] == '2026-10-02'
    assert single['album'] == ''
    assert single['release_type'] == 'single'
    assert official['title'] == 'Song'


def test_youtube_music_album_tracks_share_one_release(monkeypatch):
    class Extractor:
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, _url, download):
            assert download is False
            return {'title': 'Night Drive', 'album_artist': 'Artist', 'thumbnail': 'https://i.ytimg.com/vi/albumcover/hqdefault.jpg', 'entries': [
                {'id': 'abcdefghijk', 'title': 'First', 'artist': 'Artist', 'playlist_index': 1, 'thumbnail': 'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'},
                {'id': 'NMRhx71bGo4', 'title': 'Second', 'artist': 'Artist feat. Guest', 'playlist_index': 2, 'thumbnail': 'https://i.ytimg.com/vi/NMRhx71bGo4/hqdefault.jpg'},
            ]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)
    result = engine.extract_playlist('https://music.youtube.com/playlist?list=OLAK5uy_release123')
    assert {track['album'] for track in result['entries']} == {'Night Drive'}
    assert {track['release_id'] for track in result['entries']} == {'OLAK5uy_release123'}
    assert [track['track_number'] for track in result['entries']] == [1, 2]
    assert {track['artwork_url'] for track in result['entries']} == {'https://i.ytimg.com/vi/albumcover/hqdefault.jpg'}
    assert {track['album_artist'] for track in result['entries']} == {'Artist'}


def test_youtube_music_album_assigns_track_order_when_provider_omits_playlist_index(monkeypatch):
    class Extractor:
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, _url, download):
            assert download is False
            return {'title': 'Album', 'artist': 'Artist', 'entries': [
                {'id': 'abcdefghijk', 'title': 'First', 'artist': 'Artist'},
                {'id': 'NMRhx71bGo4', 'title': 'Second', 'artist': 'Artist'},
            ]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)

    result = engine.extract_playlist('https://music.youtube.com/playlist?list=OLAK5uy_release123')

    assert [track['track_number'] for track in result['entries']] == [1, 2]


def test_release_deduplication_does_not_merge_different_tracks_without_numbers():
    saved = {'title': 'First', 'artist': 'Artist', 'album': 'Album', 'release_id': 'release-1'}
    incoming = {'title': 'Second', 'artist': 'Artist', 'album': 'Album', 'release_id': 'release-1'}
    assert engine._same_recording(saved, incoming) is False
