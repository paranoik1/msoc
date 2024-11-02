import aiohttp
from bs4 import BeautifulSoup, Tag

from msoc.sound import Sound


def get_name(track: Tag):
    track_title = track.get("data-title")

    return track_title or track.find("div", _class="track-title").text


def get_url(track: Tag):
    return track.get("data-track")


def get_artist(track: Tag):
    return track.get("data-artist")


async def search(url: str, query: str, **kwargs):
    data = f"do=search&subaction=search&story={query}"
    async with aiohttp.ClientSession(**kwargs) as session:
        async with session.post(url, data=data) as response:
            text = await response.text()

    html = BeautifulSoup(text, "lxml")
    
    for track in html.find_all("div", {"class": "track-item"}):
        name = get_name(track)
        download_url = get_url(track)
        artist = get_artist(track)

        yield Sound(name, download_url, artist)
