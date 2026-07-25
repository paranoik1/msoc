import logging
import re

logger = logging.getLogger("msoc")

http_pattern = re.compile(r'^https?://')


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

    if http_pattern.search(sound_url):
        return sound_url
    
    if not http_pattern.search(base_url):
        raise ValueError('Базовый url должен быть абсолютным')
    
    url_fragments = base_url.split('/') 
    host_url = "/".join(url_fragments[:3])

    if not sound_url.startswith('/'):
        sound_url = '/' + sound_url

    absolute_url = host_url + sound_url
    
    logger.debug("Преобразован URL '%s' -> '%s'", sound_url, absolute_url)
    return absolute_url
