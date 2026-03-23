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

# 显式导入所有子模块，确保 PyInstaller 能够识别
import core.extractor
import core.translator
import core.builder
import core.dictionary_manager
import core.term_database
import core.decision_engine
import core.data_aggregator
import core.orchestrator
import core.quest_converter
import core.workflow
import core.models
import core.exceptions

def __getattr__(name):
    """延迟导入，避免循环导入和 PyInstaller 打包问题"""
    if name == 'Builder':
        from core.builder import Builder
        return Builder
    elif name == 'DataAggregator':
        from core.data_aggregator import DataAggregator
        return DataAggregator
    elif name == 'DecisionEngine':
        from core.decision_engine import DecisionEngine
        return DecisionEngine
    elif name == 'DictionaryManager':
        from core.dictionary_manager import DictionaryManager
        return DictionaryManager
    elif name == 'Extractor':
        from core.extractor import Extractor
        return Extractor
    elif name == 'ExtractionResult':
        from core.models import ExtractionResult
        return ExtractionResult
    elif name == 'TranslationResult':
        from core.models import TranslationResult
        return TranslationResult
    elif name == 'PackSettings':
        from core.models import PackSettings
        return PackSettings
    elif name == 'WorkflowContext':
        from core.models import WorkflowContext
        return WorkflowContext
    elif name == 'LanguageEntry':
        from core.models import LanguageEntry
        return LanguageEntry
    elif name == 'NamespaceInfo':
        from core.models import NamespaceInfo
        return NamespaceInfo
    elif name == 'DictionaryEntry':
        from core.models import DictionaryEntry
        return DictionaryEntry
    elif name == 'Orchestrator':
        from core.orchestrator import Orchestrator
        return Orchestrator
    elif name == 'PackBuilder':
        from core.pack_builder import PackBuilder
        return PackBuilder
    elif name == 'FTBQuestConverter':
        from core.quest_converter import FTBQuestConverter
        return FTBQuestConverter
    elif name == 'BQMQuestConverter':
        from core.quest_converter import BQMQuestConverter
        return BQMQuestConverter
    elif name == 'ConversionManager':
        from core.quest_converter import ConversionManager
        return ConversionManager
    elif name == 'TermDatabase':
        from core.term_database import TermDatabase
        return TermDatabase
    elif name == 'Translator':
        from core.translator import Translator
        return Translator
    elif name == 'Workflow':
        from core.workflow import Workflow
        return Workflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")