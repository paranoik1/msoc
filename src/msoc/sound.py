from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sound:
    """
    Класс, содержащий информацию о песне.

    Атрибуты:
        title (str): Название песни.
        url (str | None): Ссылка на скачивание песни. Может быть None, если ссылка недоступна.
        artist (str | None): Исполнитель песни. Может быть None, если информация об исполнителе недоступна.

        meta (dict[str, Any]): Другая информация об песне (по умолчанию - пустой словарь)

        _engine (str | None): Заполняется автоматически скриптом. Содержит название поискового движка, который нашел данную песню
    """

    title: str
    url: str | None = None
    artist: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    _engine: str | None = None
