from .msoc import search
from sys import argv
import asyncio


async def main(query):
    async for sound in search(query):
        print(f"Name: {sound.title}\nArtist: {sound.artist}\nURL: {sound.url}")
        print("================================================")


def execute():
    query = argv[1] if len(argv) >= 2 else input("Запрос: ")
    asyncio.run(main(query))


if __name__ == '__main__':
    execute()

