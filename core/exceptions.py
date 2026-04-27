from __future__ import annotations

class ModpackLocalizerError(Exception):
    def __init__(self, message: str, error_code: str | None = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

class ConfigurationError(ModpackLocalizerError):
    pass

class ExtractionError(ModpackLocalizerError):
    pass

class TranslationError(ModpackLocalizerError):
    pass

class BuildError(ModpackLocalizerError):
    pass

class AIError(ModpackLocalizerError):
    pass

class FileError(ModpackLocalizerError):
    pass
