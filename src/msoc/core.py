import asyncio
import logging
import warnings
from enum import Enum
from inspect import isasyncgenfunction
from types import ModuleType
from typing import AsyncGenerator, Callable

from aiohttp import ClientError, ClientSession, ClientTimeout

from .exceptions import LoadedEngineNotFoundError
from .sound import Sound

__all__ = [
    "Mode",
    "search",
    "get_engines",
    "register_engine",
    "unload_search_engine",
    "Sound",
    "clear_engines",
]


class Mode(Enum):
    Fast = "fast"
    Full = "full"

_ENGINES: dict[str, ModuleType] = {}

logger = logging.getLogger("msoc")

def get_engines() -> dict[str, ModuleType]:
    """
    Возвращает копию словаря зарегистрированных поисковых движков.

    Returns:
        Словарь ``{имя_движка: модуль}``.
    """
    return _ENGINES.copy()


def clear_engines() -> None:
    """Полностью очищает реестр поисковых движков."""
    _ENGINES.clear()
    logger.info("Реестр движков очищен")


def register_engine(name: str, module: ModuleType) -> None:
    """
    Регистрирует поисковой движок в реестре msoc.

    Args:
        name: Уникальное имя движка (например ``"my_engine"``).
        module: Python-модуль, содержащий асинхронную функцию-генератор ``search(query)``.

    Raises:
        AttributeError: Если в модуле нет функции ``search`` или она не является
            асинхронным генератором.
    """
    search_callback = getattr(module, "search", None)
    if not isasyncgenfunction(search_callback):
        raise AttributeError(
            f'Модуль "{name}" не содержит функцию search() '
            f"или функция не возвращает асинхронный генератор (AsyncGenerator)"
        )

    _ENGINES[name] = module
    logger.info("Зарегистрирован движок: %s", name)


def unload_search_engine(name: str) -> None:
    """
    Удаляет поисковой движок из реестра.

    Args:
        name: Имя движка для удаления.

    Raises:
        LoadedEngineNotFoundError: Если движок с таким именем не найден.
    """
    try:
        del _ENGINES[name]
    except KeyError:
        logger.warning("Попытка удалить несуществующий движок: %s", name)
        raise LoadedEngineNotFoundError(name)

    logger.info("Удалён движок: %s", name)


_AVAILABILITY_CACHE: dict[str, bool] = {}

async def _check_engine_available(engine_name: str) -> bool:
    if engine_name in _AVAILABILITY_CACHE:
        return _AVAILABILITY_CACHE[engine_name]
    
    module = _ENGINES.get(engine_name)
    if module is None:
        return False

    url: str | None = getattr(module, "URL", None)
    if not url:
        return True

    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=ClientTimeout(total=5)) as response:
                avaiable = response.ok
    except (ClientError, asyncio.TimeoutError):
        logger.warning(
            "Движок '%s' недоступен (%s), пропускаем", engine_name, url
        )
        avaiable = False

    _AVAILABILITY_CACHE[engine_name] = avaiable
    return avaiable


async def search(query: str, mode: Mode = Mode.Fast) -> AsyncGenerator[Sound, None]:
    """
    Запускает параллельный поиск музыки по всем зарегистрированным движкам.

    Каждый движок выполняется как отдельная asyncio-задача.
    Результаты возвращаются по мере поступления через асинхронный генератор.

    Args:
        query: Поисковый запрос (название трека, исполнитель или и то и другое).
        mode: Режим поиска — ``Fast`` (только первые страницы) или ``Full``
            (все страницы через ``search_full``, если он реализован).

    Yields:
        Sound — унифицированная информация о найденном треке.
        Поле ``_engine`` автоматически заполняется именем движка-источника.

    Note:
        Если ни один движок не зарегистрирован, генератор немедленно завершится.
        Ошибки отдельных движков логируются на уровне CRITICAL и не прерывают
        поиск остальными движками.
    """
    engines = get_engines()
    queue: asyncio.Queue[Sound | None] = asyncio.Queue()
    lock = asyncio.Lock()

    if not engines:
        logger.warning("search() вызван без зарегистрированных движков")
        return

    logger.info(
        "Начало поиска по %d движкам, режим: %s, запрос: '%s'",
        len(engines), mode.value, query,
    )

    finished_count = 0
    tasks: list[asyncio.Task[None]] = []

    async def _engine_search(
        engine_name: str, callback: Callable[[str], AsyncGenerator[Sound, None]]
    ) -> None:
        nonlocal finished_count

        try:
            if not await _check_engine_available(engine_name):
                async with lock:
                    finished_count += 1
                    if finished_count == len(tasks):
                        await queue.put(None)
                return

            async for sound in callback(query):
                sound._engine = engine_name
                await queue.put(sound)
        except Exception:
            logger.critical(
                "Произошла ошибка во время работы поискового движка '%s'",
                engine_name,
                exc_info=True,
            )
        finally:
            async with lock:
                finished_count += 1
                logger.debug("'%s' закончил поиск песен", engine_name)

                if finished_count == len(tasks):
                    logger.debug("Все поисковые движки окончили поиск песен")
                    await queue.put(None)

    for engine_name, engine_module in engines.items():
        try:
            callback = getattr(engine_module, "search")
        except AttributeError:
            logger.critical(
                "'%s' движок не содержит функцию search(), пропускаем...", engine_name
            )
            continue

        if mode is Mode.Full:
            search_full = getattr(engine_module, "search_full", None)
            if search_full is not None:
                callback = search_full
            else:
                logger.warning(
                    "'%s' не реализует search_full, используем search", engine_name
                )

        task = asyncio.create_task(_engine_search(engine_name, callback))
        tasks.append(task)

    logger.debug("Запущено %d задач поиска", len(tasks))

    try:
        while True:
            item = await queue.get()
            if item is None:
                break

            yield item
    finally:
        for task in tasks:
            task.cancel()

        logger.debug("Задачи поиска отменены или успешно завершены")
