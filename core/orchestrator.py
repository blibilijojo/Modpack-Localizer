# core/orchestrator.py

import logging 
from pathlib import Path
import json
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.data_aggregator import DataAggregator
from core.decision_engine import DecisionEngine
from core.pack_builder import PackBuilder
from services.gemini_translator import GeminiTranslator
from gui.manual_translation_window import ManualTranslationWindow

class Orchestrator:
    def __init__(self, settings: dict, progress_callback, root_for_dialog=None, save_data: dict | None = None):
        self.settings = settings
        self.progress_callback = progress_callback
        self.root_for_dialog = root_for_dialog
        self.save_data = save_data

    def run_workflow(self):
        try:
            # --- 初始化变量 ---
            final_translations_lookup = {}
            items_to_process_manual = []
            items_for_ai = []
            namespace_formats = {}
            is_from_save = bool(self.save_data)
            
            # --- 阶段一: 数据获取 ---
            if is_from_save:
                # 从项目存档加载
                self.progress_callback("阶段 1/2: 从项目文件加载...", 25)
                logging.info(f"从项目存档文件加载数据...")
                
                final_translations_lookup = self.save_data['existing_translations']
                items_to_process_manual = self.save_data['manual_translation_data']
                namespace_formats = self.save_data['namespace_formats']
                
                self.settings['pack_settings'] = self.save_data.get('pack_settings', self.settings['pack_settings'])
                logging.info("项目数据加载完成。")
                translation_mode = 'manual' # 从存档加载总是进入手动模式
                p_translate_base, p_translate_range = 50, 45 # 调整进度条基数和范围
                
            else:
                # 从头扫描文件
                p_agg_base, p_agg_range = 0, 20
                self.progress_callback(f"阶段 1/4: 准备聚合文件...", p_agg_base)
                
                aggregator = DataAggregator(
                    Path(self.settings['mods_dir']), 
                    [Path(p) for p in self.settings.get('zip_paths', [])],
                    self.settings.get('community_dict_path', '')
                )
                community_dict_by_key, community_dict_by_origin, master_english_dicts, internal_chinese, pack_chinese, namespace_formats = aggregator.run(lambda current, total: self.progress_callback(f"阶段 1/4: 正在扫描Mod... ({current}/{total})", p_agg_base + (current / total) * p_agg_range))
                
                if not master_english_dicts:
                    raise ValueError("未能从Mods文件夹提取任何有效原文。请确保Mods文件夹内有.jar模组文件。")

                p_dec_base, p_dec_range = 20, 5
                self.progress_callback("阶段 2/4: 应用翻译优先级...", p_dec_base)
                engine = DecisionEngine()
                
                final_translations_lookup, items_for_ai, key_contribution, origin_name_contribution = engine.run(
                    community_dict_by_key, community_dict_by_origin, 
                    master_english_dicts, internal_chinese, pack_chinese,
                    self.settings.get('use_origin_name_lookup', True)
                )
                
                if key_contribution > 0: logging.info(f"分析完成：社区词典通过 [精准 Key] 匹配贡献了 {key_contribution} 条翻译。")
                if origin_name_contribution > 0: logging.info(f"分析完成：社区词典通过 [原文 Origin Name] 匹配贡献了 {origin_name_contribution} 条翻译。")
                
                self.progress_callback("阶段 2/4: 决策完成", p_dec_base + p_dec_range)
                items_to_process_manual = items_for_ai
                translation_mode = self.settings.get('translation_mode', 'ai')
                p_translate_base, p_translate_range = 25, 70 # 正常流程的进度条基数和范围

            # --- 阶段二: 翻译 (AI 或 手动) ---
            if translation_mode == 'ai':
                use_ai = items_for_ai and self.settings.get('api_keys')
                if use_ai:
                    translator = GeminiTranslator(self.settings['api_keys'], self.settings.get('api_endpoint'))
                    texts_to_translate = [val for _, _, val in items_for_ai]
                    batch_size = self.settings.get('ai_batch_size', 50)
                    max_threads = self.settings.get('ai_max_threads', 4)
                    
                    text_batches = [texts_to_translate[i:i + batch_size] for i in range(0, len(texts_to_translate), batch_size)]
                    total_batches = len(text_batches)
                    translations_nested = [None] * total_batches
                    
                    logging.info(f"AI翻译启动：待翻译 {len(texts_to_translate)} 条，分为 {total_batches} 个批次，使用 {max_threads} 个线程。")

                    if total_batches > 0:
                        with ThreadPoolExecutor(max_workers=max_threads) as executor:
                            future_to_batch_index = {
                                executor.submit(
                                    translator.translate_batch, 
                                    (i, batch, self.settings['model'], self.settings['prompt'], self.settings['ai_max_retries'], self.settings['ai_retry_interval'], self.settings.get('use_grounding', False))
                                ): i
                                for i, batch in enumerate(text_batches)
                            }

                            completed_batches = 0
                            for future in as_completed(future_to_batch_index):
                                batch_index = future_to_batch_index[future]
                                try:
                                    result_batch = future.result()
                                    translations_nested[batch_index] = result_batch
                                except Exception as exc:
                                    logging.critical(f"翻译线程池中的批次 {batch_index + 1} 遭遇不可恢复的致命错误: {exc}", exc_info=True)
                                    raise exc
                                
                                completed_batches += 1
                                progress_percentage = p_translate_base + (completed_batches / total_batches) * p_translate_range
                                status_message = f"阶段 3/4: 已完成AI翻译批次 {completed_batches}/{total_batches}"
                                self.progress_callback(status_message, progress_percentage)

                    translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
                    if not translations or len(translations) != len(items_for_ai):
                        raise ValueError(f"AI翻译返回结果数量不匹配！预期: {len(items_for_ai)}, 得到: {len(translations)}。流程中止。")

                    for i, (namespace, key, _) in enumerate(items_for_ai):
                        final_translations_lookup[namespace][key] = translations[i]
                    logging.info("AI翻译结果已成功回填。")
                else:
                    self.progress_callback("阶段 3/4: 跳过AI翻译", p_translate_base + p_translate_range)
                    logging.info("未提供API密钥或没有待翻译内容，跳过AI翻译阶段。")
            
            elif translation_mode == 'manual':
                if items_to_process_manual:
                    if not self.root_for_dialog: raise ValueError("手动翻译模式需要一个有效的GUI根窗口。")
                    
                    stage_prefix = "阶段 2/2" if is_from_save else "阶段 3/4"
                    self.progress_callback(f"{stage_prefix}: 准备手动翻译工作台...", p_translate_base)
                    
                    manual_window = ManualTranslationWindow(
                        parent=self.root_for_dialog,
                        items_to_process=items_to_process_manual,
                        existing_translations=final_translations_lookup,
                        namespace_formats=namespace_formats,
                        current_settings=self.settings
                    )
                    self.root_for_dialog.wait_window(manual_window)
                    
                    if manual_window.result_translations is not None:
                        final_translations_lookup = manual_window.result_translations
                        self.progress_callback(f"{stage_prefix}: 手动翻译完成", p_translate_base + p_translate_range)
                    else:
                        raise InterruptedError("用户已取消手动翻译流程。")
                else:
                    self.progress_callback("无需手动翻译", p_translate_base + p_translate_range)
            
            # --- 阶段三: 构建资源包 ---
            p_build_base = 95
            self.progress_callback("最后阶段: 准备生成资源包...", p_build_base)
            builder = PackBuilder()
            success, msg = builder.run(
                Path(self.settings['output_dir']), 
                final_translations_lookup, 
                self.settings['pack_settings'],
                namespace_formats
            )
            
            if success: self.progress_callback("流程执行完毕！", 100)
            else: raise RuntimeError(f"构建资源包失败: {msg}")

        except InterruptedError as e:
            logging.warning(f"工作流被用户主动中断: {e}")
            self.progress_callback(f"已取消: {e}", -1)
        except Exception as e:
            logging.critical(f"工作流执行出错: {e}", exc_info=True)
            self.progress_callback(f"错误: {e}", -1)