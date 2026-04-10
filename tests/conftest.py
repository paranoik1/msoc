import logging

import pytest

from src.msoc import clear_engines

logging.getLogger("msoc").setLevel(logging.DEBUG)


@pytest.fixture(autouse=True)
def clean_engines():
    """Очищает реестр движков после каждого теста."""
    yield
    clear_engines()
