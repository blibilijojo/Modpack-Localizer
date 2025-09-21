import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
import threading
import logging
import os
import json
import ftb_snbt_lib as slib
from pathlib import Path
import shutil
from datetime import datetime
from gui import ui_utils
from gui.custom_widgets import ToolTip
from core.quest_converter import FTBQuestConverter, BQMQuestConverter, LANGConverter, safe_name
from gui.translation_workbench import TranslationWorkbench
class TabQuestLocalization:
    def __init__(self, parent, ai_service_tab, ai_parameters_tab, main_control_tab):
        self.frame = ttk.Frame(parent, padding="10")
        self.root = parent.winfo_toplevel()
        self.ai_service_tab = ai_service_tab
        self.ai_parameters_tab = ai_parameters_tab
        self.main_control_tab = main_control_tab
        self.modpack_name_var = tk.StringVar(value="MyModpack")
        self.quest_type_var = tk.StringVar(value="")
        self.instance_dir_var = tk.StringVar()
        self.quest_files = {}
        self.converted_quest_data = None
        self.current_quest_type = ""
        self.source_lang_dict = {}
        self.safe_name_to_path_map = {}
        self._create_widgets()
    def _log_message(self, message, level="NORMAL"):
        if self.main_control_tab:
            self.main_control_tab.log_message(message, level)
    def _create_widgets(self):
        settings_frame = ttk.LabelFrame(self.frame, text="任务汉化设置", padding="10")
        settings_frame.pack(fill="x", expand=False)
        settings_frame.columnconfigure(1, weight=1)
        ttk.Label(settings_frame, text="整合包名称 (英文):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        name_entry = ttk.Entry(settings_frame, textvariable=self.modpack_name_var)
        name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=5)
        ToolTip(name_entry, "用于生成本地化键的前缀, 请使用简短的英文名")
        ttk.Label(settings_frame, text="Minecraft 实例文件夹:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        instance_frame = ttk.Frame(settings_frame)
        instance_frame.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5, pady=5)
        instance_frame.columnconfigure(0, weight=1)
        instance_entry = ttk.Entry(instance_frame, textvariable=self.instance_dir_var)
        instance_entry.grid(row=0, column=0, sticky="ew")
        ToolTip(instance_entry, "选择你的整合包根目录 (.minecraft 文件夹)")
        ttk.Button(instance_frame, text="浏览并自动检测...", command=self._browse_and_detect_quests, bootstyle="info").grid(row=0, column=1, padx=(5,0))
        ttk.Label(settings_frame, text="自动识别的任务类型:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        type_frame = ttk.Frame(settings_frame)
        type_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        ftb_radio = ttk.Radiobutton(type_frame, text="FTB Quests (.snbt)", variable=self.quest_type_var, value="ftb", state="disabled")
        ftb_radio.pack(side="left", padx=(0, 20))
        bqm_radio = ttk.Radiobutton(type_frame, text="Better Questing (.json)", variable=self.quest_type_var, value="bqm", state="disabled")
        bqm_radio.pack(side="left")
        files_frame = ttk.LabelFrame(self.frame, text="自动发现的任务文件 (只读)", padding="10")
        files_frame.pack(fill="both", expand=True, pady=10)
        theme_bg_color = ttk.Style().lookup('TFrame', 'background')
        self.found_files_text = scrolledtext.ScrolledText(files_frame, height=8, state="disabled", relief="flat", background=theme_bg_color)
        self.found_files_text.pack(fill="both", expand=True)
        action_frame = ttk.Frame(self.frame)
        action_frame.pack(fill="x", pady=20)
        action_frame.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(action_frame, text="提取文本并打开工作台", command=self._start_processing_async, bootstyle="success", state="disabled")
        self.start_button.grid(row=0, column=0, sticky="ew", ipady=10)
    def _update_found_files_display(self):
        self.found_files_text.config(state="normal")
        self.found_files_text.delete("1.0", tk.END)
        if not self.quest_files:
            self.found_files_text.insert(tk.END, "未发现任何文件。")
        else:
            for filename in self.quest_files.keys():
                self.found_files_text.insert(tk.END, filename + "\n")
        self.found_files_text.config(state="disabled")
    def _browse_and_detect_quests(self):
        path_str = filedialog.askdirectory(title="选择你的 Minecraft 实例文件夹 (例如 .minecraft)")
        if not path_str:
            return
        self.instance_dir_var.set(path_str)
        instance_path = Path(path_str)
        self.quest_files.clear()
        self.quest_type_var.set("")
        found_ftb_files = []
        found_bqm_file = None
        ftb_base_paths = [
            instance_path / "kubejs" / "data" / "ftbquests" / "quests",
            instance_path / "config" / "ftbquests" / "quests"
        ]
        for base_path in ftb_base_paths:
            if base_path.is_dir():
                found_ftb_files.extend(list(base_path.glob("**/*.snbt")))
        bqm_path = instance_path / "config" / "betterquesting" / "DefaultQuests.json"
        if bqm_path.is_file():
            found_bqm_file = bqm_path
        if found_ftb_files and found_bqm_file:
            ui_utils.show_warning("检测到多种任务模组", "同时检测到 FTB Quests 和 Better Questing 的文件。\n将优先处理 FTB Quests。")
            self.quest_type_var.set("ftb")
            for f_path in found_ftb_files:
                self.quest_files[f_path.name] = str(f_path)
        elif found_ftb_files:
            self.quest_type_var.set("ftb")
            for f_path in found_ftb_files:
                self.quest_files[f_path.name] = str(f_path)
        elif found_bqm_file:
            self.quest_type_var.set("bqm")
            self.quest_files[found_bqm_file.name] = str(found_bqm_file)
        if self.quest_files:
            self._log_message(f"成功发现 {len(self.quest_files)} 个 '{self.quest_type_var.get()}' 任务文件。", "SUCCESS")
            ui_utils.show_info("发现成功", f"已成功自动发现 {len(self.quest_files)} 个任务文件！")
            self.start_button.config(state="normal")
        else:
            self._log_message("在所选目录中未找到支持的任务文件。", "WARNING")
            ui_utils.show_error("未找到文件", "在所选的实例文件夹中，未能自动找到任何 FTB Quests 或 Better Questing 的任务文件。")
            self.start_button.config(state="disabled")
        self._update_found_files_display()
    def _start_processing_async(self):
        if not self.modpack_name_var.get().strip():
            ui_utils.show_error("输入错误", "整合包名称不能为空。")
            return
        if not self.quest_files:
            ui_utils.show_error("输入错误", "未找到任何任务文件可供处理。")
            return
        if not self.instance_dir_var.get() or not Path(self.instance_dir_var.get()).is_dir():
            ui_utils.show_error("输入错误", "请先指定一个有效的实例文件夹。")
            return
        self.start_button.config(state="disabled", text="提取中...")
        threading.Thread(target=self._run_extraction_phase, daemon=True).start()
    def _run_extraction_phase(self):
        try:
            self._log_message("--- 开始任务文本提取流程 ---", "SUCCESS")
            read_files_content = {}
            for name, path in self.quest_files.items():
                try:
                    with open(path, 'r', encoding='utf-8-sig') as f:
                        read_files_content[name] = f.read()
                except Exception as e:
                    raise IOError(f"读取文件 '{name}' 失败: {e}")
            self._log_message("阶段 1/2: 提取任务文件中的文本...", "INFO")
            quest_type = self.quest_type_var.get()
            converter = FTBQuestConverter() if quest_type == "ftb" else BQMQuestConverter()
            modpack_name = self.modpack_name_var.get()
            self.safe_name_to_path_map = {
                safe_name(os.path.splitext(name)[0]): path for name, path in self.quest_files.items()
            }
            converted_quest_arr, source_lang_dict = converter.convert(modpack_name, read_files_content)
            if not source_lang_dict:
                raise ValueError("未在任务文件中找到可翻译的文本，流程中止。")
            self._log_message(f"成功提取 {len(source_lang_dict)} 条待翻译文本。", "INFO")
            self.converted_quest_data = converted_quest_arr
            self.current_quest_type = quest_type
            self.source_lang_dict = source_lang_dict
            self._log_message("阶段 2/2: 准备启动翻译工作台...", "INFO")
            self.root.after(0, self._launch_workbench)
        except Exception as e:
            logging.error(f"任务文本提取失败: {e}", exc_info=True)
            self._log_message(f"错误: {e}", "CRITICAL")
            self.root.after(0, lambda err=e: ui_utils.show_error("处理失败", f"提取文本时发生错误:\n{err}"))
            self.root.after(0, lambda: self.start_button.config(state="normal", text="提取文本并打开工作台"))
    def _launch_workbench(self):
        workbench_data = {
            'quest_files': {
                'jar_name': '任务文件',
                'items': []
            }
        }
        for key, value in self.source_lang_dict.items():
            workbench_data['quest_files']['items'].append({
                'key': key,
                'en': value,
                'zh': '',
                'source': '待翻译'
            })
        current_settings = {
            **self.ai_service_tab.get_and_save_settings(),
            **self.ai_parameters_tab.get_and_save_settings(),
        }
        workbench = TranslationWorkbench(
            parent=self.root,
            initial_data=workbench_data,
            namespace_formats={}, 
            raw_english_files={}, 
            current_settings=current_settings,
            log_callback=self._log_message,
            finish_button_text="完成并生成任务文件"
        )
        self.root.wait_window(workbench)
        if workbench.final_translations:
            self._log_message("翻译工作台已关闭，准备生成最终文件。", "SUCCESS")
            final_quest_translations = workbench.final_translations.get('quest_files', {})
            self._run_build_phase(final_quest_translations)
        else:
            self._log_message("翻译工作台已取消，操作中止。", "WARNING")
            self.start_button.config(state="normal", text="提取文本并打开工作台")
    def _run_build_phase(self, translated_dict: dict):
        try:
            self._log_message("开始原位替换文件...", "INFO")
            instance_path = Path(self.instance_dir_var.get())
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = instance_path / f".localizer_backups_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)
            self._log_message(f"正在备份原始文件到: {backup_path}", "INFO")
            for original_file_path_str in self.quest_files.values():
                shutil.copy(original_file_path_str, backup_path)
            for safe_filename, quest_data in self.converted_quest_data:
                original_path = self.safe_name_to_path_map.get(safe_filename)
                if not original_path:
                    logging.warning(f"找不到 '{safe_filename}' 对应的原始路径，跳过文件写入。")
                    continue
                if self.current_quest_type == 'ftb':
                    content_to_write = slib.dumps(quest_data)
                else:
                    content_to_write = json.dumps(quest_data, indent=4, ensure_ascii=False)
                with open(original_path, 'w', encoding='utf-8') as f:
                    f.write(content_to_write)
            self._log_message("已成功将汉化后的任务文件写回原位。", "INFO")
            if self.current_quest_type == 'ftb':
                lang_path = instance_path / "kubejs" / "assets" / "kubejs" / "lang"
                lang_path.mkdir(parents=True, exist_ok=True)
                lang_filename = "zh_cn.json"
                lang_content = json.dumps(translated_dict, indent=4, ensure_ascii=False)
                (lang_path / lang_filename).write_text(lang_content, encoding='utf-8')
                self._log_message(f"已将语言文件写入: {lang_path / lang_filename}", "INFO")
            else:
                lang_path = instance_path / "config" / "betterquesting"
                lang_path.mkdir(parents=True, exist_ok=True)
                lang_converter = LANGConverter()
                lang_filename = "zh_cn.lang"
                lang_content = lang_converter.convert_json_to_lang(translated_dict)
                (lang_path / lang_filename).write_text(lang_content, encoding='utf-8')
                self._log_message(f"已将语言文件写入: {lang_path / lang_filename}", "INFO")
            self._log_message("--- 任务汉化流程全部完成！ ---", "SUCCESS")
            self._show_final_instructions(backup_path)
        except Exception as e:
            logging.error(f"生成任务文件失败: {e}", exc_info=True)
            self._log_message(f"错误: {e}", "CRITICAL")
            self.root.after(0, lambda err=e: ui_utils.show_error("生成失败", f"生成最终文件时发生错误:\n{err}"))
        finally:
            self.start_button.config(state="normal", text="提取文本并打开工作台")
    def _show_final_instructions(self, backup_path: Path):
        title = "任务汉化成功！"
        if self.current_quest_type == 'ftb':
            message = (
                "所有任务文件已在原位被成功汉化！\n\n"
                f"为安全起见，所有原始文件都已备份至:\n{backup_path}\n\n"
                "---重要---\n"
                "语言文件 (zh_cn.json) 已自动为您放置在以下推荐位置：\n"
                f"{Path(self.instance_dir_var.get()) / 'kubejs' / 'assets' / 'kubejs' / 'lang'}\n\n"
                "现在，您可以直接启动游戏查看效果了！"
            )
        else:
            lang_file_path = Path(self.instance_dir_var.get()) / 'config' / 'betterquesting' / 'zh_cn.lang'
            message = (
                "所有任务文件已在原位被成功汉化！\n\n"
                f"为安全起见，所有原始文件都已备份至:\n{backup_path}\n\n"
                "---您还需要最后一步手动操作---\n"
                "Better Questing 的语言文件需要放入资源包才能加载。\n\n"
                f"1. 我们已为您生成了语言文件:\n   {lang_file_path}\n\n"
                "2. 请将这个 zh_cn.lang 文件**移动**到您自己的一个资源包内，路径为：\n"
                "   [你的资源包]/assets/betterquesting/lang/\n\n"
                "3. 在游戏中启用该资源包并重启，即可看到效果！"
            )
        ui_utils.show_info(title, message)