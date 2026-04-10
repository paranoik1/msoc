# Автор поискового движка - takilow: https://github.com/takilow

import logging
from typing import AsyncGenerator

import aiohttp
from aiohttp import ClientError
from bs4 import BeautifulSoup, Tag

from ..sound import Sound

logger = logging.getLogger("msoc.muzbomb")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


def _normalize_url(url: str) -> str:
    """Преобразует относительный URL muzbomb.net в абсолютный."""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://muzbomb.net" + url
    return url


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на muzbomb.net.

    Args:
        query: Поисковый запрос (название трека или исполнитель).

    Yields:
        Sound — информация о найденном треке.
    """
    search_url = f"https://muzbomb.net/?song={query}"
    logger.info("muzbomb: поиск по запросу '%s'", query)

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(search_url) as response:
                if response.status != 200:
                    logger.warning(
                        "muzbomb: HTTP %d при запросе %s", response.status, search_url
                    )
                    return
                html = await response.text()
    except ClientError as exc:
        logger.error("muzbomb: ошибка HTTP-запроса: %s", exc)
        return

    soup = BeautifulSoup(html, "html.parser")
    tracks = soup.find_all("div", class_="tmtMus_blc")
    logger.info("muzbomb: найдено элементов-кандидатов: %d", len(tracks))

    for track in tracks:
        try:
            track_link = track.find("a", class_="tmtMus_blc_tracklink")
            name = track_link.text.strip() if track_link else "Неизвестный трек"

            artist_link = track.find("a", class_="tmtMus_blc_artist")
            artist = (
                artist_link.text.strip() if artist_link else "Неизвестный исполнитель"
            )

            download_link: Tag | None = track.find("a", class_="tmtMus_blc_download")
            url: str | None = None
            if download_link is not None:
                raw_url = download_link.get("href")
                if raw_url and isinstance(raw_url, str):
                    url = _normalize_url(raw_url)
                    logger.debug("muzbomb: URL нормализован '%s' -> '%s'", raw_url, url)

            if not name:
                logger.debug("muzbomb: пропуск элемента без названия")
                continue

            logger.debug("muzbomb: найден трек '%s' — %s", artist, name)
            yield Sound(name, url, artist)

        except Exception:
            logger.exception("muzbomb: ошибка при обработке элемента результата")
            continue
