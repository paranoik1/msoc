import logging
from typing import AsyncGenerator

from ..sound import Sound

logger = logging.getLogger("msoc.trekson")

URL = "https://trekson.net/"


# FIXME: не работает, сайт обновили
async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Выполняет поиск треков на trekson.net.

    .. warning:: Движок временно отключён — сайт trekson.net был обновлён,
        старая структура HTML больше не актуальна.

    Args:
        query: Поисковый запрос.

    Yields:
        Sound — информация о найденном треке (пока ничего не возвращает).
    """
    logger.warning(
        "trekson: движок отключён — сайт обновлён, требуется обновление парсера"
    )
    return
    yield  # noqa: unreachable  # marker to make function an async generator
