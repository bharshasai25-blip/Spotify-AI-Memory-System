from urllib.parse import quote
from typing import Optional

def spotify_search_url(title: str, artist: Optional[str] = None) -> str:
    query=' '.join(part.strip() for part in (title,artist or '') if isinstance(part,str) and part.strip())
    return f'https://open.spotify.com/search/{quote(query)}' if query else 'https://open.spotify.com/search'

def is_verified_spotify_track_url(value: Optional[str]) -> bool:
    if not isinstance(value,str): return False
    from urllib.parse import urlparse
    parsed=urlparse(value.strip())
    parts=[part for part in parsed.path.split('/') if part]
    return parsed.scheme=='https' and parsed.netloc.casefold() in {'open.spotify.com','www.open.spotify.com'} and len(parts)==2 and parts[0]=='track' and bool(parts[1]) and '?' not in parts[1] and '#' not in parts[1]

def spotify_link_for_entity(title: str, artist: Optional[str] = None, verified_track_url: Optional[str] = None) -> dict[str,str]:
    if is_verified_spotify_track_url(verified_track_url):
        return {'spotify_url':verified_track_url.strip(),'spotify_url_type':'track','spotify_url_label':'Play on Spotify'}
    return {'spotify_url':spotify_search_url(title,artist),'spotify_url_type':'search','spotify_url_label':'Search on Spotify'}

def spotify_link_for_catalog_entity(title: str, entity_type: str, artist: Optional[str] = None, verified_url: Optional[str] = None) -> dict[str,str]:
    from urllib.parse import urlparse
    expected={'track':'track','artist':'artist','album':'album'}.get(str(entity_type).casefold())
    if isinstance(verified_url,str):
        parsed=urlparse(verified_url.strip())
        parts=[part for part in parsed.path.split('/') if part]
        if parsed.scheme=='https' and parsed.netloc.casefold() in {'open.spotify.com','www.open.spotify.com'} and expected and len(parts)==2 and parts[0]==expected and parts[1] and '?' not in parts[1] and '#' not in parts[1]:
            return {'spotify_url':verified_url.strip(),'spotify_url_type':expected,'spotify_url_label':{'track':'Play on Spotify','artist':'Open artist on Spotify','album':'Open album on Spotify'}[expected]}
    return {'spotify_url':spotify_search_url(title,artist),'spotify_url_type':'search','spotify_url_label':'Search on Spotify'}
