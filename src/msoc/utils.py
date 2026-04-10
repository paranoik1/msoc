import logging

from yarl import URL

logger = logging.getLogger("msoc")


def validate_and_return_absolute_url(sound_url: str, base_url: str) -> str:
    """
    Преобразует относительный URL в абсолютный на основе base_url.

    Args:
        sound_url: Относительный или абсолютный URL трека.
        base_url: Базовый URL сайта для преобразования относительных ссылок.

    Returns:
        Абсолютный URL в виде строки.

    Raises:
        ValueError: Если base_url не является корректным абсолютным URL.
    """
    if sound_url.startswith("https://"):
        return sound_url

    yarl_url = URL(base_url)
    try:
        host_site = yarl_url.origin()
    except ValueError:
        logger.error("Некорректный base_url: %s", base_url)
        raise ValueError(f"Поисковой запрос должен быть абсолютным: {base_url}")

    absolute_url = host_site.with_path(sound_url)
    logger.debug("Преобразован URL '%s' -> '%s'", sound_url, absolute_url)
    return str(absolute_url)
