import tkinter as tk
from tkinter import messagebox
import threading
import logging
import os
import json
from pathlib import Path
import shutil
from datetime import datetime
from io import BytesIO
import ftb_snbt_lib as slib
from ftb_snbt_lib import tag

from gui import ui_utils
from core.quest_converter import FTBQuestConverter, BQMQuestConverter, LANGConverter, ConversionManager
from gui.translation_workbench import TranslationWorkbench
from utils import config_manager

class QuestWorkflowManager:
    def __init__(self, project_info, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.instance_path = Path(project_info['instance_dir'])
        self.output_path = Path(project_info.get('output_dir', str(self.instance_path)))
        
        self.quest_files_map = {}
        self.quest_type = ""
        self.converted_quest_data = None
        self.source_lang_dict = {}

    def _log(self, message, level="INFO"):
        self.main_window.log_message(message, level)
        
    def _detect_quests(self):
        found_ftb_files = list((self.instance_path / "config" / "ftbquests" / "quests").glob("**/*.snbt"))
        if found_ftb_files:
            self.quest_type = "ftb"
            for f_path in found_ftb_files:
                self.quest_files_map[f_path.name] = str(f_path)
            return True

        bqm_path = self.instance_path / "config" / "betterquesting" / "DefaultQuests.json"
        if bqm_path.is_file():
            self.quest_type = "bqm"
            self.quest_files_map[bqm_path.name] = str(bqm_path)
            return True
        
        return False

    def run_extraction_phase(self):
        try:
            if not self._detect_quests():
                raise FileNotFoundError("在指定的实例文件夹中，未能自动找到任何支持的任务文件。")
            
            self._log(f"成功发现 {len(self.quest_files_map)} 个 '{self.quest_type}' 任务文件。", "SUCCESS")
            
            quest_files_io = []
            for name, path_str in self.quest_files_map.items():
                file_bytes = Path(path_str).read_bytes()
                bytes_io = BytesIO(file_bytes)
                bytes_io.name = name
                quest_files_io.append(bytes_io)

            if self.quest_type == "ftb":
                converter = FTBQuestConverter()
            else:
                converter = BQMQuestConverter()

            conversion_manager = ConversionManager(converter)
            
            self.converted_quest_data, self.source_lang_dict = conversion_manager(
                "quest", quest_files_io, {}
            )
            
            if not self.source_lang_dict:
                raise ValueError("未在任务文件中找到可翻译的文本，流程中止。")
            
            self._log(f"成功提取 {len(self.source_lang_dict)} 条待翻译文本。", "INFO")

            workbench_data = {'quest_files': {'display_name': '任务文件', 'items': []}}
            for key, value in self.source_lang_dict.items():
                workbench_data['quest_files']['items'].append({'key': key, 'en': value, 'zh': '', 'source': '待翻译'})
            
            self.main_window.root.after(0, self._launch_workbench, workbench_data)
        
        except ValueError as ve:
             logging.warning(f"任务文本提取中止: {ve}")
             self._log(f"提示: {ve}", "WARNING")
             self.main_window.root.after(0, lambda msg=str(ve): ui_utils.show_info("操作中止", msg))
             self.main_window._show_welcome_view()

        except Exception as e:
            logging.error(f"任务文本提取失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(0, lambda err=e: ui_utils.show_error("处理失败", f"提取任务文本时发生错误:\n{err}"))
            self.main_window._show_welcome_view()

    def _launch_workbench(self, workbench_data):
        current_settings = config_manager.load_config()
        
        workbench = TranslationWorkbench(
            parent_frame=self.main_window.content_frame, 
            initial_data=workbench_data, 
            namespace_formats={},
            raw_english_files={}, 
            current_settings=current_settings,
            log_callback=self._log, 
            finish_button_text="完成并生成汉化文件",
            finish_callback=self._on_workbench_finish,
            cancel_callback=self._on_workbench_cancel,
            project_name="任务汉化",
            main_window_instance=self.main_window
        )
        
        self.main_window.workbench_instance = workbench
        workbench.pack(fill="both", expand=True)

        if self.main_window.log_pane_visible:
            self.main_window._toggle_log_pane()
        self.main_window.update_menu_state()
        self.main_window._save_current_session()

    def _on_workbench_finish(self, final_translations, final_workbench_data):
        self.main_window.update_menu_state()
        self._log("翻译工作台已关闭，准备生成最终文件。", "SUCCESS")
        
        final_lang_dict = {}
        for item in final_workbench_data.get('quest_files', {}).get('items', []):
            if item.get('zh', '').strip():
                final_lang_dict[item['key']] = item['zh']
            else:
                final_lang_dict[item['key']] = item['en']

        threading.Thread(target=self._run_build_phase, args=(final_lang_dict,), daemon=True).start()

    def _on_workbench_cancel(self):
        self.main_window.update_menu_state()
        self._log("任务汉化流程已取消。", "WARNING")

    def _run_build_phase(self, translated_dict: dict):
        try:
            instance_path = self.instance_path
            
            if self.quest_type == 'ftb':
                self._log("开始写回已转换的 FTB Quests 文件...", "INFO")
                quests_path = self.instance_path / "config" / "ftbquests" / "quests"
                for safe_filename, quest_data in self.converted_quest_data:
                    original_name = ""
                    for name in self.quest_files_map.keys():
                        if os.path.splitext(name)[0] == safe_filename:
                            original_name = name
                            break
                    if not original_name.endswith('.snbt'): original_name += '.snbt'
                    target_path = quests_path / original_name
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    content_to_write = slib.dumps(quest_data)
                    target_path.write_text(content_to_write, encoding='utf-8')
                
                lang_path = self.output_path / "kubejs" / "assets" / "ftbquests" / "lang"
                lang_path.mkdir(parents=True, exist_ok=True)
                lang_filename = "en_us.json"
                lang_content = json.dumps(self.source_lang_dict, indent=4, ensure_ascii=False)
                (lang_path / lang_filename).write_text(lang_content, encoding='utf-8')
                self._log(f"已生成 FTB 语言文件模板: {lang_path / lang_filename}", "INFO")

                if translated_dict:
                    zh_lang_filename = "zh_cn.json"
                    zh_lang_content = json.dumps(translated_dict, indent=4, ensure_ascii=False)
                    (lang_path / zh_lang_filename).write_text(zh_lang_content, encoding='utf-8')
                    self._log(f"已生成 FTB 中文语言文件: {lang_path / zh_lang_filename}", "INFO")

            elif self.quest_type == 'bqm':
                self._log("开始写回已转换的 Better Questing 文件...", "INFO")
                # BQM usually has one file
                _, quest_data = self.converted_quest_data[0]
                original_path_str = list(self.quest_files_map.values())[0]
                content_to_write = json.dumps(quest_data, indent=4, ensure_ascii=False)
                Path(original_path_str).write_text(content_to_write, encoding='utf-8')
                self._log("已将包含翻译键的任务文件写回原位。", "INFO")

                lang_path = self.output_path / "assets" / "betterquesting" / "lang"
                lang_path.mkdir(parents=True, exist_ok=True)
                lang_converter = LANGConverter()
                lang_filename = "en_us.lang"
                lang_content = lang_converter.convert_json_to_lang(self.source_lang_dict)
                (lang_path / lang_filename).write_text(lang_content, encoding='utf-8')
                self._log(f"已生成 BQM 语言文件模板: {lang_path / lang_filename}", "INFO")

                if translated_dict:
                    zh_lang_filename = "zh_cn.lang"
                    zh_lang_content = lang_converter.convert_json_to_lang(translated_dict)
                    (lang_path / zh_lang_filename).write_text(zh_lang_content, encoding='utf-8')
                    self._log(f"已将 BQM 中文语言文件写入: {lang_path / zh_lang_filename}", "INFO")

            self._log("--- 任务汉化流程全部完成！ ---", "SUCCESS")
            self._show_final_instructions()

        except Exception as e:
            logging.error(f"生成任务文件失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(0, lambda err=e: ui_utils.show_error("生成失败", f"生成最终文件时发生错误:\n{err}"))

    def _show_final_instructions(self):
        title = "任务汉化成功！"
        message = ""
        if self.quest_type == 'ftb':
            lang_dir = self.output_path / "kubejs" / "assets" / "ftbquests" / "lang"
            message = (
                "FTB Quests 文件已成功处理！\n\n"
                "1. **任务文件**已被修改，其中的英文文本已替换为翻译键。\n"
                f"2. **语言文件**已在以下目录生成：\n   {lang_dir}\n\n"
                "您可以直接使用生成的 `kubejs` 文件夹作为资源包，或放入现有的资源包中。\n\n"
            )
        else: # bqm
            lang_file_path = self.output_path / 'assets' / 'betterquesting' / 'zh_cn.lang'
            message = (
                "Better Questing 汉化文件已成功生成！\n\n"
                "---生成完成---\n"
                "我们已为您在输出目录中生成了完整的资源包结构。\n\n"
                f"1. 语言文件已生成到:\n   {lang_file_path}\n\n"
                "2. 您可以直接使用生成的资源包结构，或根据需要进行调整。\n\n"
            )
        
        self.main_window.root.after(0, lambda t=title, m=message: ui_utils.show_info(t, m))
