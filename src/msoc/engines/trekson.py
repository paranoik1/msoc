from .base import search as base_search


URL = "https://trekson.net/"

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
    'Referer': URL,
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': URL,
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Priority': 'u=0, i',
}



async def search(query: str):
    async for sound in base_search(
        url=URL, 
        query=query,
        headers=HEADERS,
        cookies=COOKIES 
    ):
        yield sound
