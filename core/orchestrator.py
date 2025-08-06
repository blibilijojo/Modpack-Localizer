# core/orchestrator.py

import logging # 只需要导入 logging
from pathlib import Path
from core.data_aggregator import DataAggregator
from core.decision_engine import DecisionEngine
from core.pack_builder import PackBuilder
from services.gemini_translator import GeminiTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools

class Orchestrator:
    def __init__(self, settings: dict, progress_callback):
        self.settings = settings
        self.progress_callback = progress_callback

    def run_workflow(self):
        try:
            # --- 阶段 1: 聚合数据 ---
            p_agg_base, p_agg_range = 0, 20
            self.progress_callback(f"阶段 1/4: 准备聚合文件...", p_agg_base)
            aggregator = DataAggregator(Path(self.settings['mods_dir']), [Path(p) for p in self.settings.get('zip_paths', [])])
            master_english_dicts, internal_chinese, pack_chinese, namespace_formats = aggregator.run(lambda current, total: self.progress_callback(f"阶段 1/4: 正在扫描Mod... ({current}/{total})", p_agg_base + (current / total) * p_agg_range))
            if not master_english_dicts:
                logging.error("未能从Mods文件夹提取任何有效原文。")
                raise ValueError("未能从Mods文件夹提取任何有效原文。请确保Mods文件夹内有.jar模组文件。")

            # --- 阶段 2: 决策引擎 ---
            p_dec_base, p_dec_range = 20, 5
            self.progress_callback("阶段 2/4: 应用翻译优先级...", p_dec_base)
            engine = DecisionEngine()
            final_translations_lookup, items_for_ai = engine.run(master_english_dicts, internal_chinese, pack_chinese)
            self.progress_callback("阶段 2/4: 决策完成", p_dec_base + p_dec_range)
            
            # --- 阶段 3: AI 翻译 (已优化) ---
            p_ai_base, p_ai_range = 25, 70
            use_ai = items_for_ai and self.settings.get('api_keys')
            
            if use_ai:
                translator = GeminiTranslator(self.settings['api_keys'], self.settings.get('api_endpoint'))
                texts_to_translate = [val for _, _, val in items_for_ai]
                batch_size = self.settings.get('ai_batch_size', 50)
                max_threads = self.settings.get('ai_max_threads', 4)
                
                text_batches = [texts_to_translate[i:i + batch_size] for i in range(0, len(texts_to_translate), batch_size)]
                total_batches = len(text_batches)
                translations_nested = [None] * total_batches
                
                if total_batches > 0:
                    with ThreadPoolExecutor(max_workers=max_threads) as executor:
                        future_to_batch_index = {}
                        for i, batch in enumerate(text_batches):
                            batch_args = (
                                i, batch, self.settings['model'], self.settings['prompt'],
                                self.settings.get('ai_max_retries', 3), 
                                self.settings.get('ai_retry_interval', 2),
                                self.settings.get('use_grounding', False)
                            )
                            future = executor.submit(translator.translate_batch, batch_args)
                            future_to_batch_index[future] = i

                        completed_batches = 0
                        for future in as_completed(future_to_batch_index):
                            batch_index = future_to_batch_index[future]
                            try:
                                result_batch = future.result()
                                translations_nested[batch_index] = result_batch
                            except Exception as exc:
                                logging.error(f"批次 {batch_index + 1} 翻译时发生严重错误: {exc}", exc_info=True)
                                translations_nested[batch_index] = text_batches[batch_index]
                            
                            completed_batches += 1
                            progress_percentage = p_ai_base + (completed_batches / total_batches) * p_ai_range
                            status_message = f"阶段 3/4: 已完成翻译批次 {completed_batches}/{total_batches}"
                            self.progress_callback(status_message, progress_percentage)

                translations = list(itertools.chain.from_iterable(translations_nested))
                if translations and len(translations) == len(items_for_ai):
                    for i, (namespace, key, _) in enumerate(items_for_ai):
                        final_translations_lookup[namespace][key] = translations[i]
                    logging.info("AI翻译结果已成功回填。")
                else:
                    logging.error("AI翻译返回结果异常，部分文本可能未被翻译。")
            else:
                final_progress = p_ai_base + p_ai_range
                self.progress_callback(f"阶段 3/4: 跳过AI翻译", final_progress)
                logging.info("未提供API密钥或没有待翻译内容，跳过AI翻译阶段。")

            # --- 阶段 4: 构建资源包 ---
            p_build_base, p_build_range = 95, 5
            self.progress_callback("阶段 4/4: 准备生成资源包...", p_build_base)
            builder = PackBuilder()
            success, msg = builder.run(
                Path(self.settings['output_dir']), 
                final_translations_lookup, 
                self.settings['pack_settings'],
                namespace_formats,
                lambda current, total: self.progress_callback(f"阶段 4/4: 正在写入文件... ({current}/{total})", p_build_base + (current / total) * p_build_range)
            )
            
            if success:
                self.progress_callback("流程执行完毕！", 100)
            else:
                raise RuntimeError(f"构建资源包失败: {msg}")

        except Exception as e:
            # 使用 CRITICAL 记录致命错误，并附带 exc_info=True
            # 这会自动将完整的错误堆栈信息记录到日志文件中
            logging.critical(f"工作流执行出错: {e}", exc_info=True)
            self.progress_callback(f"错误: {e}", -1)