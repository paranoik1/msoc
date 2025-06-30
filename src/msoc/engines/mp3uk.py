from urllib.parse import quote

from aiohttp import ClientSession
from bs4 import BeautifulSoup

from ..sound import Sound

URL = "https://mp3feel.net/search"

COOKIES = {
    "PHPSESSID": "76025b2b8e5dd2fa493da7fdf4d51ad8",
    "rbtify_visit_id": "c7c1fd55-9c1d-4b2d-b68b-a846368d0fae",
    "rbtify_session_id": "2c5b636c-09fb-c315-8d83-4f2d65185980",
    "ad_activate_step_left_for_track": "2",
    "ad_activate_step_left_for_radio": "1",
    "domain_sid": "e2VNUeFpmLE4_jWgLjTyW%3A1730539497760",
    "_ym_uid": "1730539498584027299",
    "_ym_d": "1730539498",
    "_ym_isad": "2",
    "adrdel": "1730539499931",
    "adrcid": "AHNBf7hhYBnD_FiQEcDaTBg",
    "acs_3": "%7B%22hash%22%3A%225c916bd2c1ace501cfd5%22%2C%22nextSyncTime%22%3A1730625900254%2C%22syncLog%22%3A%7B%22224%22%3A1730539500254%2C%221228%22%3A1730539500254%2C%221230%22%3A1730539500254%7D%7D",
    "ad_last_polling_providers": "1730539504673",
    "ad_last_blur": "1730539604555",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    # 'Accept-Encoding': 'gzip, deflate, br, zstd',
    "Referer": "https://mp3feel.net/",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://mp3feel.net",
    "Connection": "keep-alive",
    # 'Cookie': 'PHPSESSID=76025b2b8e5dd2fa493da7fdf4d51ad8; rbtify_visit_id=c7c1fd55-9c1d-4b2d-b68b-a846368d0fae; rbtify_session_id=2c5b636c-09fb-c315-8d83-4f2d65185980; ad_activate_step_left_for_track=2; ad_activate_step_left_for_radio=1; domain_sid=e2VNUeFpmLE4_jWgLjTyW%3A1730539497760; _ym_uid=1730539498584027299; _ym_d=1730539498; _ym_isad=2; adrdel=1730539499931; adrcid=AHNBf7hhYBnD_FiQEcDaTBg; acs_3=%7B%22hash%22%3A%225c916bd2c1ace501cfd5%22%2C%22nextSyncTime%22%3A1730625900254%2C%22syncLog%22%3A%7B%22224%22%3A1730539500254%2C%221228%22%3A1730539500254%2C%221230%22%3A1730539500254%7D%7D; ad_last_polling_providers=1730539504673; ad_last_blur=1730539604555',
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
}


# Получение имени песни
def get_song_name(track_info):
    song_name = track_info.get("data-title")
    return song_name.strip() if song_name else None


# Получение исполнителя песни
def get_song_artist(track_info):
    song_artist = track_info.get("data-artist")
    return song_artist.strip() if song_artist else None


# Получение прямой ссылки на скачивание трека
def get_download_song_url(track_info):
    link = track_info.get("data-track")
    return link.strip() if link else None


async def search(query: str):
    encoded_query = quote(query)
    search_url = f"{URL}?q={encoded_query}"

    async with ClientSession(headers=HEADERS) as session:
        response = await session.get(search_url)
        content = await response.text()

    soup = BeautifulSoup(content, "lxml")
    all_songs = soup.select(".track-item")

    for track_info in all_songs:
        song_name = get_song_name(track_info)
        song_artist = get_song_artist(track_info)
        download_song_url = get_download_song_url(track_info)

        yield Sound(title=song_name, artist=song_artist, url=download_song_url)


if __name__ == "__main__":

    async def main():
        query = input("Песня: ")

        async for sound in search(query):
            print(sound)

    from asyncio import run

    run(main())
