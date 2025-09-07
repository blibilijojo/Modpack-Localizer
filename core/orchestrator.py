import logging 
from pathlib import Path
import json
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.data_aggregator import DataAggregator
from core.decision_engine import DecisionEngine
from core.pack_builder import PackBuilder
from services.gemini_translator import GeminiTranslator

class Orchestrator:
    def __init__(self, settings: dict, progress_callback, root_for_dialog=None, save_data: dict | None = None, log_callback=None):
        self.settings = settings
        self.progress_callback = progress_callback
        self.root_for_dialog = root_for_dialog
        self.save_data = save_data
        self.log_callback = log_callback

    def run_workflow(self):
        try:
            workbench_data = {}
            namespace_formats = {}
            final_translations_lookup = {}
            is_from_save = bool(self.save_data)
            
            if is_from_save:
                self.progress_callback("阶段 1/2: 从项目文件加载...", 50)
                logging.info(f"从项目存档文件加载数据...")
                
                workbench_data = self.save_data['workbench_data']
                namespace_formats = self.save_data['namespace_formats']
                
                self.settings['pack_settings'] = self.save_data.get('pack_settings', self.settings['pack_settings'])
                logging.info("项目数据加载完成。")
                p_translate_base = 50
                
            else:
                p_agg_base, p_agg_range = 0, 25
                self.progress_callback(f"阶段 1/3: 准备聚合文件...", p_agg_base)
                
                aggregator = DataAggregator(
                    Path(self.settings['mods_dir']), 
                    [Path(p) for p in self.settings.get('zip_paths', [])],
                    self.settings.get('community_dict_path', '')
                )
                # FIX: Unpack all 8 return values from aggregator.run
                user_dictionary, community_dict_by_key, community_dict_by_origin, master_english_dicts, internal_chinese, pack_chinese, namespace_formats, namespace_to_jar = aggregator.run(lambda current, total: self.progress_callback(f"阶段 1/3: 正在扫描Mod... ({current}/{total})", p_agg_base + (current / total) * p_agg_range))
                
                if not master_english_dicts:
                    raise ValueError("未能从Mods文件夹提取任何有效原文。请确保Mods文件夹内有.jar模组文件。")

                p_dec_base, p_dec_range = 25, 25
                self.progress_callback("阶段 2/3: 应用翻译优先级...", p_dec_base)
                engine = DecisionEngine()
                
                # FIX: Pass the new namespace_to_jar dictionary to the engine
                workbench_data = engine.run(
                    user_dictionary, community_dict_by_key, community_dict_by_origin, 
                    master_english_dicts, internal_chinese, pack_chinese,
                    self.settings.get('use_origin_name_lookup', True),
                    namespace_to_jar
                )
                
                self.progress_callback("阶段 2/3: 决策完成", p_dec_base + p_dec_range)
                p_translate_base = 50

            if not workbench_data:
                self.progress_callback("未发现任何可处理的文本条目。", 95)
            else:
                if not self.root_for_dialog: raise ValueError("翻译工作台模式需要一个有效的GUI根窗口。")
                
                from gui.translation_workbench import TranslationWorkbench

                stage_prefix = "阶段 2/2" if is_from_save else "阶段 3/3"
                self.progress_callback(f"{stage_prefix}: 准备翻译工作台...", p_translate_base)
                
                workbench = TranslationWorkbench(
                    parent=self.root_for_dialog,
                    initial_data=workbench_data,
                    namespace_formats=namespace_formats,
                    current_settings=self.settings,
                    log_callback=self.log_callback
                )
                self.root_for_dialog.wait_window(workbench)
                
                if workbench.final_translations is not None:
                    final_translations_lookup = workbench.final_translations
                else:
                    raise InterruptedError("用户已取消翻译流程。")
            
            p_build_base = 95
            self.progress_callback("最后阶段: 准备生成资源包...", p_build_base)
            builder = PackBuilder()
            success, msg = builder.run(
                Path(self.settings['output_dir']), 
                final_translations_lookup, 
                self.settings['pack_settings'],
                namespace_formats
            )
            
            if success: 
                self.progress_callback("流程执行完毕！", 100)
            else: 
                raise RuntimeError(f"构建资源包失败: {msg}")

        except InterruptedError as e:
            logging.warning(f"工作流被用户主动中断: {e}")
            self.progress_callback(f"已取消: {e}", -1)
        except Exception as e:
            logging.critical(f"工作流执行出错: {e}", exc_info=True)
            self.progress_callback(f"错误: {e}", -1)