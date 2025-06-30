# За основу был взят код Ushiiro82:
# https://github.com/Ushiiro82/MelodyHub/blob/master/parsing/hitmo_parser.py

from urllib.parse import quote

from aiohttp import ClientSession
from bs4 import BeautifulSoup

from ..sound import Sound

# Headers
HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}

# URL сайта
BASE_URL = "https://rus.hitmotop.com/"


# Получение имени песни
def get_song_name(track_info):
    song_name = track_info.find(class_="track__title")
    return song_name.text.strip() if song_name else None


# Получение исполнителя песни
def get_song_artist(track_info):
    song_artist = track_info.find(class_="track__desc")
    return song_artist.text.strip() if song_artist else None


# Получение прямой ссылки на скачивание трека
def get_download_song_url(track_info):
    tag_a = track_info.find("a", class_="track__download-btn")
    link = tag_a["href"]
    return link.strip() if link else None


async def search(query: str):
    encoded_query = quote(query)  # Кодируем строку запроса
    search_url = f"{BASE_URL}search?q={encoded_query}"

    async with ClientSession(headers=HEADERS) as session:
        response = await session.get(search_url)
        content = await response.text()

    soup = BeautifulSoup(content, "lxml")

    # Получаем информацию о всех песнях
    all_songs = soup.select(".tracks__item")

    for track_info in all_songs:
        song_name = get_song_name(track_info)
        song_artist = get_song_artist(track_info)
        download_song_url = get_download_song_url(track_info)

        yield Sound(title=song_name, artist=song_artist, url=download_song_url)
