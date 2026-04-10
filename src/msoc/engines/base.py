import aiohttp
import logging
import yarl
from bs4 import BeautifulSoup, Tag

from ..sound import Sound


logger = logging.getLogger('base_engine')


def get_name(track: Tag):
    track_title = track.get("data-title")
    track_title_v2 = track.find("div", _class="track-title")

    return track_title or track_title_v2.text # type: ignore


def validate_and_return_absolute_url(sound_url: str, base_url: str):
    if sound_url.startswith('https://'):
        return sound_url
    
    yarl_url = yarl.URL(base_url)
    try:
        host_site = yarl_url.origin()
    except ValueError:
        logger.error(f'Поисковой запрос должен быть абсолютным: {base_url}')
    absolute_url = host_site.with_path(sound_url)
    return str(absolute_url)


def get_url(track: Tag, search_url: str) -> str | None:
    url = track.get("data-track")
    if not isinstance(url, str):
        logger.warning(f'url должен быть типом str: {url=}')
        return None
    
    if url.startswith('https://'):
        return url
    
    yarl_url = yarl.URL(search_url)
    try:
        host_site = yarl_url.origin()
    except ValueError:
        logger.error(f'Поисковой запрос должен быть абсолютным: {search_url}')
    absolute_url = host_site.with_path(url)
    return str(absolute_url)


def get_artist(track: Tag) -> str | None:
    artist = track.get("data-artist")
    if not isinstance(artist, str):
        logger.warning(f'artist должен быть типом str: {artist=}')
        return None
    return artist



async def search(url: str, query: str, **kwargs):
    data = f"do=search&subaction=search&story={query}"
    async with aiohttp.ClientSession(**kwargs) as session:
        async with session.post(url, data=data) as response:
            text = await response.text()

    html = BeautifulSoup(text, "lxml")

    for track in html.find_all("div", {"class": "track-item"}):
        name = get_name(track)
        download_url = get_url(track, url)
        artist = get_artist(track)

        yield Sound(name, download_url, artist)
