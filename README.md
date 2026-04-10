<div align="center">

# 🎵 MSOC - Библиотека для быстрого и асинхронного поиска музыки

[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/msoc?style=for-the-badge)](https://pypi.org/project/msoc/)
[![Downloads](https://img.shields.io/pypi/dm/msoc?style=for-the-badge)](https://pypi.org/project/msoc/)

![MSOC Banner](https://placehold.co/1200x400?text=MSOC+-+Асинхронный+поиск+музыки) <!-- Замените на реальный баннер -->

</div>

## ✨ Особенности
- ⚡ Асинхронный поиск музыки
- 🔍 Поддержка нескольких источников
- 🛠️ Простое расширение новыми движками
- 📦 Легкая интеграция в проекты
- 🚀 Быстрая установка через pip

---

# 🎵 MSOC - Библиотека для быстрого и асинхронного поиска музыки

MSOC - это библиотека на Python для быстрого и асинхронного поиска музыки в Интернете. Она позволяет искать треки на различных музыкальных сайтах и возвращает информацию о найденных треках, включая их названия и ссылки на скачивание.

# 📦 Установка

Для установки библиотеки можно использовать pip:
```bash
pip install msoc
```

Так же можно установить из исходников:
```bash
git clone https://github.com/paranoik1/msoc.git

cd MSOC

pip install .
```

# 🚀 Использование

## 💻 В консоле

Можно протестировать пакет обычным скриптом, который был установлен после установки самой библиотеки:
```shell
msoc <query or empty>
# or
python -m msoc <query or empty>
```

При запуске будет выведена информация о найденных треках: `Name`, `Artist`, `URL`, `Engine` (название движка) и `Meta` (дополнительные метаданные).

## ⌨️ В коде

Импортируйте модуль msoc и используйте функцию search() для поиска музыки:

```python
from msoc import search
import asyncio


async def main():
    query = input("Запрос: ")

    async for sound in search(query):
        print(f"Name: {sound.title}\nArtist: {sound.artist}\nURL: {sound.url}")
        print("================================================")


asyncio.run(main())
```

Функция `search()` принимает поисковый запрос в качестве аргумента и возвращает асинхронный генератор, который генерирует объекты `Sound` с информацией о найденных треках.

## 🎶 Класс Sound

Класс `Sound` содержит информацию о песне.

Атрибуты:

- `title (str)`: Название песни.
- `url (str | None)`: Ссылка на скачивание песни. Может быть None, если ссылка недоступна (Необязательный атрибут).
- `artist (str | None)`: Исполнитель песни. Может быть None, если информация об исполнителе недоступна (Необязательный атрибут).
- `meta (dict[str, Any])`: Дополнительные метаданные трека.
- `_engine (str | None)`: Название движка, нашедшего трек (заполняется автоматически).


## 🔌 Реализованные движки поиска

В настоящее время библиотека MSOC поддерживает следующие движки поиска:

- zaycev_net: Поиск на сайте [zaycev.net](https://zaycev.net)
- hitmo: Поиск на сайте [rus.hitmotop.com](https://rus.hitmotop.com) - реализован на основе [данного кода](https://github.com/Ushiiro82/MelodyHub/blob/master/parsing/hitmo_parser.py)
- muzbomb: Поиск на сайте [muzbomb.net](https://muzbomb.net/) - создан [takilow](https://github.com/takilow)
- trekson: ~~Поиск на сайте [trekson.net](https://trekson.net/)~~ ⚠️ отключён — сайт обновлён, требуется обновление парсера

Движки загружаются автоматически при импорте пакета `msoc`.

## ❌ Exceptions

Библиотека MSOC определяет следующие исключения:

- `LoadedEngineNotFoundError`: Выбрасывается, когда движок поиска не был найден в загруженных движках.

## 🛠️ Создание своих поисковых движков
Для создания собственных поисковых движков на Python вы можете использовать следующий подход:

1. Создайте новый Python-файл для вашего поискового движка:
   - Например, создайте файл `my_search_engine.py`.

2. Определите асинхронную функцию `search(query)`, которая будет реализовывать поисковый алгоритм:
   - Реализуйте логику поиска, взаимодействуя с API или веб-страницами источников, которые вы хотите использовать.
   - Можете использовать библиотеки, такие как `aiohttp`, `beautifulsoup4` и другие, для выполнения HTTP-запросов и парсинга HTML-страниц.

Функция `search` внутри движка должна возвращать генератор объектов `Sound`.  
Пример реализации функции `search(query)` в `my_search_engine.py`:

```python
import aiohttp
from bs4 import BeautifulSoup

from msoc.sound import Sound


async def search(query: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://example.com/search?q={query}") as response:
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")

    for item in soup.find_all("div", class_="search-result"):
        name = item.find("h3").get_text(strip=True)
        artist = item.find("span", class_="artist").get_text(strip=True)
        url = item.find("a").get("href")
        yield Sound(name, url, artist)
```

3. Подключите ваш поисковый движок к системе:

```python
from msoc import register_engine, get_engines

import my_search_engine


register_engine("my_search_engine", my_search_engine)
print(get_engines())
```
   - Замените `my_search_engine` на название вашего python файла.
   - Далее вызываем `get_engines()`, чтобы удостовериться, что движок был успешно загружен

4. Теперь при запуске основной `search` функции, ваш движок будет автоматически загружен и использован для поиска песен

### ℹ️ P.S 1
Если вам нужно подключить поисковой движок, файл которого находится не в текущей папке проекта, можете воспользоваться встроенным python пакетом `importlib`

```python
from msoc import register_engine
from importlib import util

spec = util.spec_from_file_location("my_search_engine", "/path/to/python/file/my_search_engine.py")
module = util.module_from_spec(spec)

spec.loader.exec_module(module)


register_engine("my_search_engine", module)
```

### ℹ️ P.S 2
Если вам не нужен какой либо поисковой движок, используй `unload_search_engine` для его удаления из загруженных:

```python
from msoc import unload_search_engine, engines

unload_search_engine("my_search_engine")
print(engines())
```

## 🤝 Contribution

Если вы хотите внести свой вклад в развитие библиотеки MSOC, вы можете:

- 🐞 Сообщить об ошибках или предложить новые функции
- 🎛️ Разработать и добавить новые движки поиска
- 📖 Улучшить документацию
- 🔧 Исправить существующие проблемы


<div align="center">
  
[![Open Issues](https://img.shields.io/github/issues/paranoik1/msoc?style=for-the-badge)](https://github.com/paranoik1/msoc/issues)
[![Stars](https://img.shields.io/github/stars/paranoik1/msoc?style=for-the-badge)](https://github.com/paranoik1/msoc/stargazers)

</div>
