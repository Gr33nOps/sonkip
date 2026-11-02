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


def test_search_prefers_artist_audio_over_lyrics_upload():
    items = [
        {'id': 'abcdefghijk', 'title': 'Artist - Song (Lyrics)', 'uploader': 'Lyrics Vault', 'view_count': 9000000},
        {'id': 'NMRhx71bGo4', 'title': 'Artist - Song (Official Audio)', 'uploader': 'Artist - Topic', 'view_count': 10000},
    ]
    results = engine._rank_search_results('Artist Song', items)
    assert results[0]['video_id'] == 'NMRhx71bGo4'


def test_search_does_not_treat_verified_lyrics_as_the_official_recording():
    items = [
        {'id': 'abcdefghijk', 'title': 'Artist - Song (Lyrics)', 'uploader': 'Lyrics Vault',
         'channel_is_verified': True, 'view_count': 9000000},
        {'id': 'NMRhx71bGo4', 'title': 'Artist - Song (Audio)', 'uploader': 'Artist - Topic',
         'view_count': 10000},
    ]
    assert engine._rank_search_results('Artist Song', items)[0]['video_id'] == 'NMRhx71bGo4'


def test_official_words_in_a_reupload_title_do_not_beat_an_artist_topic_channel():
    items = [
        {'id': 'abcdefghijk', 'title': 'Artist - Song (Official Audio)', 'uploader': 'Music Reuploads',
         'view_count': 9000000},
        {'id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Artist', 'uploader': 'Artist - Topic',
         'view_count': 1000},
    ]
    assert engine._rank_search_results('Artist Song', items)[0]['video_id'] == 'NMRhx71bGo4'


def test_verified_reupload_with_another_artist_in_title_is_not_official():
    result = engine._search_result({
        'id': 'abcdefghijk', 'title': 'Artist - Song (Official Audio)',
        'uploader': 'Music Archive', 'channel_is_verified': True,
    })
    assert result['source_quality'] == 'community'


def test_search_does_not_select_a_making_of_video_as_the_song():
    items = [
        {'id': 'abcdefghijk', 'title': "The Making of 'Song' | Footnotes", 'artist': 'Artist',
         'uploader': 'Artist', 'channel_is_verified': True, 'view_count': 10000000},
        {'id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Artist',
         'uploader': 'Artist - Topic', 'view_count': 1000},
    ]
    assert engine._rank_search_results('Artist Song', items)[0]['video_id'] == 'NMRhx71bGo4'


def test_import_match_prefers_artist_audio_over_lyrics_upload(monkeypatch):
    monkeypatch.setattr(engine, 'search_music', lambda *a: [
        {'video_id': 'abcdefghijk', 'title': 'Song (Lyrics)', 'artist': 'Artist', 'duration': 200},
        {'video_id': 'NMRhx71bGo4', 'title': 'Song (Official Audio)', 'artist': 'Artist', 'duration': 200,
         'source_quality': 'official'},
    ])
    result = engine._match_track({'title': 'Song', 'artist': 'Artist', 'duration': 200}, None)
    assert result['video_id'] == 'NMRhx71bGo4'


def test_import_does_not_auto_match_a_lyrics_only_upload(monkeypatch):
    monkeypatch.setattr(engine, 'search_music', lambda *a: [
        {'video_id': 'abcdefghijk', 'title': 'Song (Lyrics)', 'artist': 'Artist',
         'duration': 200, 'is_lyrics_upload': True},
    ])
    assert engine._match_track({'title': 'Song', 'artist': 'Artist', 'duration': 200}, None) is None


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
    assert single['release_type'] == 'unknown'
    assert official['title'] == 'Song'


def test_youtube_music_album_tracks_share_one_release(monkeypatch):
    class Extractor:
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, _url, download):
            assert download is False
            return {'title': 'Night Drive', 'album_artist': 'Artist', 'thumbnail': 'https://i.ytimg.com/vi/albumcover/hqdefault.jpg', 'entries': [
                {'id': 'abcdefghijk', 'title': 'First', 'artist': 'Artist', 'uploader': 'Artist - Topic', 'playlist_index': 1, 'thumbnail': 'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'},
                {'id': 'NMRhx71bGo4', 'title': 'Second', 'artist': 'Artist feat. Guest', 'uploader': 'Artist feat. Guest - Topic', 'playlist_index': 2, 'thumbnail': 'https://i.ytimg.com/vi/NMRhx71bGo4/hqdefault.jpg'},
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
                {'id': 'abcdefghijk', 'title': 'First', 'artist': 'Artist', 'uploader': 'Artist - Topic'},
                {'id': 'NMRhx71bGo4', 'title': 'Second', 'artist': 'Artist', 'uploader': 'Artist - Topic'},
            ]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)

    result = engine.extract_playlist('https://music.youtube.com/playlist?list=OLAK5uy_release123')

    assert [track['track_number'] for track in result['entries']] == [1, 2]


def test_release_deduplication_does_not_merge_different_tracks_without_numbers():
    saved = {'title': 'First', 'artist': 'Artist', 'album': 'Album', 'release_id': 'release-1'}
    incoming = {'title': 'Second', 'artist': 'Artist', 'album': 'Album', 'release_id': 'release-1'}
    assert engine._same_recording(saved, incoming) is False


def test_spotify_import_reads_all_250_tracks_with_release_metadata(monkeypatch):
    offsets = []
    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return self.body
    def fetch(request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        if '/embed/' in url:
            state = {'data': {'entity': {'name': 'TOP', 'trackList': [
                {'title': 'Song 0', 'subtitle': 'Artist', 'duration': 200000}]}},
                'settings': {'session': {'accessToken': 'public-guest-token'}}}
            return Response(('<script id="__NEXT_DATA__">'+json.dumps(
                {'props': {'pageProps': {'state': state}}})+'</script>').encode())
        payload = json.loads(request.data)
        offset = payload['variables']['offset']
        offsets.append(offset)
        items = [{'itemV2': {'data': {'uri': f'spotify:track:{i:022d}',
            'name': f'Song {i}', 'artists': {'items': [{'profile': {'name': 'Artist'}}]},
            'duration': {'totalMilliseconds': 200000}, 'trackNumber': 4,
            'albumOfTrack': {'uri': 'spotify:album:album-1', 'name': 'Real Album',
                'coverArt': {'sources': [{'url': 'https://i.scdn.co/image/cover', 'width': 640}]}}}}}
            for i in range(offset, min(offset+100, 250))]
        return Response(json.dumps({'data': {'playlistV2': {'name': 'TOP', 'content': {
            'items': items, 'totalCount': 250, 'pagingInfo': {'nextOffset': offset+100 if offset<200 else None}}}}}).encode())
    monkeypatch.setattr(engine.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(engine, '_match_track', lambda track, _: {
        'video_id': f"{int(track['title'].split()[-1]):011d}", 'title': track['title'], 'artist': 'Artist', 'duration': 200})
    result = engine.extract_playlist('https://open.spotify.com/playlist/regressionfixture12345')
    assert result['source_count'] == 250
    assert len(result['entries']) == 250
    assert offsets == [0, 100, 200]
    assert result['entries'][-1]['title'] == 'Song 249'
    assert result['entries'][-1]['album'] == 'Real Album'
    assert result['entries'][-1]['track_number'] == 4
    assert result['entries'][-1]['artwork_url'] == 'https://i.scdn.co/image/cover'


def test_import_matching_searches_past_a_truncated_top_result(monkeypatch):
    def search(query, *_args, **kwargs):
        if query == 'Artist Song':
            return [{'video_id': 'abcdefghijk', 'title': 'Song (Making Of)', 'artist': 'Artist', 'duration': 200}]
        return [{'video_id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Artist',
            'duration': 200, 'source_quality': 'official'}]
    monkeypatch.setattr(engine, 'search_music', search)
    result = engine._match_track({'title': 'Song', 'artist': 'Artist', 'duration': 200}, None)
    assert result['video_id'] == 'NMRhx71bGo4'


def test_music_catalog_search_preserves_official_album_and_artist(monkeypatch):
    watch = {'watchEndpoint': {'videoId': 'NMRhx71bGo4', 'watchEndpointMusicSupportedConfigs': {
        'watchEndpointMusicConfig': {'musicVideoType': 'MUSIC_VIDEO_TYPE_ATV'}}}}
    def run(text, browse=None):
        return {'text': text, **({'navigationEndpoint': {'browseEndpoint': {'browseId': browse}}} if browse else {})}
    row = {'musicResponsiveListItemRenderer': {'flexColumns': [
        {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [{'text': 'Song', 'navigationEndpoint': watch}]}}},
        {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [run('Artist', 'UCartist'),
            run(' • '), run('Real Album', 'MPREb_release'), run(' • '), run('3:20')]}}}],
        'thumbnail': {'musicThumbnailRenderer': {'thumbnail': {'thumbnails': [
            {'url': 'https://lh3.googleusercontent.com/cover', 'width': 600}]}}}}}
    monkeypatch.setattr(engine, '_request_music_catalog', lambda *a: {'contents': [row]})
    results = engine._catalog_search('Artist Song')
    assert results[0]['source_quality'] == 'official'
    assert results[0]['artist'] == 'Artist'
    assert results[0]['album'] == 'Real Album'
    assert results[0]['release_id'] == 'MPREb_release'
    assert results[0]['duration'] == 200


def test_artist_name_in_another_performers_title_is_not_a_match(monkeypatch):
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [
        {'video_id': 'abcdefghijk', 'title': 'DRAKE ONE DANCE', 'artist': 'mistah isolation',
         'duration': 174, 'source_quality': 'official'}])
    monkeypatch.setattr(engine, 'search_music', lambda *a: [])
    assert engine._match_track({'title': 'One Dance', 'artist': 'Drake, Wizkid, Kyla', 'duration': 174}, None) is None


def test_repeated_playlist_recordings_are_reviewed_and_queued_once(monkeypatch):
    monkeypatch.setattr(engine, '_spotify_tracks', lambda *_: ('Repeats', [
        {'title': 'Song', 'artist': 'Artist'}, {'title': 'Song', 'artist': 'Artist'}], ''))
    monkeypatch.setattr(engine, '_match_track', lambda *_: {
        'video_id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Artist'})
    result = engine.extract_playlist('https://open.spotify.com/playlist/regressionfixture12345')
    assert result['source_count'] == 2
    assert len(result['entries']) == 1
    assert result['duplicate_count'] == 1


def test_youtube_playlist_replaces_lyrics_upload_with_the_official_recording(monkeypatch):
    class Extractor:
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, _url, download):
            return {'title': 'Mix', 'entries': [{'id': 'abcdefghijk', 'title': 'Artist - Song (Lyrics)',
                'uploader': 'Lyrics Vault', 'duration': 200}]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [{
        'video_id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Artist', 'album': 'Real Album',
        'source_quality': 'official', 'duration': 200, 'artwork_url': 'https://i.scdn.co/image/cover'}])
    result = engine.extract_playlist('https://youtube.com/playlist?list=PLmix')
    assert result['source_count'] == 1
    assert result['entries'][0]['video_id'] == 'NMRhx71bGo4'
    assert result['entries'][0]['album'] == 'Real Album'


def test_feature_credits_after_official_audio_label_do_not_hide_the_song(monkeypatch):
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [{
        'video_id': 'NMRhx71bGo4', 'title': 'Get Lucky (Radio Edit - feat. Pharrell Williams and Nile Rodgers)',
        'artist': 'Daft Punk, Pharrell Williams, Nile Rodgers', 'album': 'Get Lucky',
        'source_quality': 'official', 'duration': 249}])
    track = engine.resolve_music_metadata({'title': 'Get Lucky (Official Audio) ft. Pharrell Williams, Nile Rodgers',
        'artist': 'Daft Punk', 'duration': 249})
    result = engine._match_track(track, None, _catalog_only=True)
    assert result is not None
    assert result['album'] == 'Get Lucky'


def test_album_metadata_can_identify_a_video_edit_without_importing_it_as_the_full_recording(monkeypatch):
    monkeypatch.setattr(engine, '_catalog_search', lambda *a: [{
        'video_id': 'NMRhx71bGo4', 'title': 'Lucidity', 'artist': 'Tame Impala',
        'album': 'InnerSpeaker', 'source_quality': 'official', 'duration': 272}])
    monkeypatch.setattr(engine, 'search_music', lambda *a: [])
    track = {'title': 'Lucidity', 'artist': 'Tame Impala', 'duration': 234}
    assert engine._match_track(track, None, _catalog_only=True)['album'] == 'InnerSpeaker'
    assert engine._match_track(track, None) is None


def test_youtube_album_prefix_and_owner_do_not_split_the_release(monkeypatch):
    class Extractor:
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, *_args, **_kwargs):
            return {'title': 'Album - Currents', 'uploader': 'Tame Impala - Topic', 'entries': [
                {'id': 'NMRhx71bGo4', 'title': 'Song', 'artist': 'Tame Impala', 'uploader': 'Tame Impala - Topic'}]}
    monkeypatch.setattr(engine, 'YoutubeDL', Extractor)
    result = engine.extract_playlist('https://music.youtube.com/playlist?list=OLAK5uy_release')
    assert result['entries'][0]['album'] == 'Currents'
    assert result['entries'][0]['album_artist'] == 'Tame Impala'
