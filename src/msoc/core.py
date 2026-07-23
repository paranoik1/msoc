import asyncio
import logging
import warnings
from inspect import isasyncgenfunction
from types import ModuleType
from typing import AsyncGenerator, Callable

from aiohttp import ClientError, ClientSession, ClientTimeout

from .exceptions import LoadedEngineNotFoundError
from .sound import Sound

__all__ = [
    "search",
    "get_engines",
    "register_engine",
    "load_search_engine",
    "unload_search_engine",
    "Sound",
    "clear_engines",
]

_ENGINES: dict[str, ModuleType] = {}

logger = logging.getLogger("msoc")

_AVAILABILITY_CACHE: dict[str, bool] = {}


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
    _AVAILABILITY_CACHE.clear()
    logger.info("Реестр движков очищен")


def load_search_engine(name: str, module: ModuleType) -> None:
    """
    ⚠️ УСТАРЕЛО: Используйте :func:`register_engine` вместо этой функции.

    Эта функция будет удалена в будущем выпуске.
    """
    warnings.warn(
        "load_search_engine() устарела и будет удалена в будущем. "
        "Используйте register_engine() вместо неё.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "Вызов устаревшей функции load_search_engine(). "
        "Пожалуйста, обновите код на register_engine()."
    )
    register_engine(name, module)


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

    _AVAILABILITY_CACHE.pop(name, None)
    logger.info("Удалён движок: %s", name)


async def _check_engine_available(engine_name: str, engine_module: ModuleType) -> bool:
    url: str | None = getattr(engine_module, "URL", None)
    if not url:
        return True

    if engine_name in _AVAILABILITY_CACHE:
        return _AVAILABILITY_CACHE[engine_name]

    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=ClientTimeout(total=5)) as response:
                available = response.status < 500
    except (ClientError, asyncio.TimeoutError):
        available = False

    _AVAILABILITY_CACHE[engine_name] = available
    if not available:
        logger.warning(
            "Движок '%s' недоступен (%s), пропускаем", engine_name, url
        )
    return available


async def search(query: str) -> AsyncGenerator[Sound, None]:
    """
    Запускает параллельный поиск музыки по всем зарегистрированным движкам.

    Каждый движок выполняется как отдельная asyncio-задача.
    Результаты возвращаются по мере поступления через асинхронный генератор.

    Args:
        query: Поисковый запрос (название трека, исполнитель или и то и другое).

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

    logger.info("Начало поиска по %d движкам, запрос: '%s'", len(engines), query)

    finished_count = 0
    tasks: list[asyncio.Task[None]] = []

    async def _engine_search(
        engine_name: str, search_callback: Callable[[str], AsyncGenerator[Sound, None]]
    ) -> None:
        nonlocal finished_count

        try:
            if not await _check_engine_available(engine_name, engines[engine_name]):
                async with lock:
                    finished_count += 1
                    if finished_count == len(tasks):
                        await queue.put(None)
                return

            async for sound in search_callback(query):
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
            search_callback = getattr(engine_module, "search")
        except AttributeError:
            logger.error(
                "'%s' движок не содержит функцию search(), пропускаем...", engine_name
            )
            continue

        task = asyncio.create_task(_engine_search(engine_name, search_callback))
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
