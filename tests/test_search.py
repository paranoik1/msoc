import pytest
import logging
from src.msoc import search, get_engines


logging.getLogger().setLevel(logging.DEBUG)


@pytest.mark.asyncio
async def test_search():
    print(get_engines())
    async for sound in search('Лама'):
        print(sound.url)
