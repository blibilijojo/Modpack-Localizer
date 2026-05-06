from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


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


@dataclass
class ServiceResult(Generic[T]):
    success: bool
    data: T | None = None
    message: str = ""
    extra: Any = field(default=None, repr=False)

    @property
    def error(self) -> str:
        return "" if self.success else self.message

    @staticmethod
    def ok(data: T | None = None, message: str = "") -> ServiceResult[T]:
        return ServiceResult(success=True, data=data, message=message)

    @staticmethod
    def fail(message: str, data: T | None = None) -> ServiceResult[T]:
        return ServiceResult(success=False, data=data, message=message)

    def __iter__(self):
        if self.extra is not None:
            yield self.success
            yield self.data
            yield self.message
        else:
            yield self.success
            yield self.message
