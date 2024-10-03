from msoc import engines, load_search_engine, unload_search_engine
import asyncio


async def main():
    print(engines())
    name = input("Наименование поискового движка: ")
    path = input("Путь к Python файлу: ")

    load_search_engine(name, path)
    print(engines())

    unload_search_engine(name)
    print(engines())


asyncio.run(main())