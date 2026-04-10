import asyncio
import logging
from types import ModuleType
from typing import AsyncGenerator, Callable

from .engines import hitmo, mp3feel, trekson, zaycev_net, muzbomb
from .exceptions import LoadedEngineNotFoundError
from .sound import Sound

__all__ = [
    "search",
    "get_engines",
    "load_search_engine",
    "unload_search_engine",
    "Sound",
]


ENGINES = {"mp3uk": mp3feel, "trekson": trekson, "hitmo": hitmo, "zaycev_net": zaycev_net, "muzbomb": muzbomb}


logger = logging.getLogger("msoc")


def get_engines() -> dict[str, ModuleType]:
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


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Функция начинает поиск песен по запросу query.

    Возвращает: асинхронный генератор Sound
    """
    engines = get_engines()
    queue: asyncio.Queue[Sound | None] = asyncio.Queue()
    lock = asyncio.Lock()

    if not engines:
        return

    finished_count = 0
    tasks: list[asyncio.Task] = []

    async def _engine_search(
        engine_name: str, search_callback: Callable[[str], AsyncGenerator[Sound]]
    ):
        nonlocal finished_count

        try:
            async for sound in search_callback(query):
                sound._engine = engine_name
                await queue.put(sound)
        except Exception:
            logger.critical(
                f'Произошла ошибка во время работы поискового движка "{engine_name}"',
                exc_info=True,
            )
        finally:
            async with lock:
                finished_count += 1
                logger.debug(f'"{engine_name}" закончил поиск песен')

                if finished_count == len(tasks):
                    logger.debug("Все поисковые движки окончили поиск песен")
                    await queue.put(None)

    for engine_name, engine_module in engines.items():
        search_callback = getattr(engine_module, "search", None)
        if not callable(search_callback):
            logger.error(f'В движке "{engine_name}" не была найдена функция search')
            continue

        task = asyncio.create_task(_engine_search(engine_name, search_callback))
        tasks.append(task)

    try:
        while True:
            item = await queue.get()
            if item is None:
                break

            yield item
    finally:
        for task in tasks:
            task.cancel()
