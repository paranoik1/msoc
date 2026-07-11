import logging
from os.path import basename
from typing import Any, AsyncGenerator

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup, Tag

from ..sound import Sound

logger = logging.getLogger("msoc.zaycev_net")

URL = "https://zaycev.net"
API_URL = URL + "/api/external/track"
SEARCH_URL = URL + "/search?query_search="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": URL,
    "Connection": "keep-alive",
    "Referer": URL,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

DATA_TEMPLATE_TRACKS_META = {"trackIds": [], "subscription": False}


def get_id(li: Tag) -> str | None:
    tag = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(1)"
    )
    if tag is None:
        return None

    href = tag.attrs.get("href")
    if not href or not isinstance(href, str):
        return None

    track_id = basename(href).split(".")[0]
    return track_id


TrackInfo = tuple[int, str | None, str | None]


async def get_tracks_download_hashes(
    session: ClientSession, track_ids: list[str]
) -> AsyncGenerator[TrackInfo, None]:
    data = DATA_TEMPLATE_TRACKS_META.copy()
    data["trackIds"] = track_ids

    try:
        async with session.post(
            url=API_URL + "/filezmeta", json=data, headers=HEADERS
        ) as response:
            if response.status != 200:
                logger.warning(
                    "zaycev_net: HTTP %d при запросе метаданных треков", response.status
                )
                return
            json_data: Any = await response.json()
    except ClientError as exc:
        logger.error("zaycev_net: ошибка HTTP-запроса метаданных: %s", exc)
        return
    except ValueError as exc:
        logger.error("zaycev_net: ошибка парсинга JSON метаданных: %s", exc)
        return

    if not isinstance(json_data, dict) or "tracks" not in json_data:
        logger.warning("zaycev_net: неожиданный формат ответа метаданных")
        return

    for track_meta in json_data["tracks"]:
        track_id: int | None = track_meta.get("id")
        if track_id is None:
            logger.warn('zaycev_net: не был получен track_id с объекта, пропускаем')
            continue

        download_hash: str | None = track_meta.get("download")
        streaming_hash: str | None = track_meta.get("streaming")

        yield track_id, download_hash, streaming_hash


async def get_url(session: ClientSession, download_hash: str) -> str | None:
    try:
        async with session.get(API_URL + "/download/" + download_hash) as response:
            if response.status != 200:
                logger.warning(
                    "zaycev_net: HTTP %d при запросе URL скачивания", response.status
                )
                return None
            url = await response.text()
            return url
    except ClientError as exc:
        logger.error("zaycev_net: ошибка при получении URL скачивания: %s", exc)
        return None


async def get_streaming_url(session: ClientSession, streaming_hash: str) -> str | None:
    try:
        async with session.get(API_URL + "/play/" + streaming_hash) as response:
            if response.status != 200:
                logger.warning(
                    "zaycev_net: HTTP %d при запросе streaming URL", response.status
                )
                return None
            json_data: Any = await response.json()
            url = json_data.get("url")
            return url if isinstance(url, str) else None
    except ClientError as exc:
        logger.error("zaycev_net: ошибка при получении streaming URL: %s", exc)
        return None
    except ValueError as exc:
        logger.error("zaycev_net: ошибка парсинга JSON streaming ответа: %s", exc)
        return None


def get_name(li: Tag) -> str:
    span = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(1) > span:nth-child(1)"
    )
    if span is None:
        return ""
    return span.get_text(strip=True)


def get_artist(li: Tag) -> str:
    span = li.select_one(
        "div:nth-child(1) > div:nth-child(1) > article:nth-child(2) > a:nth-child(2) > span"
    )
    if span is None:
        return ""
    return span.get_text(strip=True)


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на zaycev.net через HTML-парсинг и API.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    logger.info("zaycev_net: поиск по запросу '%s'", query)
    session = ClientSession()
    try:
        async with session.get(SEARCH_URL + query) as response:
            if response.status != 200:
                logger.warning(
                    "zaycev_net: HTTP %d при поисковом запросе", response.status
                )
                return
            html_text = await response.text()

        html = BeautifulSoup(html_text, "html.parser")
        ul = html.find("ul", attrs={"class": "xm4ofx-1 itNyE"})
        if ul is None or not isinstance(ul, Tag):
            logger.debug("zaycev_net: не найдена таблица с результатами поиска")
            return

        tracks_info: dict[str, tuple[str, str]] = {}
        for li in ul.find_all("li"):
            track_id = get_id(li)
            if track_id is None:
                continue

            name = get_name(li)
            artist = get_artist(li)

            tracks_info[track_id] = (name, artist)

        logger.info("zaycev_net: найдено треков в HTML: %d", len(tracks_info))

        async for tid, download_hash, streaming_hash in get_tracks_download_hashes(
            session, list(tracks_info.keys())
        ):
            track_info = tracks_info.get(str(tid))
            if track_info is None:
                continue

            name, artist = track_info

            url: str | None = None
            if download_hash:
                url = await get_url(session, download_hash)
            elif streaming_hash:
                url = await get_streaming_url(session, streaming_hash)

            if not url:
                logger.warning(
                    "zaycev_net: не удалось получить URL для '%s' — %s", artist, name
                )
                continue

            yield Sound(name, url, artist)
    except ClientError as exc:
        logger.error("zaycev_net: ошибка HTTP-запроса поиска: %s", exc)
        return
    finally:
        await session.close()

