import logging
from pathlib import Path
from typing import Dict, Optional, Callable

from core.models import (
    ExtractionResult, TranslationResult, PackSettings,
    WorkflowContext
)
from core.extractor import Extractor
from core.translator import Translator
from core.builder import Builder
from core.dictionary_manager import DictionaryManager

class Workflow:
    """工作流协调器"""
    
    def __init__(self):
        self.extractor = Extractor()
        self.translator = Translator()
        self.builder = Builder()
        self.dictionary_manager = DictionaryManager()
    
    def _load_dictionaries(self, community_dict_dir, progress_callback=None) -> tuple[Dict, Dict, Dict]:
        """加载各种词典"""
        return self.dictionary_manager.get_all_dictionaries(community_dict_dir, progress_callback)
    
    def run_extraction(
        self, 
        context: WorkflowContext
    ) -> Optional[ExtractionResult]:
        """
        执行数据提取阶段
        """
        logging.info("数据提取开始")
        
        try:
            # 验证配置
            if not context.settings.get('mods_dir'):
                raise ValueError("未配置Mods目录，请先在设置中配置")
            
            mods_path = Path(context.settings['mods_dir'])
            logging.debug(f"正在验证Mods目录: {mods_path}")
            if not mods_path.exists():
                raise ValueError(f"配置的Mods目录不存在: {mods_path}")
            if not mods_path.is_dir():
                raise ValueError(f"配置的Mods路径不是目录: {mods_path}")
            
            # 执行提取
            logging.debug(f"开始从Mods目录提取语言数据: {mods_path}")
            # 从配置中获取汉化包路径，优先使用community_pack_paths，兼容旧版本的zip_paths
            pack_paths = context.settings.get('community_pack_paths', [])
            if not pack_paths:
                pack_paths = context.settings.get('zip_paths', [])
            
            extraction_result = self.extractor.run(
                mods_dir=mods_path,
                zip_paths=[Path(p) for p in pack_paths if Path(p).exists()],
                community_dict_dir=context.settings['community_dict_dir'],
                progress_update_callback=context.progress_callback,
                stop_event=getattr(context, 'stop_event', None)
            )
            
            context.extraction_result = extraction_result
            logging.info("数据提取完成")
            return extraction_result
            
        except ValueError as ve:
            logging.error(f"数据提取阶段配置错误: {ve}")
            raise
        except Exception as e:
            logging.error(f"数据提取阶段执行错误: {e}", exc_info=True)
            raise
    
    def run_translation(
        self, 
        context: WorkflowContext
    ) -> Optional[TranslationResult]:
        """
        执行翻译决策阶段
        """
        logging.info("翻译决策开始")
        
        try:
            # 验证提取结果是否存在
            if not context.extraction_result:
                raise ValueError("提取结果不存在，请先执行数据提取阶段")
            logging.debug(f"提取结果验证通过，包含 {len(context.extraction_result.master_english)} 个命名空间")
            
            # 加载词典
            logging.debug("开始加载翻译词典...")
            user_dict, community_dict_by_key, community_dict_by_origin = self._load_dictionaries(
                context.settings['community_dict_dir'],
                lambda msg, progress: context.progress_callback(50 + progress // 2, 100) if context.progress_callback else None
            )
            logging.debug(f"词典加载完成: 用户词典条目数={len(user_dict.get('by_key', {}))+len(user_dict.get('by_origin_name', {}))}, 社区词典Key条目数={len(community_dict_by_key)}, 社区词典原文条目数={len(community_dict_by_origin)}")
            
            # 执行翻译决策
            logging.debug(f"开始执行翻译决策，处理 {len(context.extraction_result.master_english)} 个命名空间")
            translation_result = self.translator.run(
                extraction_result=context.extraction_result,
                user_dictionary=user_dict,
                community_dict_by_key=community_dict_by_key,
                community_dict_by_origin=community_dict_by_origin,
                use_origin_name_lookup=context.settings.get('use_origin_name_lookup', True),
                dictionary_manager=self.dictionary_manager
            )
            
            context.translation_result = translation_result
            logging.info("翻译决策完成")
            return translation_result
            
        except ValueError as ve:
            logging.error(f"翻译决策阶段配置错误: {ve}")
            raise
        except Exception as e:
            logging.error(f"翻译决策阶段执行错误: {e}", exc_info=True)
            raise
    
    def run_build(
        self, 
        context: WorkflowContext
    ) -> tuple[bool, str]:
        """
        执行资源包构建阶段
        """
        logging.info("资源包构建开始")
        
        try:
            # 验证必要结果是否存在
            if not context.extraction_result:
                raise ValueError("提取结果不存在，请先执行数据提取阶段")
            logging.debug(f"提取结果验证通过，包含 {len(context.extraction_result.master_english)} 个命名空间")
            
            if not context.translation_result:
                raise ValueError("翻译结果不存在，请先执行翻译决策阶段")
            logging.debug(f"翻译结果验证通过，包含 {context.translation_result.total_entries} 个翻译条目")
            
            if not context.pack_settings:
                raise ValueError("资源包设置不存在，请先配置")
            logging.debug(f"资源包设置验证通过: 压缩模式={context.pack_settings.pack_as_zip}, 格式版本={context.pack_settings.pack_format}")
            
            # 执行构建
            logging.info("开始执行资源包构建...")
            success, message = self.builder.run(
                output_dir=Path(context.settings['output_dir']),
                translation_result=context.translation_result,
                extraction_result=context.extraction_result,
                pack_settings=context.pack_settings
            )
            
            logging.info("资源包构建完成")
            return success, message
            
        except ValueError as ve:
            logging.error(f"资源包构建阶段配置错误: {ve}")
            return False, f"构建配置错误: {ve}"
        except Exception as e:
            logging.error(f"资源包构建阶段执行错误: {e}", exc_info=True)
            return False, f"构建执行错误: {e}"
    
    def run_full_workflow(
        self, 
        context: WorkflowContext
    ) -> tuple[bool, str]:
        """
        执行完整工作流
        """
        logging.info("完整工作流开始")
        
        try:
            # 执行数据提取
            self.run_extraction(context)
            
            # 执行翻译决策
            self.run_translation(context)
            
            # 执行资源包构建
            return self.run_build(context)
            
        except Exception as e:
            logging.error(f"完整工作流失败: {e}", exc_info=True)
            return False, f"工作流失败: {e}"
        finally:
            logging.info("完整工作流结束")
    
    def create_context(
        self, 
        settings: Dict,
        pack_settings: Optional[PackSettings] = None,
        progress_callback: Optional[Callable] = None
    ) -> WorkflowContext:
        """
        创建工作流上下文
        """
        return WorkflowContext(
            settings=settings,
            pack_settings=pack_settings,
            progress_callback=progress_callback
        )
