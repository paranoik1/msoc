import aiohttp
from bs4 import BeautifulSoup, Tag

from msoc.sound import Sound


def get_name(track: Tag):
    track_title = track.get("data-title")

    if track_title:
        return track_title

    span = track.find("div", _class="track-title")
    return span.text
    

def get_url(track: Tag):
    data_track = track.get("data-track")

    if data_track:
        return data_track

    return ""


async def search(url: str, query: str, **kwargs):
    data = f"do=search&subaction=search&story={query}"
    async with aiohttp.ClientSession(**kwargs) as session:
        async with session.post(url, data=data) as response:
            text = await response.text()

    html = BeautifulSoup(text, "lxml")
    
    for track in html.find_all("div", {"class": "track-item"}):
        name = get_name(track)
        download_url = get_url(track)

        yield Sound(name, download_url)
