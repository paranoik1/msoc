import asyncio
from sys import argv

from .core import search


async def main(query: str) -> None:
    async for sound in search(query):
        print(
            f"Name: {sound.title}\n"
            f"Artist: {sound.artist}\n"
            f"URL: {sound.url}\n"
            f"Engine: {sound._engine}\n"
            f"Meta: {sound.meta}"
        )
        print("================================================")


def execute() -> None:
    query = argv[1] if len(argv) >= 2 else input("Запрос: ")
    asyncio.run(main(query))


if __name__ == "__main__":
    execute()
