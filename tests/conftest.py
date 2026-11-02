import pytest
from app import engine


@pytest.fixture(autouse=True)
def offline_music_catalog(monkeypatch):
    # Unit tests never contact the public music catalog. Catalog contract tests
    # replace this HTTP boundary with a complete, hand-checked response.
    monkeypatch.setattr(engine, '_request_music_catalog', lambda *args: {})
    monkeypatch.setattr(engine, '_spotify_album_info', lambda *args: {})
    engine._ARTWORK_HOST_RETRY.clear()
