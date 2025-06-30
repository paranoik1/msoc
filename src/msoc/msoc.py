from types import ModuleType
from typing import AsyncGenerator

from .engines import hitmo, mp3uk, trekson, zaycev_net
from .exceptions import LoadedEngineNotFoundError
from .functions import create_generator_task
from .sound import Sound

__all__ = ["search", "engines", "load_search_engine", "unload_search_engine", "Sound"]


ENGINES = {"mp3uk": mp3uk, "trekson": trekson, "hitmo": hitmo, "zaycev_net": zaycev_net}


def engines() -> dict[str, ModuleType]:
    """
    Функция возвращает словарь загруженных поисковых движков.
    """
    return ENGINES.copy()


def load_search_engine(name: str, engine: ModuleType) -> None:
    """
    Функция загружает поисковой движок по путю к python файлу.
    """

    ENGINES[name] = engine


def unload_search_engine(name: str) -> None:
    """
    Функция удаляет поисковой движок из загруженных по name

    Exceptions: LoadedEngineNotFoundError
    """
    try:
        del ENGINES[name]
    except KeyError:
        raise LoadedEngineNotFoundError(name)


async def search(query: str) -> AsyncGenerator[None, Sound]:
    """
    Функция начинает поиск песен по запросу query.

    Возвращает: асинхронный генератор Sound
    """

    tasks = [create_generator_task(engine.search(query)) for engine in ENGINES.values()]

    for task in tasks:
        async for sound in task:
            yield sound
