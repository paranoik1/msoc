from os.path import basename
from typing import Any, AsyncGenerator

import bs4
from aiohttp import ClientSession

from ..sound import Sound

URL = "https://zaycev.net"
API_URL = URL + "/api/external/track"
SEARCH_URL = URL + "/search?query_search="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://zaycev.net",
    "Connection": "keep-alive",
    "Referer": "https://zaycev.net/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

DATA_TEMPLATE_TRACKS_META = {"trackIds": [], "subscription": False}


def get_id(li: bs4.Tag) -> str:
    href = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(1)"
    ).attrs.get("href")

    track_id = basename(href).split(".")[0]
    return track_id


async def get_tracks_download_hashes(
    session: ClientSession, track_ids: list[str]
) -> AsyncGenerator[int, str]:
    data = DATA_TEMPLATE_TRACKS_META.copy()
    data["trackIds"] = track_ids

    async with session.post(
        url=API_URL + "/filezmeta", json=data, headers=HEADERS
    ) as response:
        json_data = await response.json()

    for track_meta in json_data["tracks"]:
        track_id = track_meta["id"]
        download_hash = track_meta["download"]
        streaming_hash = track_meta["streaming"]

        yield track_id, download_hash, streaming_hash


async def get_url(session: ClientSession, download_hash: str) -> str:
    async with session.get(API_URL + "/download/" + download_hash) as response:
        url = await response.text()
        return url


async def get_streaming_url(session: ClientSession, streaming_hash: str) -> str:
    async with session.get(API_URL + "/play/" + streaming_hash) as response:
        json_data = await response.json()
        return json_data["url"]


def get_name(li: bs4.Tag) -> str:
    span = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(1) > span:nth-child(1)"
    )
    return span.get_text(strip=True)


def get_artist(li: bs4.Tag) -> str:
    span = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(2) > span"
    )
    return span.get_text(strip=True)


async def search(query: str):
    async with ClientSession() as session:
        async with session.get(SEARCH_URL + query) as response:
            html_text = await response.text()

        html = bs4.BeautifulSoup(html_text, "html.parser")
        ul = html.find("ul", attrs={"class", "xm4ofx-1 itNyE"})
        if not ul:
            return

        tracks_info = dict()
        for li in ul.find_all("li"):
            name = get_name(li)
            artist = get_artist(li)
            track_id = get_id(li)

            tracks_info[track_id] = (name, artist)

        async for track_id, download_hash, streaming_hash in get_tracks_download_hashes(
            session, list(tracks_info.keys())
        ):
            track_info = tracks_info[str(track_id)]
            name = track_info[0]
            artist = track_info[1]

            if download_hash:
                url = await get_url(session, download_hash)
            else:
                url = await get_streaming_url(session, streaming_hash)

            yield Sound(name, url, artist)
