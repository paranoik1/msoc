import logging
from importlib import import_module
from pathlib import Path

from .msoc import *

logger = logging.getLogger("msoc.auto_discover_engines")


def _auto_discover_engines() -> None:
    """
    Автоматически регистрирует все .py-модули в папке engines,
    которые содержат функцию search().

    Вызывается один раз при импорте пакета.
    """
    engines_dir = Path(__file__).parent / "engines"

    for file in engines_dir.glob("*.py"):
        # Пропускаем служебные файлы
        if file.stem.startswith("_"):
            continue

        module_name = f"{__name__}.engines.{file.stem}"

        try:
            # Импорт выполнит код модуля, включая его саморегистрацию если она есть
            module = import_module(module_name)
            engines = get_engines()

            # Если модуль не зарегистрировал себя сам - регистрируем автоматически
            if file.stem not in engines:
                register_engine(file.stem, module)
                logger.debug(f"Авто-зарегистрирован движок: {file.stem}")
        except ImportError as e:
            logger.error(f"Не удалось импортировать модуль движка {module_name}: {e}")
        except Exception as e:
            logger.exception(f"Ошибка при инициализации движка {module_name}: {e}")


# Инициализация при импорте пакета
_auto_discover_engines()
