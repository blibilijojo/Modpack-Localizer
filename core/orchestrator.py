import logging
from pathlib import Path
from tkinter import messagebox
from datetime import datetime
from core.data_aggregator import DataAggregator
from core.decision_engine import DecisionEngine
from core.pack_builder import PackBuilder
from gui.translation_workbench import TranslationWorkbench
DEFAULT_NAME_TEMPLATE = "汉化资源包_{timestamp}"
DEFAULT_DESC_TEMPLATE = (
    "整合包汉化数据分析 (共 {total} 条):\n"
    "▷ AI 翻译贡献: {ai_count} 条 ({ai_percent})\n"
    "▷ 人工及社区贡献: {human_count} 条 ({human_percent})"
)
class Orchestrator:
    def __init__(self, settings, update_progress, root_window, log_callback=None, save_data=None, project_path=None):
        self.settings = settings
        self.update_progress = update_progress
        self.root = root_window
        self.log = log_callback or (lambda msg, lvl: logging.info(f"[{lvl}] {msg}"))
        self.save_data = save_data
        self.project_path = project_path
        self.final_translations = None
        self.final_workbench_data = None
        self.raw_english_files = {}
        self.namespace_formats = {}
    def run_translation_phase(self):
        try:
            self.log("阶段 1/3: 开始聚合语言数据...", "INFO")
            self.update_progress("正在聚合数据...", 10)
            
            # 验证配置
            if not self.settings.get('mods_dir'):
                raise ValueError("未配置Mods目录，请先在设置中配置")
            
            mods_path = Path(self.settings['mods_dir'])
            if not mods_path.exists() or not mods_path.is_dir():
                raise ValueError(f"配置的Mods目录不存在或不是目录: {mods_path}")
            
            aggregator = DataAggregator(
                mods_dir=mods_path,
                zip_paths=[Path(p) for p in self.settings.get('zip_paths', []) if Path(p).exists()],
                community_dict_path=self.settings['community_dict_path']
            )
            
            try:
                (user_dict, comm_dict_key, comm_dict_origin, 
                 en_dicts, internal_zh, pack_zh, 
                 ns_formats, ns_to_jar, raw_en_files) = aggregator.run(
                    lambda cur, total: self.update_progress(f"扫描Mods... ({cur}/{total})", 10 + (cur/total) * 40)
                )
            except Exception as agg_error:
                logging.error(f"数据聚合失败: {agg_error}", exc_info=True)
                raise Exception(f"数据聚合失败: {agg_error}")
            
            self.update_progress("数据聚合完成", 50)
            self.raw_english_files = raw_en_files
            self.namespace_formats = ns_formats
            
            self.log("阶段 2/3: 执行翻译决策...", "INFO")
            self.update_progress("正在应用翻译规则...", 60)
            
            engine = DecisionEngine()
            try:
                workbench_data = engine.run(
                    user_dictionary=user_dict,
                    community_dict_by_key=comm_dict_key,
                    community_dict_by_origin=comm_dict_origin,
                    master_english_dicts=en_dicts,
                    internal_chinese_dicts=internal_zh,
                    pack_chinese_dict=pack_zh,
                    use_origin_name_lookup=self.settings.get('use_origin_name_lookup', True),
                    namespace_to_jar=ns_to_jar,
                    raw_english_files=raw_en_files,
                    namespace_formats=ns_formats
                )
            except Exception as dec_error:
                logging.error(f"翻译决策失败: {dec_error}", exc_info=True)
                raise Exception(f"翻译决策失败: {dec_error}")
            
            # 验证决策结果
            if not workbench_data:
                raise Exception("翻译决策未生成任何数据")
            
            self.update_progress("决策完成，准备打开工作台", 90)
            self.log("阶段 3/3: 启动翻译工作台...", "INFO")
            self.root.after(0, self._launch_workbench, workbench_data)
        except ValueError as ve:
            logging.error(f"配置错误: {ve}")
            self.root.after(0, lambda: messagebox.showerror("配置错误", f"请检查配置后重试:\n{ve}"))
            self.update_progress(f"错误: {ve}", -1)
        except Exception as e:
            logging.error(f"翻译处理阶段失败: {e}", exc_info=True)
            self.root.after(0, lambda: messagebox.showerror("处理失败", f"在处理文件时发生错误:\n{e}\n请查看日志获取更多详细信息。"))
            self.update_progress(f"错误: {e}", -1)
    def _launch_workbench(self, workbench_data):
        workbench = TranslationWorkbench(
            parent=self.root,
            initial_data=workbench_data,
            namespace_formats=self.namespace_formats,
            raw_english_files=self.raw_english_files,
            current_settings=self.settings,
            log_callback=self.log,
            project_path=self.project_path,
            finish_button_text="完成并生成资源包"
        )
        self.root.wait_window(workbench)
        if workbench.final_translations is not None:
            self.final_translations = workbench.final_translations
            self.final_workbench_data = workbench.translation_data
            self.log("翻译工作台已关闭，数据已准备好生成资源包。", "SUCCESS")
            self.update_progress("翻译处理完成，现在可以生成资源包", -10)
        else:
            self.log("翻译工作台已取消，操作中止。", "WARNING")
            self.update_progress("操作已取消", -2)
    def _generate_pack_metadata_values(self) -> dict:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not self.final_workbench_data:
            return {"timestamp": timestamp, "total": 0, "ai_count": 0, "ai_percent": "0.0%", "human_count": 0, "human_percent": "0.0%"}
        ai_count = 0
        human_count = 0
        total_translated = 0
        ai_sources = {"AI翻译"}
        for ns_data in self.final_workbench_data.values():
            for item in ns_data.get('items', []):
                if item.get('zh', '').strip():
                    total_translated += 1
                    source = item.get('source', '')
                    if source in ai_sources:
                        ai_count += 1
                    else:
                        human_count += 1
        ai_percent = (ai_count / total_translated * 100) if total_translated > 0 else 0
        human_percent = (human_count / total_translated * 100) if total_translated > 0 else 0
        logging.info("--- 最终资源包元数据统计 ---")
        logging.info(f"总翻译条目: {total_translated}")
        logging.info(f"  ▷ AI 翻译贡献: {ai_count} 条 ({ai_percent:.1f}%)")
        logging.info(f"  ▷ 人工及社区贡献: {human_count} 条 ({human_percent:.1f}%)")
        logging.info("-------------------------------")
        return {
            "timestamp": timestamp,
            "total": total_translated,
            "ai_count": ai_count,
            "ai_percent": f"{ai_percent:.1f}%",
            "human_count": human_count,
            "human_percent": f"{human_percent:.1f}%"
        }
    def _replace_placeholders(self, template_str: str, data: dict) -> str:
        for key, value in data.items():
            template_str = template_str.replace(f"{{{key}}}", str(value))
        return template_str
    def run_build_phase(self, pack_settings: dict):
        try:
            if self.final_translations is None:
                raise ValueError("没有可用于构建的翻译数据。请先完成翻译阶段。")
            self.log("开始生成资源包...", "INFO")
            self.update_progress("正在构建资源包...", 10)
            metadata_values = self._generate_pack_metadata_values()
            user_preset_name = pack_settings.get('preset_name', '')
            user_description = pack_settings.get('pack_description', '')
            desc_template = user_description.strip() or DEFAULT_DESC_TEMPLATE
            final_description = self._replace_placeholders(desc_template, metadata_values)
            name_template = ""
            if user_preset_name.strip() and user_preset_name != "默认预案":
                name_template = user_preset_name
            else:
                name_template = DEFAULT_NAME_TEMPLATE
            final_name = self._replace_placeholders(name_template, metadata_values)
            pack_settings['pack_description'] = final_description
            pack_settings['pack_base_name'] = final_name
            builder = PackBuilder()
            success, message = builder.run(
                output_dir=Path(self.settings['output_dir']),
                final_translations_lookup_by_ns=self.final_translations,
                pack_settings=pack_settings,
                namespace_formats=self.namespace_formats,
                raw_english_files=self.raw_english_files
            )
            if success:
                self.log(f"资源包生成成功！", "SUCCESS")
                self.update_progress("资源包生成成功！", 100)
            else:
                raise RuntimeError(message)
        except Exception as e:
            logging.error(f"构建资源包阶段失败: {e}", exc_info=True)
            self.root.after(0, lambda: messagebox.showerror("构建失败", f"构建资源包时发生错误:\n{e}"))
            self.update_progress(f"错误: {e}", -1)
    def run_workflow(self):
        if not self.save_data:
            self.log("项目数据未加载，无法直接运行完整工作流。", "ERROR")
            self.update_progress("错误: 项目数据未加载", -1)
            return
        self.log("从存档文件加载数据并启动工作台...", "INFO")
        self.update_progress("正在加载项目...", 10)
        self.raw_english_files = self.save_data.get('raw_english_files', {})
        self.namespace_formats = self.save_data.get('namespace_formats', {})
        workbench_data = self.save_data.get('workbench_data', {})
        if not all([self.raw_english_files, self.namespace_formats, workbench_data]):
            self.log("存档文件不完整，缺少核心数据。", "ERROR")
            self.update_progress("错误: 存档文件不完整", -1)
            return
        self.root.after(0, self._launch_workbench, workbench_data)