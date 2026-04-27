from __future__ import annotations
import re
import threading
from typing import Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from packaging.version import parse as parse_version

JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)


class TranslationSource:
    ORIGINAL_COPY = "原文复制"
    MOD_BUILTIN = "模组自带"
    PENDING = "待翻译"
    USER_DICT_KEY = "个人词典 [Key]"
    USER_DICT_ORIGIN = "个人词典 [原文]"
    COMMUNITY_PACK = "第三方汉化包"
    COMMUNITY_DICT_KEY = "社区词典 [Key]"
    COMMUNITY_DICT_ORIGIN = "社区词典 [原文]"
    AI_TRANSLATION = "AI翻译"


def resolve_origin_name_conflict(candidates: list[dict]) -> str | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["trans"]

    trans_counts = Counter(c["trans"] for c in candidates)
    max_freq = max(trans_counts.values())
    top_candidates = [c for c in candidates if trans_counts[c["trans"]] == max_freq]

    if len(top_candidates) == 1:
        return top_candidates[0]["trans"]

    def get_version_key(candidate):
        try:
            return parse_version(candidate["version"])
        except Exception:
            return parse_version("0.0.0")

    try:
        sorted_by_version = sorted(top_candidates, key=get_version_key, reverse=True)
        return sorted_by_version[0]["trans"]
    except Exception:
        return top_candidates[0]["trans"]

@dataclass
class LanguageEntry:
    key: str
    en: str
    zh: str | None = None
    source: str | None = None
    namespace: str = "minecraft"

@dataclass
class NamespaceInfo:
    name: str
    jar_name: str = "Unknown"
    file_format: str = "json"
    raw_content: str = ""

@dataclass
class DictionaryEntry:
    key: str | None = None
    original: str | None = None
    translation: str | None = None
    version: str = "0.0.0"
    source: str = ""

@dataclass
class ExtractionResult:
    master_english: dict[str, dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    internal_chinese: dict[str, dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    pack_chinese: dict[str, str] = field(default_factory=dict)
    namespace_info: dict[str, NamespaceInfo] = field(default_factory=dict)
    raw_english_files: dict[str, str] = field(default_factory=dict)
    module_names: list[dict[str, str]] = field(default_factory=list)
    curseforge_names: list[dict[str, str]] = field(default_factory=list)
    modrinth_names: list[dict[str, str]] = field(default_factory=list)

@dataclass
class TranslationResult:
    workbench_data: dict[str, dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    source_counts: dict[str, int] = field(default_factory=dict)
    total_entries: int = 0

@dataclass
class PackSettings:
    pack_as_zip: bool = False
    pack_description: str = "A Modpack Localization Pack"
    pack_base_name: str = "Generated_Pack"
    pack_format: int = 7
    pack_icon_path: str = ""

@dataclass
class WorkflowContext:
    settings: dict
    extraction_result: ExtractionResult | None = None
    translation_result: TranslationResult | None = None
    pack_settings: PackSettings | None = None
    progress_callback: Callable[..., Any] | None = None
    extraction_progress: Callable[[str, int, int], None] | None = None
    stop_event: threading.Event | None = None

@dataclass
class ZipFileResult:
    namespace: str | None = None
    file_format: str = "json"
    content: str = ""
    extracted_data: dict[str, str] = field(default_factory=dict)
    is_english: bool = False
    is_chinese: bool = False

    @property
    def is_valid(self) -> bool:
        return self.namespace is not None

    @staticmethod
    def empty() -> ZipFileResult:
        return ZipFileResult()

@dataclass
class TranslationContext:
    user_dict_by_key: dict[str, str] = field(default_factory=dict)
    user_dict_by_origin: dict[str, str] = field(default_factory=dict)
    community_dict_by_key: dict[str, str] = field(default_factory=dict)
    community_dict_by_origin: dict[str, list[dict]] = field(default_factory=dict)
    internal_chinese: dict[str, LanguageEntry] = field(default_factory=dict)
    pack_chinese_dict: dict[str, str] = field(default_factory=dict)
    use_community_dict_key: bool = True
    use_community_dict_origin: bool = True
    dictionary_manager: Any = None
