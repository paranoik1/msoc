import aiohttp
from bs4 import BeautifulSoup

from msoc.sound import Sound


URL = "https://mp3uk.net/index.php?do=search"

COOKIES = {
    'rbtify_session_id': '04d49b7a-08d2-a4bc-c30c-6127a51fc5dd',
    '_ym_uid': '1721741605992017505',
    '_ym_d': '1721741605',
    'adrdel': '1724606317001',
    'adrcid': 'Aq7cHMWm9vbcQzzcjWyR94A',
    'acs_3': '%7B%22hash%22%3A%2240a47f53e220d7da5392%22%2C%22nextSyncTime%22%3A1724692716180%2C%22syncLog%22%3A%7B%22224%22%3A1724606316180%2C%221228%22%3A1724606316180%2C%221230%22%3A1724606316180%7D%7D',
    'PHPSESSID': '70ce656ba4dbc6dfa06baed7b63149e2',
    'rbtify_visit_id': '58409e4f-7214-44da-8ca3-fe344b502568',
    '_ym_isad': '2',
    'ad_activate_step_left_for_track': '2',
    'ad_activate_step_left_for_radio': '1',
    'domain_sid': 'd09BWjxDiLZpyN2DijL2E%3A1724606324922',
    'ad_last_polling_providers': '1724606329182',
    'ad_last_blur': '1724606348821',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    'Referer': 'https://mp3uk.net/index.php?do=search',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://mp3uk.net',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Priority': 'u=0, i',
}


def get_name(track):
    track_title = track.find("div", {"class": "track-title"})
    try:
        return track_title.find("span").text
    except:
        return track_title.text
    

def get_url(track):
    unclean_url = track.find("a", {"class": "track-dl"})["href"]
        
    if "/dl.php?" in unclean_url:
        url = "https://mp3uk.net" + unclean_url
    else:
        url = "https:" + unclean_url

    return url



async def search(query):
    data = f"do=search&subaction=search&story={query}"
    async with aiohttp.ClientSession(headers=HEADERS, cookies=COOKIES) as session:
        async with session.post(URL, data=data) as response:
            text = await response.text()

    html = BeautifulSoup(text, "html.parser")

    for track in html.find_all("div", {"class": "track-item"}):
        name = get_name(track)
        url = get_url(track)

        yield Sound(name, url)
