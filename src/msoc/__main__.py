import argparse
import asyncio

from .core import Mode, search


async def main(query: str, mode: Mode) -> None:
    async for sound in search(query, mode=mode):
        print(
            f"Name: {sound.title}\n"
            f"Artist: {sound.artist}\n"
            f"URL: {sound.url}\n"
            f"Engine: {sound._engine}\n"
            f"Meta: {sound.meta}"
        )
        print("================================================")


def execute() -> None:
    parser = argparse.ArgumentParser(
        prog="msoc",
        description="Быстрый асинхронный поиск музыки",
    )
    parser.add_argument("query", nargs="?", help="Поисковый запрос")
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Запустить графический интерфейс (TUI)",
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "full"],
        default="fast",
        help="Режим поиска: fast (только первые страницы) или full (все страницы)",
    )
    args = parser.parse_args()

    if args.tui:
        from .textual_app import MsocApp

        app = MsocApp()
        app.run()
        return

    mode = Mode(args.mode)
    query = args.query if args.query else input("Запрос: ")
    asyncio.run(main(query, mode))


if __name__ == "__main__":
    execute()
