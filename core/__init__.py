# Core module exports
# 使用__getattr__实现延迟导入，避免 PyInstaller 打包时的模块导入问题
__all__ = [
    'Builder',
    'DataAggregator',
    'DecisionEngine',
    'DictionaryManager',
    'Extractor',
    'Orchestrator',
    'PackBuilder',
    'FTBQuestConverter',
    'BQMQuestConverter',
    'ConversionManager',
    'TermDatabase',
    'Translator',
    'Workflow',
    'ExtractionResult',
    'TranslationResult',
    'PackSettings',
    'WorkflowContext',
    'LanguageEntry',
    'NamespaceInfo',
    'DictionaryEntry'
]

def __getattr__(name):
    """延迟导入，避免循环导入和 PyInstaller 打包问题"""
    if name == 'Builder':
        from .builder import Builder
        return Builder
    elif name == 'DataAggregator':
        from .data_aggregator import DataAggregator
        return DataAggregator
    elif name == 'DecisionEngine':
        from .decision_engine import DecisionEngine
        return DecisionEngine
    elif name == 'DictionaryManager':
        from .dictionary_manager import DictionaryManager
        return DictionaryManager
    elif name == 'Extractor':
        from .extractor import Extractor
        return Extractor
    elif name == 'ExtractionResult':
        from .models import ExtractionResult
        return ExtractionResult
    elif name == 'TranslationResult':
        from .models import TranslationResult
        return TranslationResult
    elif name == 'PackSettings':
        from .models import PackSettings
        return PackSettings
    elif name == 'WorkflowContext':
        from .models import WorkflowContext
        return WorkflowContext
    elif name == 'LanguageEntry':
        from .models import LanguageEntry
        return LanguageEntry
    elif name == 'NamespaceInfo':
        from .models import NamespaceInfo
        return NamespaceInfo
    elif name == 'DictionaryEntry':
        from .models import DictionaryEntry
        return DictionaryEntry
    elif name == 'Orchestrator':
        from .orchestrator import Orchestrator
        return Orchestrator
    elif name == 'PackBuilder':
        from .pack_builder import PackBuilder
        return PackBuilder
    elif name == 'FTBQuestConverter':
        from .quest_converter import FTBQuestConverter
        return FTBQuestConverter
    elif name == 'BQMQuestConverter':
        from .quest_converter import BQMQuestConverter
        return BQMQuestConverter
    elif name == 'ConversionManager':
        from .quest_converter import ConversionManager
        return ConversionManager
    elif name == 'TermDatabase':
        from .term_database import TermDatabase
        return TermDatabase
    elif name == 'Translator':
        from .translator import Translator
        return Translator
    elif name == 'Workflow':
        from .workflow import Workflow
        return Workflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")