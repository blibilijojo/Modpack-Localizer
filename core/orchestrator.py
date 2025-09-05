import logging 
from pathlib import Path
import queue

from core.data_aggregator import DataAggregator
from core.decision_engine import DecisionEngine

class Orchestrator:
    def __init__(self, settings: dict, ui_queue: queue.Queue):
        self.settings = settings
        self.ui_queue = ui_queue

    def prepare_data(self):
        try:
            p_agg_base, p_agg_range = 0, 50
            self.ui_queue.put({'type': 'progress', 'data': {'message': f"阶段 1/2: 准备聚合文件...", 'percentage': p_agg_base}})
            
            aggregator = DataAggregator(
                Path(self.settings['mods_dir']), 
                [Path(p) for p in self.settings.get('zip_paths', [])],
                self.settings.get('community_dict_path', '')
            )
            
            def agg_progress_sender(current, total):
                msg = f"阶段 1/2: 正在扫描Mod... ({current}/{total})"
                percent = p_agg_base + (current / total) * p_agg_range
                self.ui_queue.put({'type': 'progress', 'data': {'message': msg, 'percentage': percent}})
                
            user_dictionary, community_dict_by_key, community_dict_by_origin, master_english_dicts, internal_chinese, pack_chinese, namespace_formats, namespace_to_jar = aggregator.run(agg_progress_sender)
            
            if not master_english_dicts:
                raise ValueError("未能从Mods文件夹提取任何有效原文。请确保Mods文件夹内有.jar模组文件。")

            p_dec_base, p_dec_range = 50, 50
            self.ui_queue.put({'type': 'progress', 'data': {'message': "阶段 2/2: 应用翻译优先级...", 'percentage': p_dec_base}})
            engine = DecisionEngine()
            
            workbench_data = engine.run(
                user_dictionary, community_dict_by_key, community_dict_by_origin, 
                master_english_dicts, internal_chinese, pack_chinese,
                self.settings.get('use_origin_name_lookup', True),
                namespace_to_jar
            )
            
            self.ui_queue.put({'type': 'progress', 'data': {'message': "数据准备完成，即将打开工作台...", 'percentage': 100}})
            
            # Send all prepared data to the main thread
            self.ui_queue.put({
                'type': 'data_ready',
                'data': {
                    'workbench_data': workbench_data,
                    'namespace_formats': namespace_formats,
                }
            })

        except Exception as e:
            logging.critical(f"数据准备工作流执行出错: {e}", exc_info=True)
            self.ui_queue.put({'type': 'error', 'data': {'error': str(e)}})