# Core module exports
from .builder import Builder
from .dictionary_manager import DictionaryManager
from .exceptions import (
    ModpackLocalizerError, ConfigurationError, ExtractionError,
    TranslationError, BuildError, AIError, FileError, ServiceResult,
)
from .extractor import Extractor
from .models import (
    ExtractionResult, TranslationResult, PackSettings,
    WorkflowContext, LanguageEntry, NamespaceInfo,
    DictionaryEntry, TranslationSource, ZipFileResult,
    resolve_origin_name_conflict
)
from .quest_converter import ConversionManager, BaseQuestConverter, FTBQuestConverter, BQMQuestConverter, LANGConverter
from .term_database import TermDatabase
from .translator import Translator
from .workflow import Workflow

from .mod_fingerprint import (
    curseforge_fingerprint_from_jar_bytes,
    jar_mod_fingerprints_and_meta,
    is_version_string,
    match_github_version,
)
from .mod_repository import ModrinthClient, CurseForgeClient

__all__ = [
    'Builder',
    'DictionaryManager',
    'Extractor',
    'ConversionManager',
    'BaseQuestConverter',
    'FTBQuestConverter',
    'BQMQuestConverter',
    'LANGConverter',
    'TermDatabase',
    'Translator',
    'Workflow',
    'ExtractionResult',
    'TranslationResult',
    'PackSettings',
    'WorkflowContext',
    'LanguageEntry',
    'NamespaceInfo',
    'DictionaryEntry',
    'TranslationSource',
    'ZipFileResult',
    'resolve_origin_name_conflict',
    'ModrinthClient',
    'CurseForgeClient',
    'ServiceResult',
]