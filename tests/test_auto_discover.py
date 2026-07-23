import logging
from pathlib import Path

from src.msoc import _auto_discover_engines, get_engines # type: ignore

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def test_all_loaded_engines():
    engines = get_engines()
    logger.info(engines.keys())
    assert len(engines) != 0
