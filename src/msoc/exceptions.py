class LoadedEngineNotFoundError(KeyError):
    def __init__(self, name):
        super().__init__("Движок не был найден в загруженных: " + name)
        