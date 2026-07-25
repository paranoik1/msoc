# За основу был взят код Ushiiro82:
# https://github.com/Ushiiro82/MelodyHub/blob/master/parsing/hitmo_parser.py

import logging
from typing import AsyncGenerator, Generator
from urllib.parse import quote

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup, Tag

try:
    from ..sound import Sound
    from ..utils import validate_and_return_absolute_url
except ImportError:
    from msoc.sound import Sound
    from msoc.utils import validate_and_return_absolute_url

logger = logging.getLogger("msoc.hitmo")

# Headers
HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}

URL = "https://rus.hitmotop.com/"


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
        url = validate_and_return_absolute_url(link.strip(), URL)
    except ValueError:
        logger.warning("Не удалось преобразовать URL скачивания: %s", link)
        return None

    return url


async def _create_soup_obj(url: str) -> BeautifulSoup:
    async with ClientSession(headers=HEADERS) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.text()

    return BeautifulSoup(content, "lxml")


def parse_tracks(soup: BeautifulSoup) -> Generator[Sound, None]:
    all_songs = soup.select(".tracks__item")
    logger.info("hitmo: найдено треков: %d", len(all_songs))

    for track_info in all_songs:
        name = get_song_name(track_info)
        artist = get_song_artist(track_info)
        url = get_download_song_url(track_info)

        if not name:
            logger.debug("Пропуск трека без названия")
            continue

        if not url:
            logger.warning('Пропуск трека без ссылки на скачивание')
            continue

        logger.debug("hitmo: найден трек '%s' — %s", artist or "N/A", name)
        yield Sound(title=name, artist=artist, url=url)


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на rus.hitmotop.com.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    encoded_query = quote(query)
    search_url = f"{URL}search?q={encoded_query}"

    logger.info("hitmo: поиск по запросу '%s'", query)

    try:
        soup = await _create_soup_obj(search_url)
    except ClientError as exc:
        logger.error("hitmo: ошибка HTTP-запроса: %s", exc)
        return

    for sound in parse_tracks(soup):
        yield sound


async def search_full(query: str) -> AsyncGenerator[Sound, None]:
    encoded_query = quote(query)
    current_url = f"{URL}search?q={encoded_query}"

    logger.info("hitmo: поиск по запросу '%s'", query)

    while True:
        try:
            soup = await _create_soup_obj(current_url)
        except ClientError as exc:
            logger.error("hitmo: ошибка HTTP-запроса: %s", exc)
            return

        for sound in parse_tracks(soup):
            yield sound

        page_links = soup.select('ul.pagination__list > li > a')
        if not page_links:
            logger.info('Не найден список страниц - завершаем парсинг')
            break

        next_page_links = [link for link in page_links if link.get_text(strip=True) == ">"]
        if len(next_page_links) == 0:
            logger.info('Не найден элемент следующей ссылки - заврешаем парсинг')
            break

        next_url = next_page_links[0].get('href')
        # For mypy
        if not (next_url and isinstance(next_url, str)):
            logger.info('У ссылки не обнаружен href или href не того типа - завершаем парсинг')
            break

        current_url = validate_and_return_absolute_url(next_url, URL)
        logger.debug('Следующая страница: %s', current_url)


if __name__ == '__main__':
    import asyncio

    async def main():
        async for sound in search_full("Sweet Dreams"):
            print(sound.title, sound.url)

    asyncio.run(main())
