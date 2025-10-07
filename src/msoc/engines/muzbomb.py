# Автор поискового движка - takilow: https://github.com/takilow
import aiohttp
from bs4 import BeautifulSoup

from msoc.sound import Sound

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0',
}


async def search(query: str):
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"https://muzbomb.net/?song={query}") as response:
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")

    # ищем все треки в блоке с результатами
    tracks = soup.find_all("div", class_="tmtMus_blc")

    for track in tracks:
        try:
            # извлекаем название трека
            track_link = track.find("a", class_="tmtMus_blc_tracklink")
            name = track_link.text.strip() if track_link else "Неизвестный трек"

            # извлекаем исполнителя
            artist_link = track.find("a", class_="tmtMus_blc_artist")
            artist = artist_link.text.strip() if artist_link else "Неизвестный исполнитель"

            # извлекаем URL для скачивания
            download_link = track.find("a", class_="tmtMus_blc_download")
            url = download_link.get("href") if download_link else None

            if url:
                # Преобразуем относительный URL в абсолютный
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = "https://muzbomb.net" + url

                # print(f"Найден трек: {artist} - {name}")
                yield Sound(name, url, artist)

        except Exception as e:
            print(f"Ошибка при обработке трека: {e}")
            continue
