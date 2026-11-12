from spotify_ai_memory_backend_memory_pipeline.backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity, spotify_search_url, is_verified_spotify_track_url

def test_search_url_is_generated_and_encoded():
    assert spotify_search_url('Galliyan','Ankit Tiwari') == 'https://open.spotify.com/search/Galliyan%20Ankit%20Tiwari'

def test_only_track_page_is_verified_as_track_url():
    assert is_verified_spotify_track_url('https://open.spotify.com/track/abc123')
    assert not is_verified_spotify_track_url('https://open.spotify.com/search/Galliyan')
    assert not is_verified_spotify_track_url('https://open.spotify.com/artist/abc123')

def test_track_uses_verified_url_when_available():
    result=spotify_link_for_catalog_entity('Galliyan','track','Ankit Tiwari','https://open.spotify.com/track/abc123')
    assert result['spotify_url']=='https://open.spotify.com/track/abc123'
    assert result['spotify_url_type']=='track'

def test_track_uses_search_fallback_without_persisting_mapping():
    result=spotify_link_for_catalog_entity('Galliyan','track','Ankit Tiwari','https://open.spotify.com/search/Galliyan')
    assert result['spotify_url']=='https://open.spotify.com/search/Galliyan%20Ankit%20Tiwari'
    assert result['spotify_url_type']=='search'

def test_artist_mapping_requires_artist_url():
    result=spotify_link_for_catalog_entity('Ankit Tiwari','artist',None,'https://open.spotify.com/track/abc123')
    assert result['spotify_url']=='https://open.spotify.com/search/Ankit%20Tiwari'
    assert result['spotify_url_type']=='search'
