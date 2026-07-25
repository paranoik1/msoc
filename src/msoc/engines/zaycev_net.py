import json
import logging
from os.path import basename
from typing import Any, AsyncGenerator

from aiohttp import ClientError, ClientResponseError, ClientSession
from bs4 import BeautifulSoup, Tag

try:
    from ..sound import Sound
except ImportError:
    from msoc.sound import Sound

logger = logging.getLogger("msoc.zaycev_net")

URL = "https://zaycev.net"
SEARCH_URL = URL + "/search?query_search={query}&type=track"
API_URL = URL + "/api/external/track"
MAX_RETRY_ATTEMPTS = 3



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

TrackInfo = tuple[int, str | None, str | None]


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
                    "HTTP %d при запросе метаданных треков", response.status
                )
                return
            json_data: Any = await response.json()
    except ClientError as exc:
        logger.error("ошибка HTTP-запроса метаданных: %s", exc)
        return
    except ValueError as exc:
        logger.error("ошибка парсинга JSON метаданных: %s", exc)
        return

    if not isinstance(json_data, dict) or "tracks" not in json_data:
        logger.warning("неожиданный формат ответа метаданных")
        return

    for track_meta in json_data["tracks"]:
        track_id: int | None = track_meta.get("id")
        if track_id is None:
            logger.warn('не был получен track_id с объекта, пропускаем')
            continue

        download_hash: str | None = track_meta.get("download")
        streaming_hash: str | None = track_meta.get("streaming")

        yield track_id, download_hash, streaming_hash


async def get_download_url(session: ClientSession, download_hash: str) -> str | None:
    try:
        async with session.get(API_URL + "/download/" + download_hash) as response:
            if response.status != 200:
                logger.warning(
                    "HTTP %d при запросе URL скачивания", response.status
                )
                return None
            url = await response.text()
            return url
    except ClientError as exc:
        logger.error("ошибка при получении URL скачивания: %s", exc)
        return None


async def get_streaming_url(session: ClientSession, streaming_hash: str) -> str | None:
    try:
        async with session.get(API_URL + "/play/" + streaming_hash) as response:
            if response.status != 200:
                logger.warning(
                    "HTTP %d при запросе streaming URL", response.status
                )
                return None
            json_data: Any = await response.json()
            url = json_data.get("url")
            return url if isinstance(url, str) else None
    except ClientError as exc:
        logger.error("ошибка при получении streaming URL: %s", exc)
        return None
    except ValueError as exc:
        logger.error("ошибка парсинга JSON streaming ответа: %s", exc)
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


def _is_valid_search(soup: BeautifulSoup) -> bool:
    next_data_raw = soup.select_one("#__NEXT_DATA__")
    if not next_data_raw:
        logger.debug("NEXT_DATA не был найден в html")
        return False

    next_data = json.loads(next_data_raw.get_text(strip=True))
    try:
        popular_in_search = next_data["props"]["initialReduxState"]["search"]["popularInSearch"]
    except KeyError as ex:
        logger.error(f"{ex}: {next_data}")
        return False

    if popular_in_search:
        logger.info("API вернул лишь популярные запросы — результаты невалидны")
        return False

    return True


def _parse_search_page(soup: BeautifulSoup) -> dict[str, tuple[str, str]] | None:
    ul = soup.find("ul", attrs={"class": "xm4ofx-1 itNyE"})
    if ul is None or not isinstance(ul, Tag):
        logger.info("Не найдена таблица с результатами поиска")
        return None

    tracks_info: dict[str, tuple[str, str]] = {}
    for li in ul.find_all("li"):
        track_id = get_id(li)
        if track_id is None:
            continue

        name = get_name(li)
        artist = get_artist(li)

        tracks_info[track_id] = (name, artist)

    return tracks_info


def _get_max_page(soup: BeautifulSoup) -> int:
    nav_pages = soup.select_one("div.styles_pagination__1dKAp")
    if not nav_pages:
        return 1

    links = nav_pages.find_all("a")
    page_numbers: list[int] = []
    for link in links:
        text = link.get_text(strip=True)
        if text.isdigit():
            page_numbers.append(int(text))

    return max(page_numbers) if page_numbers else 1


async def _create_sound_generator(session: ClientSession, all_tracks: dict[str, tuple[str, str]]) -> AsyncGenerator[Sound, None]:
    async for tid, download_hash, streaming_hash in get_tracks_download_hashes(
        session, list(all_tracks.keys())
    ):
        track_info = all_tracks.get(str(tid))
        if track_info is None:
            continue

        name, artist = track_info

        url: str | None = None
        if download_hash:
            url = await get_download_url(session, download_hash)
        elif streaming_hash:
            url = await get_streaming_url(session, streaming_hash)

        if not url:
            logger.warning(
                "не удалось получить URL для '%s' — %s", artist, name
            )
            continue

        yield Sound(name, url, artist)


async def _create_beautiful_soup_obj(session: ClientSession, url: str) -> BeautifulSoup:
    async with session.get(url) as resp:
        resp.raise_for_status()
        html_text = await resp.text()

    return BeautifulSoup(html_text, "html.parser")


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на zaycev.net через HTML-парсинг и API.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    logger.info("поиск по запросу '%s'", query)
    session = ClientSession()

    try:
        page_url = SEARCH_URL.format(query=query)

        try:
            soup = await _create_beautiful_soup_obj(session, page_url)
        except ClientResponseError as ex:
            logger.error('Ошибка запроса', exc_info=True)
            return

        if not _is_valid_search(soup):
            return

        all_tracks = _parse_search_page(soup)
        if all_tracks is None:
            logger.info("парсинг не дал результатов, прекращаем поиск")
            return

        logger.info(
            "%d треков было найдено", len(all_tracks)
        )

        async for sound in _create_sound_generator(session, all_tracks):
            yield sound
    except ClientError as exc:
        logger.error("ошибка HTTP-запроса поиска: %s", exc)
        return
    finally:
        await session.close()


async def search_full(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков (полный, все страницы) на zaycev.net через HTML-парсинг и API.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    logger.info("поиск по запросу '%s'", query)
    session = ClientSession()

    try:
        all_tracks: dict[str, tuple[str, str]] = {}
        page = 1
        max_page = 1
        retry_attempts = MAX_RETRY_ATTEMPTS

        while page <= max_page:
            page_url = SEARCH_URL.format(query=query)
            if page > 1:
                page_url += f"&tracks-page={page}"

            try:
                soup = await _create_beautiful_soup_obj(session, page_url)
            except ClientResponseError as ex:
                logger.error('Ошибка запроса.. Повторяем запрос', exc_info=True)
                if retry_attempts <= 0:
                    logger.error('Максимальное кол-во попыток изчерпано... Выходим', exc_info=True)
                    return
                
                retry_attempts -= 1
                continue

            retry_attempts = MAX_RETRY_ATTEMPTS

            if page == 1:
                if not _is_valid_search(soup):
                    return
                max_page = _get_max_page(soup)
                logger.info("страниц для парсинга: %d", max_page)

            page_tracks = _parse_search_page(soup)
            if page_tracks is None:
                logger.info("парсинг страницы %d не дал результатов, прекращаем поиск", page)
                break

            all_tracks.update(page_tracks)
            logger.info(
                "страница %d: +%d треков (всего %d)",
                page, len(page_tracks), len(all_tracks),
            )
            page += 1

        if not all_tracks:
            logger.info("не найдено треков ни на одной странице")
            return

        logger.info("всего найдено треков: %d", len(all_tracks))

        async for sound in _create_sound_generator(session, all_tracks):
            yield sound
    except ClientError as exc:
        logger.error("ошибка HTTP-запроса поиска: %s", exc)
        return
    finally:
        await session.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        async for sound in search_full("Sweet Dreams"):
            print(sound.title, sound.url)

    asyncio.run(main())
