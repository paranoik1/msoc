from dataclasses import dataclass, field


@dataclass
class Sound:
    """
    Класс, содержащий информацию о песне.

    Атрибуты:
        title (str): Название песни.
        url (str | None): Ссылка на скачивание песни. Может быть None, если ссылка недоступна.
        artist (str | None): Исполнитель песни. Может быть None, если информация об исполнителе недоступна.
    """

    title: str
    url: str | None = field(default=None)
    artist: str | None = field(default=None)
