from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class LanguageEntry:
    """语言条目数据模型"""
    key: str
    en: str
    zh: Optional[str] = None
    source: Optional[str] = None
    namespace: str = "minecraft"

@dataclass
class NamespaceInfo:
    """命名空间信息"""
    name: str
    jar_name: str = "Unknown"
    file_format: str = "json"
    raw_content: str = ""

@dataclass
class DictionaryEntry:
    """词典条目"""
    key: Optional[str] = None
    original: Optional[str] = None
    translation: Optional[str] = None
    version: str = "0.0.0"
    source: str = ""

@dataclass
class ExtractionResult:
    """提取结果数据模型"""
    master_english: Dict[str, Dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    internal_chinese: Dict[str, Dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    pack_chinese: Dict[str, str] = field(default_factory=dict)
    namespace_info: Dict[str, NamespaceInfo] = field(default_factory=dict)
    raw_english_files: Dict[str, str] = field(default_factory=dict)
    module_names: List[Dict[str, str]] = field(default_factory=list)
    curseforge_names: List[Dict[str, str]] = field(default_factory=list)
    modrinth_names: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class TranslationResult:
    """翻译结果数据模型"""
    workbench_data: Dict[str, Dict[str, LanguageEntry]] = field(default_factory=lambda: defaultdict(dict))
    source_counts: Dict[str, int] = field(default_factory=dict)
    total_entries: int = 0

@dataclass
class PackSettings:
    """资源包设置"""
    pack_as_zip: bool = False
    pack_description: str = "A Modpack Localization Pack"
    pack_base_name: str = "Generated_Pack"
    pack_format: int = 7
    pack_icon_path: str = ""

@dataclass
class WorkflowContext:
    """工作流上下文"""
    settings: Dict
    extraction_result: Optional[ExtractionResult] = None
    translation_result: Optional[TranslationResult] = None
    pack_settings: Optional[PackSettings] = None
    progress_callback: Optional[callable] = None
