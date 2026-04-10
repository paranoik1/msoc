class LoadedEngineNotFoundError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__("Движок не был найден в загруженных: " + name)
