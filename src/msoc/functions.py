import asyncio
import traceback
from typing import AsyncGenerator


async def consume(a_iter):
    try:
        return await a_iter.__anext__(), asyncio.create_task(consume(a_iter))
    except StopAsyncIteration:
        return None, None
    except Exception:
        print(traceback.format_exc())
        return None, None


def create_generator_task(gen: AsyncGenerator) -> AsyncGenerator:
    result_queue = asyncio.create_task(consume(gen.__aiter__()))

    async def consumer():
        nonlocal result_queue
        while True:
            item, result_queue = await result_queue
            if result_queue is None:
                assert item is None
                return
            yield item

    return consumer()
