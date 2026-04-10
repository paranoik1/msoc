# За основу был взят код Ushiiro82:
# https://github.com/Ushiiro82/MelodyHub/blob/master/parsing/hitmo_parser.py

import logging
from typing import AsyncGenerator
from urllib.parse import quote

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup, Tag

from ..sound import Sound
from ..utils import validate_and_return_absolute_url

logger = logging.getLogger("msoc.hitmo")

# Headers
HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}

# URL сайта
BASE_URL = "https://rus.hitmotop.com/"


def get_song_name(track_info: Tag) -> str:
    """Извлекает название трека из элемента .track__title."""
    song_name = track_info.find(class_="track__title")
    return song_name.text.strip() if song_name else ""


def get_song_artist(track_info: Tag) -> str:
    """Извлекает имя исполнителя из элемента .track__desc."""
    song_artist = track_info.find(class_="track__desc")
    return song_artist.text.strip() if song_artist else ""


def get_download_song_url(track_info: Tag) -> str | None:
    """Извлекает ссылку на скачивание трека и преобразует её в абсолютный URL."""
    tag_a = track_info.find("a", class_="track__download-btn")
    if tag_a is None:
        return None

    link = tag_a.get("href")
    if not link or not isinstance(link, str):
        return None

    try:
        url = validate_and_return_absolute_url(link.strip(), BASE_URL)
    except ValueError:
        logger.warning("Не удалось преобразовать URL скачивания: %s", link)
        return None

    return url


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на rus.hitmotop.com.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    encoded_query = quote(query)
    search_url = f"{BASE_URL}search?q={encoded_query}"
    logger.info("hitmo: поиск по запросу '%s'", query)

    try:
        async with ClientSession(headers=HEADERS) as session:
            async with session.get(search_url) as response:
                if response.status != 200:
                    logger.warning(
                        "hitmo: HTTP %d при запросе %s", response.status, search_url
                    )
                    return
                content = await response.text()
    except ClientError as exc:
        logger.error("hitmo: ошибка HTTP-запроса: %s", exc)
        return

    soup = BeautifulSoup(content, "lxml")
    all_songs = soup.select(".tracks__item")
    logger.info("hitmo: найдено треков: %d", len(all_songs))

    for track_info in all_songs:
        name = get_song_name(track_info)
        artist = get_song_artist(track_info)
        url = get_download_song_url(track_info)

        if not name:
            logger.debug("hitmo: пропуск трека без названия")
            continue

        logger.debug("hitmo: найден трек '%s' — %s", artist or "N/A", name)
        yield Sound(title=name, artist=artist, url=url)
