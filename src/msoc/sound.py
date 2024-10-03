from dataclasses import dataclass, field


@dataclass
class Sound:
    """
    Класс, содержащий  информацию об песне
    """
    title: str
    url: str
