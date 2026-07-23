import pytest

from src.msoc import Sound, register_engine, search # type: ignore


async def mock_search(query: str):
    yield Sound(title="Test Track", url="https://example.com/1", artist="Mock Artist")
    yield Sound(title="Another Track", url="https://example.com/2", artist="Mock Band")


@pytest.fixture
def register_mock_engine():
    register_engine("mock", type("MockModule", (), {"search": mock_search}))


@pytest.mark.asyncio
async def test_search_yields_sounds(register_mock_engine):
    results = []
    async for sound in search("test"):
        results.append(sound)

    assert len(results) == 2
    assert results[0].title == "Test Track"
    assert results[1].artist == "Mock Band"


@pytest.mark.asyncio
async def test_search_empty_when_no_engines():
    results = []
    async for sound in search("anything"):
        results.append(sound)
    assert results == []
