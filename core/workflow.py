import logging
from pathlib import Path
from typing import Dict, Optional, Callable

from .models import (
    ExtractionResult, TranslationResult, PackSettings,
    WorkflowContext
)
from .extractor import Extractor
from .translator import Translator
from .builder import Builder
from .dictionary_manager import DictionaryManager

class Workflow:
    """工作流协调器"""
    
    def __init__(self):
        self.extractor = Extractor()
        self.translator = Translator()
        self.builder = Builder()
        self.dictionary_manager = DictionaryManager()
    
    def _load_dictionaries(self, community_dict_path: str) -> tuple[Dict, Dict, Dict]:
        """加载各种词典"""
        return self.dictionary_manager.get_all_dictionaries(community_dict_path)
    
    def run_extraction(
        self, 
        context: WorkflowContext
    ) -> Optional[ExtractionResult]:
        """
        执行数据提取阶段
        """
        logging.info("=== 开始数据提取阶段 ===")
        
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
            logging.info(f"开始从Mods目录提取语言数据: {mods_path}")
            # 从配置中获取汉化包路径，优先使用community_pack_paths，兼容旧版本的zip_paths
            pack_paths = context.settings.get('community_pack_paths', [])
            if not pack_paths:
                pack_paths = context.settings.get('zip_paths', [])
            
            extraction_result = self.extractor.run(
                mods_dir=mods_path,
                zip_paths=[Path(p) for p in pack_paths if Path(p).exists()],
                community_dict_path=context.settings['community_dict_path'],
                progress_update_callback=context.progress_callback
            )
            
            # 提取模组名称
            logging.info("开始提取模组名称...")
            module_names = self.extractor.extract_module_names(mods_path)
            if module_names:
                logging.info(f"成功提取到 {len(module_names)} 个模组名称")
                for module in module_names[:5]:  # 只显示前5个作为示例
                    logging.info(f"- {module['name']} (来源: {module['source']})")
                if len(module_names) > 5:
                    logging.info(f"... 等 {len(module_names) - 5} 个模组")
            
            # 将提取到的模组名称设置到提取结果中
            extraction_result.module_names = module_names
            
            # 提取curseforge名称
            logging.info("开始提取curseforge名称...")
            curseforge_names = self.extractor.extract_curseforge_names(mods_path)
            if curseforge_names:
                logging.info(f"成功提取到 {len(curseforge_names)} 个curseforge名称")
                for module in curseforge_names[:5]:  # 只显示前5个作为示例
                    logging.info(f"- {module['curseforge_name']} (来源: {module['source']})")
                if len(curseforge_names) > 5:
                    logging.info(f"... 等 {len(curseforge_names) - 5} 个curseforge名称")
            
            # 将提取到的curseforge名称设置到提取结果中
            extraction_result.curseforge_names = curseforge_names
            
            # 提取Modrinth名称：只对没有Curseforge名称的模组进行搜索
            logging.info("开始提取Modrinth名称...")
            
            # 找出所有的JAR文件
            all_jar_files = list(mods_path.glob('*.jar'))
            
            # 找出已经有Curseforge名称的JAR文件
            curseforge_jar_files = []
            for module in curseforge_names:
                source = module.get('source', '')
                # 从source中提取JAR文件名
                # source格式如："AmbientEnvironment-fabric-1.21.1-18.0.0.2.jar\fabric.mod.json"
                if '.jar' in source:
                    # 尝试从source路径中提取JAR文件的完整路径
                    import re
                    parts = re.split(r'[\\/]', source, 1)
                    if len(parts) > 0:
                        jar_name = parts[0]
                        # 查找对应的JAR文件
                        for jar_file in all_jar_files:
                            if jar_file.name == jar_name:
                                curseforge_jar_files.append(jar_file)
                                break
            
            # 提取Modrinth名称，排除那些已经有Curseforge名称的JAR文件
            modrinth_names = self.extractor.extract_modrinth_names(mods_path, excluded_jar_files=curseforge_jar_files)
            if modrinth_names:
                logging.info(f"成功提取到 {len(modrinth_names)} 个Modrinth名称")
                for module in modrinth_names[:5]:  # 只显示前5个作为示例
                    logging.info(f"- {module['modrinth_name']} (来源: {module['source']})")
                if len(modrinth_names) > 5:
                    logging.info(f"... 等 {len(modrinth_names) - 5} 个Modrinth名称")
            
            # 将提取到的Modrinth名称设置到提取结果中
            extraction_result.modrinth_names = modrinth_names
            
            context.extraction_result = extraction_result
            logging.info("=== 数据提取阶段完成 ===")
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
        logging.info("=== 开始翻译决策阶段 ===")
        
        try:
            # 验证提取结果是否存在
            if not context.extraction_result:
                raise ValueError("提取结果不存在，请先执行数据提取阶段")
            logging.debug(f"提取结果验证通过，包含 {len(context.extraction_result.master_english)} 个命名空间")
            
            # 加载词典
            logging.info("开始加载翻译词典...")
            user_dict, community_dict_by_key, community_dict_by_origin = self._load_dictionaries(
                context.settings['community_dict_path']
            )
            logging.debug(f"词典加载完成: 用户词典条目数={len(user_dict.get('by_key', {}))+len(user_dict.get('by_origin_name', {}))}, 社区词典Key条目数={len(community_dict_by_key)}, 社区词典原文条目数={len(community_dict_by_origin)}")
            
            # 执行翻译决策
            logging.info(f"开始执行翻译决策，处理 {len(context.extraction_result.master_english)} 个命名空间")
            translation_result = self.translator.run(
                extraction_result=context.extraction_result,
                user_dictionary=user_dict,
                community_dict_by_key=community_dict_by_key,
                community_dict_by_origin=community_dict_by_origin,
                use_origin_name_lookup=context.settings.get('use_origin_name_lookup', True)
            )
            
            context.translation_result = translation_result
            logging.info("=== 翻译决策阶段完成 ===")
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
        logging.info("=== 开始资源包构建阶段 ===")
        
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
            
            logging.info("=== 资源包构建阶段完成 ===")
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
        logging.info("========== 开始完整工作流 ==========")
        
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
            logging.info("========== 完整工作流结束 ==========")
    
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
