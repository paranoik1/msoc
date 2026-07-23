import logging
import re
from typing import AsyncGenerator

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup, Tag

from ..sound import Sound

logger = logging.getLogger("msoc.trekson")

URL = "https://trekson.net/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}


def _parse_tracks(html: str, query: str) -> list[Sound]:
    soup = BeautifulSoup(html, "html.parser")
    tracks: list[Sound] = []

    query_lower = query.lower()

    for item in soup.find_all(class_="js-item"):
        if not isinstance(item, Tag):
            continue

        title = item.get("data-title")
        artist = item.get("data-artist")
        track_url = item.get("data-track")

        if not title or not track_url:
            continue

        title_str = str(title).strip()
        artist_str = str(artist).strip() if artist else ""
        track_url_str = str(track_url).strip()

        if query_lower not in title_str.lower() and query_lower not in artist_str.lower():
            continue

        tracks.append(Sound(title=title_str, url=track_url_str, artist=artist_str or None))

    return tracks


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на trekson.net.
    Поскольку сайт использует клиентский поиск (JavaScript),
    парсер загружает главную страницу и фильтрует результаты по запросу локально.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    logger.info("trekson: поиск по запросу '%s'", query)

    try:
        async with ClientSession(headers=HEADERS) as session:
            async with session.post(URL, data={"q": query}) as response:
                if response.status != 200:
                    logger.warning(
                        "trekson: HTTP %d при запросе %s", response.status, URL
                    )
                    return
                html = await response.text()
    except ClientError as exc:
        logger.error("trekson: ошибка HTTP-запроса: %s", exc)
        return

    tracks = _parse_tracks(html, query)
    logger.info("trekson: найдено треков: %d", len(tracks))

    for sound in tracks:
        yield sound
