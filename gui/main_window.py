import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext, Menu
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import logging
import threading
from pathlib import Path
import json
import webbrowser
import os
import re
import sys

from gui import ui_utils
from gui.dialogs import PackPresetDialog, DownloadProgressDialog
from utils import config_manager, session_manager
from core.orchestrator import Orchestrator
from _version import __version__
from gui.quest_workflow_manager import QuestWorkflowManager
from gui.translation_workbench import TranslationWorkbench
from gui.find_replace_dialog import FindReplaceDialog
from gui.theme_utils import set_title_bar_theme
from gui.settings_window import SettingsWindow

class ProjectTab:
    def __init__(self, parent_notebook, root_window, main_window_instance):
        self.root = root_window
        self.main_window = main_window_instance
        self.frame = ttk.Frame(parent_notebook)
        self.orchestrator = None
        self.workbench_instance = None
        self.tab_id = None
        self.log_pane_visible = True
        self.project_name = "新项目"
        self.project_type = "mod"
        self.project_info = {}
        self.loading_frame = None
        self.tab_uuid = None
        self._is_fully_loaded = False
        self._restored_state_data = None
        # 线程管理属性
        self.background_threads = []
        self.stop_event = threading.Event()

        self.project_type_var = tk.StringVar(value="mod")
        self.mods_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.jar_dir_var = tk.StringVar()
        self.instance_dir_var = tk.StringVar()
        self.modpack_name_var = tk.StringVar()

        self._create_widgets()
        self._show_welcome_view()
        self._toggle_log_pane()
    
    def add_background_thread(self, thread):
        """添加后台线程到管理列表"""
        self.background_threads.append(thread)
    
    def stop_all_threads(self):
        """停止所有后台线程"""
        # 设置停止事件
        self.stop_event.set()
        
        # 遍历所有线程并尝试停止
        for thread in self.background_threads:
            if thread.is_alive():
                # 对于守护线程，它们会在主线程退出时自动停止
                # 这里主要是为了清理线程引用
                pass
        
        # 清空线程列表
        self.background_threads = []

    def get_state(self):
        if not self.workbench_instance:
            if self._restored_state_data:
                return {
                    "project_name": self.project_name,
                    "project_type": self.project_type,
                    "project_info": self._clean_project_info(),
                    "workbench_state": self._restored_state_data.get("workbench_state"),
                    "tab_uuid": self.tab_uuid,
                    "namespace_summary": self._restored_state_data.get("namespace_summary", []),
                }
            return None

        workbench_state = self.workbench_instance.get_state()
        return {
            "project_name": self.project_name,
            "project_type": self.project_type,
            "project_info": self._clean_project_info(),
            "workbench_state": workbench_state,
            "tab_uuid": self.tab_uuid,
            "namespace_summary": self._get_namespace_summary(),
        }

    def _clean_project_info(self):
        """清理项目信息，移除临时目录路径"""
        if not self.project_info:
            return {}
        cleaned = {}
        for key, value in self.project_info.items():
            if key == 'mods_dir' and value and 'AppData\\Local\\Temp' in str(value):
                continue
            cleaned[key] = value
        return cleaned

    def _get_namespace_summary(self):
        """获取namespace摘要信息，用于懒加载恢复"""
        if not self.workbench_instance or not self.workbench_instance.translation_data:
            return []
        
        summary = []
        for ns, data in sorted(self.workbench_instance.translation_data.items()):
            items = data.get('items', [])
            total_count = len(items)
            completed = sum(1 for item in items if item.get('zh', '').strip())
            summary.append({
                'ns': ns,
                'jar_name': data.get('jar_name', ''),
                'total': total_count,
                'completed': completed
            })
        return summary

    def _lazy_load_workbench(self):
        """懒加载工作台数据"""
        if self._is_fully_loaded or not self._restored_state_data:
            return
        
        state_data = self._restored_state_data
        self._restored_state_data = None
        self._is_fully_loaded = True
        
        workbench_state = state_data.get('workbench_state')
        if not workbench_state:
            self.log_message("会话状态不完整，无法恢复工作台。", "ERROR")
            self._show_welcome_view()
            return
        
        current_settings = config_manager.load_config()
        finish_text = ""

        if self.project_type == "mod":
            self.orchestrator = Orchestrator(
                settings=current_settings,
                update_progress=self.update_progress,
                root_window=self.root,
                log_callback=self.log_message
            )
            # 传递停止事件
            self.orchestrator.stop_event = self.stop_event
            self.orchestrator.raw_english_files = workbench_state['raw_english_files']
            self.orchestrator.namespace_formats = workbench_state['namespace_formats']
            finish_text = "完成并生成资源包"
        
        elif self.project_type == "quest":
            if not self.project_info:
                self.log_message("项目信息丢失，无法恢复任务汉化流程。", "ERROR")
                self._show_welcome_view()
                return

            self.quest_manager = QuestWorkflowManager(project_info=self.project_info, main_window=self)
            def run_quest_build(trans_dict):
                threading.Thread(target=self.quest_manager._run_build_phase, args=(trans_dict,), daemon=True).start()
            self._run_quest_build_phase = run_quest_build
            finish_text = "完成"

        self._show_workbench_view(
            workbench_data=workbench_state['workbench_data'],
            namespace_formats=workbench_state['namespace_formats'],
            raw_english_files=workbench_state['raw_english_files'],
            current_settings=current_settings,
            project_path=workbench_state['current_project_path'],
            finish_button_text=finish_text
        )
        self.log_message(f"项目 '{self.project_name}' 已从缓存中成功恢复。", "SUCCESS")

    def restore_from_state(self, state_data: dict):
        self.project_name = state_data.get("project_name", "已恢复的项目")
        self.project_type = state_data.get("project_type", "mod")
        self.project_info = state_data.get("project_info", {})
        self.tab_uuid = state_data.get("tab_uuid")
        
        self.main_window.update_tab_title(self.tab_id, self.project_name)
        
        namespace_summary = state_data.get("namespace_summary", [])
        workbench_state = state_data.get("workbench_state")
        
        if not workbench_state:
            self.log_message("会话状态不完整，无法恢复工作台。", "ERROR")
            self._show_welcome_view()
            return
        
        self._restored_state_data = state_data
        self._is_fully_loaded = False
        
        self._show_lazy_loaded_view(namespace_summary)
        self.log_message(f"项目 '{self.project_name}' 已恢复（懒加载模式）。", "INFO")

    def _show_lazy_loaded_view(self, namespace_summary: list):
        """显示懒加载视图，只显示namespace名称列表"""
        self._clear_content_frame()
        if self.log_pane_visible:
            self._toggle_log_pane()
        
        container = ttk.Frame(self.content_frame)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(container, text=f"项目: {self.project_name}", font=("-size 14 -weight bold")).pack(anchor="w", pady=(0, 10))
        
        info_label = ttk.Label(container, text="点击下方按钮加载项目数据，或双击项目列表中的项目标签加载", bootstyle="secondary")
        info_label.pack(anchor="w", pady=(0, 20))
        
        load_btn = ttk.Button(container, text="加载项目", command=self._lazy_load_workbench, bootstyle="primary")
        load_btn.pack(anchor="w", pady=(0, 20))
        
        if namespace_summary:
            summary_frame = tk_ttk.LabelFrame(container, text="项目概览", padding=10)
            summary_frame.pack(fill="both", expand=True)
            
            summary_tree = ttk.Treeview(summary_frame, columns=("namespace", "jar", "total", "completed"), show="headings", height=15)
            summary_tree.heading("namespace", text="命名空间")
            summary_tree.heading("jar", text="来源")
            summary_tree.heading("total", text="总条目")
            summary_tree.heading("completed", text="已翻译")
            
            summary_tree.column("namespace", width=200)
            summary_tree.column("jar", width=150)
            summary_tree.column("total", width=80, anchor="center")
            summary_tree.column("completed", width=80, anchor="center")
            
            scrollbar = ttk.Scrollbar(summary_frame, orient="vertical", command=summary_tree.yview)
            summary_tree.configure(yscroll=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            summary_tree.pack(fill="both", expand=True)
            
            total_items = 0
            total_completed = 0
            for item in namespace_summary:
                ns = item.get('ns', '')
                jar = item.get('jar_name', '未知')
                total = item.get('total', 0)
                completed = item.get('completed', 0)
                summary_tree.insert("", "end", values=(ns, jar, total, completed))
                total_items += total
                total_completed += completed
            
            ttk.Label(summary_frame, text=f"总计: {total_items} 条条目, {total_completed} 条已翻译", bootstyle="secondary").pack(anchor="w", pady=(10, 0))
        
        self.content_frame.update_idletasks()
        self.main_window.update_menu_state()

    def _create_widgets(self):
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)

        self.content_frame = ttk.Frame(self.frame)
        self.content_frame.grid(row=0, column=0, sticky="nsew")

        self.log_container_frame = tk_ttk.LabelFrame(self.frame, text="状态与日志", padding="10")
        self.log_container_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(self.log_container_frame, height=8, state="disabled", wrap=tk.WORD, font=("Consolas", 9), relief="flat")
        self.log_text.pack(fill="both", expand=True, pady=5)
        
        self._update_log_tag_colors()
        
        status_bar_frame = ttk.Frame(self.frame, padding=(10, 5), bootstyle="secondary")
        status_bar_frame.grid(row=2, column=0, sticky="ew")
        status_bar_frame.columnconfigure(1, weight=1)

        self.toggle_log_btn = ttk.Button(status_bar_frame, text="隐藏日志", command=self._toggle_log_pane, bootstyle="secondary")
        self.toggle_log_btn.grid(row=0, column=0, sticky="w")
        
        self.status_var = tk.StringVar(value="准备就绪")
        status_label = ttk.Label(status_bar_frame, textvariable=self.status_var, anchor="w", bootstyle="inverse-secondary")
        status_label.grid(row=0, column=1, sticky="ew", padx=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(status_bar_frame, variable=self.progress_var, maximum=100, style="Striped.Horizontal.TProgressbar", length=200)
        self.progress_bar.grid(row=0, column=2, sticky="e")

    def _update_log_tag_colors(self):
        style = self.root.style
        self.log_text.tag_config("INFO", foreground=style.colors.secondary)
        self.log_text.tag_config("WARNING", foreground=style.colors.warning)
        self.log_text.tag_config("ERROR", foreground=style.colors.danger)
        self.log_text.tag_config("SUCCESS", foreground=style.colors.success)
        self.log_text.tag_config("NORMAL", foreground=style.colors.fg)
        self.log_text.tag_config("CRITICAL", foreground=style.colors.danger, font=("Consolas", 9, "bold"))

    def _toggle_log_pane(self):
        if self.log_pane_visible:
            self.log_container_frame.grid_remove()
            self.toggle_log_btn.config(text="显示日志")
            self.frame.rowconfigure(1, weight=0)
        else:
            self.log_container_frame.grid()
            self.toggle_log_btn.config(text="隐藏日志")
            self.frame.rowconfigure(1, weight=1)
        self.log_pane_visible = not self.log_pane_visible

    def _clear_content_frame(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _show_welcome_view(self):
        self._clear_content_frame()
        self.workbench_instance = None
        self.main_window.update_menu_state()
        self.project_name = "新项目"
        if self.tab_id:
            self.main_window.update_tab_title(self.tab_id, "新项目")
        
        container = ttk.Frame(self.content_frame)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        container.columnconfigure((0, 1), weight=1, uniform="group1")
        container.rowconfigure(0, weight=1)

        new_project_frame = tk_ttk.LabelFrame(container, text="开始新项目", padding=20)
        new_project_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        new_project_frame.rowconfigure(2, weight=1)

        mod_rb = ttk.Radiobutton(new_project_frame, text="模组汉化", variable=self.project_type_var, value="mod", style="TRadiobutton")
        mod_rb.pack(anchor="w", pady=(5, 0))
        ttk.Label(new_project_frame, text="推荐流程。扫描Mods文件夹，生成标准汉化资源包。", bootstyle="secondary").pack(anchor="w", padx=(20, 0), pady=(0, 15))

        mod_search_rb = ttk.Radiobutton(new_project_frame, text="模组搜索", variable=self.project_type_var, value="modsearch", style="TRadiobutton")
        mod_search_rb.pack(anchor="w", pady=(5, 0))
        ttk.Label(new_project_frame, text="从Modrinth和CurseForge平台搜索模组，自动下载并启动汉化流程。", bootstyle="secondary").pack(anchor="w", padx=(20, 0), pady=(0, 15))

        quest_rb = ttk.Radiobutton(new_project_frame, text="任务汉化", variable=self.project_type_var, value="quest", style="TRadiobutton")
        quest_rb.pack(anchor="w", pady=(5, 0))
        ttk.Label(new_project_frame, text="特定流程。处理FTB Quests或BQM任务文件。", bootstyle="secondary").pack(anchor="w", padx=(20, 0), pady=(0, 15))

        github_rb = ttk.Radiobutton(new_project_frame, text="从GitHub下载", variable=self.project_type_var, value="github", style="TRadiobutton")
        github_rb.pack(anchor="w", pady=(5, 0))
        ttk.Label(new_project_frame, text="从GitHub汉化仓库下载项目并创建标签页。", bootstyle="secondary").pack(anchor="w", padx=(20, 0), pady=(0, 15))

        ttk.Button(new_project_frame, text="下一步", command=self._show_setup_view, bootstyle="primary").pack(side="bottom", anchor="se")

        load_project_frame = tk_ttk.LabelFrame(container, text="继续已有项目", padding=20)
        load_project_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        load_project_frame.rowconfigure(0, weight=1)
        load_project_frame.columnconfigure(0, weight=1)
        
        load_btn = ttk.Button(load_project_frame, text="加载项目文件 (.sav)", command=self._load_project, bootstyle="outline")
        load_btn.place(relx=0.5, rely=0.5, anchor="center")

    def _show_setup_view(self):
        self._clear_content_frame()
        self.project_type = self.project_type_var.get()
        
        container_wrapper = ttk.Frame(self.content_frame)
        container_wrapper.pack(expand=True)

        container = tk_ttk.LabelFrame(container_wrapper, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        title_text = "配置模组汉化项目" if self.project_type == "mod" else "配置任务汉化项目"
        ttk.Label(container, text=title_text, font=("-size 14 -weight bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 20))

        if self.project_type == "mod":
            self.main_window.update_tab_title(self.tab_id, "模组汉化设置")
            config = config_manager.load_config()
            self.mods_dir_var.set(config.get("mods_dir", ""))
            self.output_dir_var.set(config.get("output_dir", ""))

            ttk.Label(container, text="Mods 文件夹:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.mods_dir_var, width=60).grid(row=1, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.mods_dir_var)).grid(row=1, column=2, padx=5, pady=8)

            ttk.Label(container, text="输出文件夹:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.output_dir_var, width=60).grid(row=2, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.output_dir_var)).grid(row=2, column=2, padx=5, pady=8)
            
            start_command = self._setup_new_mod_project
        
        elif self.project_type == "modsearch":
            self.main_window.update_tab_title(self.tab_id, "模组搜索设置")
            config = config_manager.load_config()
            self.output_dir_var.set(config.get("output_dir", ""))
            self.jar_dir_var.set(config.get("jar_dir", ""))

            ttk.Label(container, text="汉化包输出:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.output_dir_var, width=60).grid(row=1, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.output_dir_var)).grid(row=1, column=2, padx=5, pady=8)

            ttk.Label(container, text="JAR 下载:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.jar_dir_var, width=60).grid(row=2, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.jar_dir_var)).grid(row=2, column=2, padx=5, pady=8)

            start_command = self._setup_new_mod_search_project
        
        elif self.project_type == "quest":
            self.main_window.update_tab_title(self.tab_id, "任务汉化设置")
            self.modpack_name_var.set("MyModpack")
            config = config_manager.load_config()
            self.output_dir_var.set(config.get("output_dir", ""))

            ttk.Label(container, text="MC 实例文件夹:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.instance_dir_var, width=60).grid(row=1, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.instance_dir_var)).grid(row=1, column=2, padx=5, pady=8)

            ttk.Label(container, text="输出文件夹:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
            ttk.Entry(container, textvariable=self.output_dir_var, width=60).grid(row=2, column=1, sticky="ew", padx=5, pady=8)
            ttk.Button(container, text="浏览...", command=lambda: ui_utils.browse_directory(self.output_dir_var)).grid(row=2, column=2, padx=5, pady=8)
            
            start_command = self._setup_new_quest_project
        elif self.project_type == "github":
            # 直接打开GitHub下载UI
            self.main_window._open_github_download_ui()
            return
        
        else:
            self._show_welcome_view()
            return

        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=3, column=0, columnspan=3, sticky="e", pady=(20, 0))
        ttk.Button(btn_frame, text="返回", command=self._show_welcome_view, bootstyle="secondary").pack(side="left", padx=10)
        ttk.Button(btn_frame, text="开始处理", command=start_command, bootstyle="success").pack(side="left")

    def _show_workbench_view(self, workbench_data, namespace_formats, raw_english_files, current_settings, project_path, finish_button_text="完成", save_session_after=False):
        self._clear_content_frame()
        if self.log_pane_visible:
            self._toggle_log_pane()
        self.workbench_instance = TranslationWorkbench(
            parent_frame=self.content_frame,
            initial_data=workbench_data,
            namespace_formats=namespace_formats,
            raw_english_files=raw_english_files,
            current_settings=current_settings,
            log_callback=self.log_message,
            project_path=project_path,
            finish_button_text=finish_button_text,
            finish_callback=self._on_workbench_finish,
            cancel_callback=self._on_workbench_cancel,
            project_name=self.project_name,
            main_window_instance=self.main_window
        )
        self.workbench_instance.pack(fill="both", expand=True)
        self.content_frame.update_idletasks()
        self.workbench_instance.update_idletasks()
        self.main_window.update_menu_state()
        # 仅在正常的翻译决策流程中保存会话，不在标签页恢复过程中保存
        if save_session_after:
            self.main_window._save_current_session()

    def _on_workbench_finish(self, final_translations, final_workbench_data):
        self.main_window.update_menu_state()
        if self.project_type == "mod":
            self.orchestrator.final_translations = final_translations
            self.orchestrator.final_workbench_data = final_workbench_data
            self.log_message("翻译工作台已关闭，数据已准备好生成资源包。", "SUCCESS")
            self.update_progress("翻译处理完成，现在可以生成资源包", -10)
        elif self.project_type == "quest":
             self.log_message("任务汉化已完成，准备生成最终文件。", "SUCCESS")
             final_translations_quest = final_translations.get('quest_files', {})
             self._run_quest_build_phase(final_translations_quest)
             self._show_welcome_view()

    def _on_workbench_cancel(self):
        self.main_window.update_menu_state()
        self.log_message("翻译工作台已取消，操作中止。", "WARNING")
        self.update_progress("操作已取消", -2)
        self._show_welcome_view()

    def log_message(self, message, level="NORMAL"):
        def _log():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, message + "\n", level)
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        try:
            if self.root.winfo_exists(): self.root.after(0, _log)
        except (RuntimeError, tk.TclError): pass

    def update_progress(self, message, percentage):
        def _update():
            self.status_var.set(message)
            self.progress_bar.config(bootstyle="info-striped")
            if percentage >= 0: self.progress_var.set(percentage)

            if percentage == 100: 
                # 仅当翻译处理完成时才重置UI，资源包生成使用99%
                self._reset_ui_after_workflow("success")
            elif percentage == 99:
                # 资源包生成成功，重置UI，移除加载界面，保持工作台可见
                self._reset_ui_after_workflow("success")
                self.status_var.set("资源包生成成功！您可以继续修改或再次生成。")
                self.progress_bar.config(bootstyle="success")
            elif percentage < 0:
                status_map = {-1: "error", -2: "cancelled", -10: "continue"}
                final_status = status_map.get(percentage, "error")
                if final_status == "continue":
                     self.status_var.set("翻译处理完成，请选择预案以生成")
                     self.progress_bar.config(bootstyle="success")
                     self.progress_var.set(100)
                     self.root.after(100, self._continue_to_build_phase)
                else:
                    self._reset_ui_after_workflow(final_status)
        try:
            if self.root.winfo_exists(): self.root.after(0, _update)
        except (RuntimeError, tk.TclError): pass

    def _setup_new_mod_project(self):
        mods_dir = self.mods_dir_var.get()
        output_dir = self.output_dir_var.get()
        if not mods_dir or not output_dir:
            ui_utils.show_error("路径不能为空", "请同时指定 Mods 文件夹和输出文件夹。", parent=self.root)
            return
        
        self.project_type = "mod"
        self.project_name = Path(mods_dir).parent.name
        self.project_info = {"mods_dir": mods_dir, "output_dir": output_dir}
        self.main_window.update_tab_title(self.tab_id, self.project_name)
        
        config = config_manager.load_config()
        config['mods_dir'] = mods_dir
        config['output_dir'] = output_dir
        config_manager.save_config(config)
        self.log_message("模组汉化项目已配置，开始执行...", "INFO")

        self._prepare_ui_for_workflow(1)
        self.orchestrator = Orchestrator(
            settings=config,
            update_progress=self.update_progress,
            root_window=self.root,
            log_callback=self.log_message
        )
        # 传递停止事件
        self.orchestrator.stop_event = self.stop_event
        self.orchestrator._launch_workbench = lambda data: self._show_workbench_view(data, self.orchestrator.namespace_formats, self.orchestrator.raw_english_files, config, None, "完成并生成资源包", save_session_after=True)
        thread = threading.Thread(target=self.orchestrator.run_translation_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _setup_new_quest_project(self):
        instance_dir = self.instance_dir_var.get()
        output_dir = self.output_dir_var.get()
        if not instance_dir:
            ui_utils.show_error("输入不能为空", "请指定实例文件夹。", parent=self.root)
            return

        self.project_type = "quest"
        self.project_name = "任务汉化"
        self.project_info = {"instance_dir": instance_dir, "output_dir": output_dir}
        self.log_message("任务汉化项目已配置，开始提取文本...", "INFO")
        self.main_window.update_tab_title(self.tab_id, "任务汉化")
        
        # 保存配置
        config = config_manager.load_config()
        config['output_dir'] = output_dir
        config_manager.save_config(config)
        
        self.quest_manager = QuestWorkflowManager(project_info=self.project_info, main_window=self)
        
        def launch_quest_workbench(data):
             self._show_workbench_view(data, {}, {}, config_manager.load_config(), None, "完成")
        self.quest_manager._launch_workbench = launch_quest_workbench

        def run_quest_build(trans_dict):
            thread = threading.Thread(target=self.quest_manager._run_build_phase, args=(trans_dict,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_quest_build_phase = run_quest_build

        thread = threading.Thread(target=self.quest_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()
    
    def _setup_new_mod_search_project(self):
        output_dir = self.output_dir_var.get()
        jar_dir = self.jar_dir_var.get()
        if not output_dir:
            ui_utils.show_error("输入不能为空", "请指定汉化包输出文件夹。", parent=self.root)
            return
        if not jar_dir:
            ui_utils.show_error("输入不能为空", "请指定 JAR 下载文件夹。", parent=self.root)
            return

        self.project_type = "modsearch"
        self.project_name = "模组搜索"
        self.project_info = {"output_dir": output_dir, "jar_dir": jar_dir}
        self.log_message("模组搜索项目已配置，开始搜索界面...", "INFO")
        self.main_window.update_tab_title(self.tab_id, "模组搜索")

        # 保存配置
        config = config_manager.load_config()
        config['output_dir'] = output_dir
        config['jar_dir'] = jar_dir
        config_manager.save_config(config)

        # 显示模组搜索界面
        self._show_mod_search_view()
    
    def _show_mod_search_view(self):
        """显示模组搜索界面"""
        self._clear_content_frame()
        if not self.log_pane_visible:
            self._toggle_log_pane()
        
        # 创建主容器
        main_container = ttk.Frame(self.content_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 使用网格布局管理主容器
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=0)
        main_container.rowconfigure(1, weight=1)
        
        # 搜索和筛选区域
        search_frame = ttk.LabelFrame(main_container, text="搜索")
        search_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        
        # 搜索输入框
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_input_frame, text="搜索关键词:", width=10).pack(side="left", padx=5, pady=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_input_frame, textvariable=self.search_var, width=60)
        search_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        search_entry.bind("<Return>", lambda e: self.start_mod_search())
        
        # 筛选选项
        filter_frame = ttk.Frame(search_frame)
        filter_frame.pack(fill="x")
        
        ttk.Label(filter_frame, text="平台:", width=10).pack(side="left", padx=5, pady=5)
        self.platform_var = tk.StringVar(value="CurseForge")
        platform_combo = ttk.Combobox(filter_frame, textvariable=self.platform_var, values=["Modrinth", "CurseForge"], state="readonly", width=15)
        platform_combo.pack(side="left", padx=5, pady=5)
        platform_combo.bind("<<ComboboxSelected>>", lambda e: platform_combo.selection_clear())

        ttk.Label(filter_frame, text="游戏版本:", width=10).pack(side="left", padx=5, pady=5)
        self.game_version_var = tk.StringVar(value="全部")
        game_versions = [
            "全部", "1.21", "1.20.4", "1.20.2", "1.20.1", "1.20", "1.19.4",
            "1.19.3", "1.19.2", "1.19.1", "1.19", "1.18.2", "1.18.1", "1.18",
            "1.17.1", "1.17", "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1", "1.16",
            "1.15.2", "1.15.1", "1.15", "1.14.4", "1.14.3", "1.14.2", "1.14.1", "1.14",
            "1.13.2", "1.13.1", "1.13", "1.12.2", "1.12.1", "1.12", "1.11.2", "1.11.1", "1.11",
            "1.10.2", "1.10.1", "1.10", "1.9.4", "1.9.3", "1.9.2", "1.9.1", "1.9",
            "1.8.9", "1.8.8", "1.8.7", "1.8.6", "1.8.5", "1.8.4", "1.8.3", "1.8.2", "1.8.1", "1.8"
        ]
        game_version_combo = ttk.Combobox(filter_frame, textvariable=self.game_version_var, values=game_versions, state="readonly", width=15)
        game_version_combo.pack(side="left", padx=5, pady=5)
        game_version_combo.bind("<<ComboboxSelected>>", lambda e: game_version_combo.selection_clear())

        ttk.Label(filter_frame, text="加载器:", width=10).pack(side="left", padx=5, pady=5)
        self.mod_loader_var = tk.StringVar(value="全部")
        mod_loader_combo = ttk.Combobox(filter_frame, textvariable=self.mod_loader_var, values=["全部", "fabric", "forge", "quilt"], state="readonly", width=15)
        mod_loader_combo.pack(side="left", padx=5, pady=5)
        mod_loader_combo.bind("<<ComboboxSelected>>", lambda e: mod_loader_combo.selection_clear())
        
        ttk.Button(filter_frame, text="搜索", command=self.start_mod_search, bootstyle="primary").pack(side="right", padx=5, pady=5)
        
        # 模组列表区域（左侧）
        results_frame = ttk.LabelFrame(main_container, text="模组列表")
        results_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10), padx=(0, 5))
        
        # 模组列表
        self.results_tree = ttk.Treeview(results_frame, columns=("title", "author", "downloads"), show="headings")
        self.results_tree.heading("title", text="模组名称")
        self.results_tree.heading("author", text="作者")
        self.results_tree.heading("downloads", text="下载量")
        self.results_tree.column("title", width=200)
        self.results_tree.column("author", width=100)
        self.results_tree.column("downloads", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.results_tree.pack(fill="both", expand=True)
        
        # 右侧按钮
        results_button_frame = ttk.Frame(results_frame)
        results_button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(results_button_frame, text="查看文件列表", command=self.view_files, bootstyle="outline").pack(side="left", padx=5)
        ttk.Button(results_button_frame, text="打开模组页面", command=self.open_mod_page, bootstyle="outline").pack(side="left", padx=5)
        ttk.Button(results_button_frame, text="下载并汉化", command=self.download_and_localize, bootstyle="success").pack(side="right", padx=5)
        
        # 文件列表区域（右侧）
        files_label_frame = ttk.LabelFrame(main_container, text="文件列表")
        files_label_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 10), padx=(5, 0))
        
        # 文件列表
        self.files_tree = ttk.Treeview(files_label_frame, columns=("name", "mod_version", "game_version", "size", "date"), show="headings")
        self.files_tree.heading("name", text="文件名")
        self.files_tree.heading("mod_version", text="模组版本")
        self.files_tree.heading("game_version", text="游戏版本")
        self.files_tree.heading("size", text="大小")
        self.files_tree.heading("date", text="上传日期")
        self.files_tree.column("name", width=200)
        self.files_tree.column("mod_version", width=80)
        self.files_tree.column("game_version", width=80)
        self.files_tree.column("size", width=80, anchor="center")
        self.files_tree.column("date", width=120)
        
        files_scrollbar = ttk.Scrollbar(files_label_frame, orient="vertical", command=self.files_tree.yview)
        self.files_tree.configure(yscroll=files_scrollbar.set)
        files_scrollbar.pack(side="right", fill="y")
        self.files_tree.pack(fill="both", expand=True)
        
        # 结果变量
        self.all_results = []
        self.current_mod = None
        self.current_files = []
    
    def start_mod_search(self):
        """启动搜索"""
        query = self.search_var.get().strip()
        if not query:
            messagebox.showinfo("提示", "请输入搜索关键词。")
            return
        
        platform = self.platform_var.get()
        game_version = self.game_version_var.get()
        mod_loader = self.mod_loader_var.get()
        
        # 清空结果
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # 更新状态
        self.status_var.set(f"正在搜索{platform}...")
        self.log_message(f"开始搜索: {query} (平台: {platform})", "INFO")
        
        # 在后台线程中执行搜索
        if platform == "Modrinth":
            thread = threading.Thread(target=self.search_modrinth, args=(query, game_version, mod_loader), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        else:
            thread = threading.Thread(target=self.search_curseforge, args=(query, game_version, mod_loader), daemon=True)
            self.add_background_thread(thread)
            thread.start()
    
    def search_modrinth(self, query, game_version=None, mod_loader=None):
        """执行Modrinth搜索请求"""
        try:
            import requests
            params = {
                "query": query,
                "limit": 50,
                "index": "relevance"
            }
            
            # 添加筛选参数
            if game_version and game_version != "全部":
                params["filters"] = f"versions={game_version}"
            if mod_loader and mod_loader != "全部":
                if "filters" in params:
                    params["filters"] += f",categories={mod_loader}"
                else:
                    params["filters"] = f"categories={mod_loader}"
            
            # 发送API请求
            response = requests.get("https://api.modrinth.com/v2/search", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # 处理结果
            results = []
            for hit in data.get("hits", []):
                mod_data = {
                    "project_id": hit.get("project_id"),
                    "title": hit.get("title"),
                    "author": hit.get("author"),
                    "description": hit.get("description"),
                    "downloads": hit.get("downloads", 0),
                    "follows": hit.get("follows", 0),
                    "license": hit.get("license"),
                    "slug": hit.get("slug"),
                    "versions": [],
                    "platform": "Modrinth"
                }
                results.append(mod_data)
            
            self.all_results = results
            self.root.after(0, self.update_results)
        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
    
    def search_curseforge(self, query, game_version=None, mod_loader=None):
        """执行CurseForge搜索请求"""
        try:
            import requests
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                self.root.after(0, lambda: messagebox.showwarning("警告", "请先在设置中配置CurseForge API密钥"))
                self.root.after(0, lambda: self.status_var.set("未配置API密钥"))
                return

            # 构建API请求URL
            base_urls = [
                "https://api.curseforge.com"
            ]
            
            # 构建查询参数
            import urllib.parse
            params = {
                "gameId": 432,
                "sortField": 2,
                "sortOrder": "desc",
                "pageSize": 40,
                "classId": 6  # Mod 分类
            }
            
            # 添加游戏版本筛选
            if game_version and game_version != "全部":
                params["gameVersion"] = game_version
            
            # 添加加载器筛选
            if mod_loader and mod_loader != "全部":
                mod_loader_map = {
                    "forge": 1,
                    "fabric": 4,
                    "quilt": 5
                }
                if mod_loader in mod_loader_map:
                    params["modLoaderType"] = mod_loader_map[mod_loader]
            
            # 添加搜索关键词
            if query:
                params["searchFilter"] = query
            
            # 发送API请求，尝试多个源
            response = None
            for base_url in base_urls:
                try:
                    address = f"{base_url}/v1/mods/search"
                    headers = {
                        "x-api-key": api_key,
                        "Content-Type": "application/json"
                    }
                    
                    # 打印请求信息以便调试
                    self.log_message(f"尝试CurseForge API请求: {address}?{urllib.parse.urlencode(params)}", "INFO")
                    
                    response = requests.get(address, params=params, headers=headers, timeout=15)
                    
                    # 打印响应状态码
                    self.log_message(f"CurseForge API响应状态: {response.status_code}", "INFO")
                    if response.status_code == 200:
                        break
                    else:
                        self.log_message(f"CurseForge API错误: {response.text}", "ERROR")
                except Exception as e:
                    self.log_message(f"尝试{base_url}失败: {str(e)}", "WARNING")
                    continue
            
            if not response or response.status_code != 200:
                raise Exception("无法连接到CurseForge API，请检查网络连接或稍后再试")
            
            data = response.json()
            
            # 处理结果
            results = []
            for mod in data.get("data", []):
                # 解析作者信息
                author_name = "未知"
                if mod.get("authors"):
                    author_name = mod.get("authors")[0].get("name", "未知")
                
                # 解析许可证信息
                license_name = None
                if mod.get("license"):
                    license_name = mod.get("license").get("name")
                
                # 构建模组数据
                mod_data = {
                    "project_id": mod.get("id"),
                    "title": mod.get("name"),
                    "author": author_name,
                    "description": mod.get("summary"),
                    "downloads": mod.get("downloadCount", 0),
                    "follows": mod.get("popularityScore", 0),
                    "license": license_name,
                    "slug": mod.get("slug"),
                    "versions": [],
                    "platform": "CurseForge"
                }
                results.append(mod_data)
            
            self.all_results = results
            self.root.after(0, self.update_results)
        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
    
    def update_results(self):
        """更新搜索结果"""
        # 清空结果
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # 添加结果
        for mod in self.all_results:
            self.results_tree.insert("", "end", values=(mod["title"], mod["author"], mod["downloads"]), tags=(mod["project_id"],))
        
        # 更新状态
        self.status_var.set(f"搜索完成，找到 {len(self.all_results)} 个结果")
        self.log_message(f"搜索完成，找到 {len(self.all_results)} 个结果", "SUCCESS")
    
    def view_files(self):
        """查看模组文件"""
        selected_items = self.results_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个模组。")
            return
        
        # 获取选中的模组
        item = selected_items[0]
        tags = self.results_tree.item(item, "tags")
        if not tags:
            messagebox.showinfo("错误", "无法获取模组ID。")
            return
        
        project_id = tags[0]
        mod = next((m for m in self.all_results if str(m["project_id"]) == project_id), None)
        if not mod:
            messagebox.showinfo("错误", "无法找到选中的模组。")
            return

        self.current_mod = mod
        self.status_var.set("正在获取文件列表...")
        self.log_message(f"获取模组文件: {mod['title']}", "INFO")
        
        # 在后台线程中获取文件
        if mod.get("platform") == "Modrinth":
            thread = threading.Thread(target=self.get_mod_files, args=(project_id,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        else:
            thread = threading.Thread(target=self.get_curseforge_files, args=(project_id,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
    
    def get_mod_files(self, project_id):
        """获取Modrinth模组文件"""
        try:
            import requests
            response = requests.get(f"https://api.modrinth.com/v2/project/{project_id}/version", timeout=30)
            response.raise_for_status()
            files = response.json()
            
            # 添加平台信息
            for file_info in files:
                file_info["platform"] = "Modrinth"
            
            self.current_files = files
            self.root.after(0, self.update_files_list)
        except Exception as e:
            error_msg = f"获取文件失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
    
    def get_curseforge_files(self, project_id):
        """获取CurseForge模组文件"""
        try:
            import requests
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                self.root.after(0, lambda: messagebox.showwarning("警告", "请先在设置中配置CurseForge API密钥"))
                self.root.after(0, lambda: self.status_var.set("未配置API密钥"))
                return

            # 构建API请求URL，尝试多个源
            base_urls = [
                "https://api.curseforge.com"
            ]
            
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # 发送API请求，尝试多个源
            response = None
            for base_url in base_urls:
                try:
                    address = f"{base_url}/v1/mods/{project_id}/files"
                    
                    # 打印请求信息以便调试
                    self.log_message(f"尝试CurseForge文件API请求: {address}", "INFO")
                    
                    response = requests.get(address, headers=headers, timeout=15)
                    
                    # 打印响应状态码
                    self.log_message(f"CurseForge文件API响应状态: {response.status_code}", "INFO")
                    if response.status_code == 200:
                        break
                    else:
                        self.log_message(f"CurseForge文件API错误: {response.text}", "ERROR")
                except Exception as e:
                    self.log_message(f"尝试{base_url}失败: {str(e)}", "WARNING")
                    continue
            
            if not response or response.status_code != 200:
                raise Exception("无法连接到CurseForge API，请检查网络连接或稍后再试")
            
            data = response.json()
            files = data.get("data", [])
            
            # 转换为与Modrinth类似的格式
            formatted_files = []
            for file_info in files:
                # 构建下载URL
                download_url = file_info.get("downloadUrl")
                if not download_url:
                    # 如果没有直接的下载URL，构建一个备用URL
                    file_id = file_info.get("id")
                    file_name = file_info.get("fileName")
                    if file_id and file_name:
                        download_url = f"https://edge.forgecdn.net/files/{str(file_id)[:4]}/{str(file_id)[4:]}/{file_name}"
                
                # 添加镜像源下载链接
                download_urls = [download_url]
                mirror_url = None
                if download_url:
                    # 添加镜像源
                    mirror_url = download_url.replace("https://edge.forgecdn.net", "https://cdn.mod.gg")
                    download_urls.append(mirror_url)
                
                # 构建文件信息
                formatted_file = {
                    "id": file_info.get("id"),
                    "version_number": file_info.get("displayName"),
                    "game_versions": file_info.get("gameVersions", []),
                    "date_published": file_info.get("fileDate"),
                    "files": [{
                        "primary": True,
                        "filename": file_info.get("fileName"),
                        "size": file_info.get("fileLength"),
                        "url": download_url,
                        "mirror_url": mirror_url
                    }],
                    "platform": "CurseForge"
                }
                formatted_files.append(formatted_file)
            
            # 按发布日期排序，最新的在前
            formatted_files.sort(key=lambda x: x.get("date_published", ""), reverse=True)
            
            self.current_files = formatted_files
            self.root.after(0, self.update_files_list)
        except Exception as e:
            error_msg = f"获取文件失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
    
    def update_files_list(self):
        """更新文件列表"""
        # 清空文件列表
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # 添加文件
        for file_info in self.current_files:
            file_name = ""
            file_size = 0
            for asset in file_info.get("files", []):
                if asset.get("primary"):
                    file_name = asset.get("filename")
                    file_size = asset.get("size", 0)
                    break
            
            mod_version = file_info.get("version_number", "")
            game_versions = file_info.get("game_versions", [])
            game_version = ", ".join(game_versions) if game_versions else ""
            date = file_info.get("date_published", "")
            
            # 格式化大小
            size_str = self._format_file_size(file_size)
            
            # 格式化日期
            date_str = date[:10] if date else ""
            
            self.files_tree.insert("", "end", values=(file_name, mod_version, game_version, size_str, date_str), tags=(file_info.get("id"),))
        
        # 更新状态
        self.status_var.set(f"获取完成，找到 {len(self.current_files)} 个文件")
        self.log_message(f"获取完成，找到 {len(self.current_files)} 个文件", "SUCCESS")
    
    def _format_file_size(self, size):
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    
    def open_mod_page(self):
        """打开模组页面"""
        selected_items = self.results_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个模组。")
            return
        
        # 获取选中的模组
        item = selected_items[0]
        tags = self.results_tree.item(item, "tags")
        if not tags:
            return
        
        project_id = tags[0]
        mod = next((m for m in self.all_results if str(m["project_id"]) == project_id), None)
        if not mod:
            return

        # 打开模组页面
        if mod.get("platform") == "Modrinth":
            url = f"https://modrinth.com/mod/{mod['slug']}"
        else:
            url = f"https://www.curseforge.com/minecraft/mc-mods/{mod['slug']}"
        webbrowser.open(url)
    
    def download_and_localize(self):
        """下载并本地化"""
        selected_items = self.files_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个文件。")
            return
        
        # 获取选中的文件
        item = selected_items[0]
        tags = self.files_tree.item(item, "tags")
        if not tags:
            return
        
        file_id = tags[0]
        file_info = next((f for f in self.current_files if str(f["id"]) == file_id), None)
        if not file_info:
            return
        
        # 获取下载URL
        download_url = None
        file_name = None
        for asset in file_info.get("files", []):
            if asset.get("primary"):
                download_url = asset.get("url")
                file_name = asset.get("filename")
                break
        
        if not download_url:
            messagebox.showinfo("错误", "无法获取下载链接。")
            return
        
        # 更新状态
        self.status_var.set("正在下载文件...")
        self.log_message(f"开始下载: {file_name}", "INFO")
        
        # 在后台线程中下载文件
        thread = threading.Thread(target=self.download_file, args=(download_url, file_name, file_info), daemon=True)
        self.add_background_thread(thread)
        thread.start()
    
    def download_file(self, url, file_name, file_info):
        """下载文件"""
        try:
            import requests
            import os
            from pathlib import Path
            
            # 获取JAR下载目录和汉化包输出目录
            jar_dir = self.project_info.get('jar_dir')
            output_dir = self.project_info.get('output_dir')
            if not jar_dir:
                error_msg = "JAR下载目录未设置"
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
                self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
                self.root.after(0, lambda: self.status_var.set("错误"))
                return

            # 确保JAR下载目录存在
            jar_path = Path(jar_dir)
            jar_path.mkdir(parents=True, exist_ok=True)

            # 下载文件到JAR目录
            file_path = jar_path / file_name
            self.log_message(f"正在下载到: {file_path}", "INFO")
            
            # 准备下载链接列表
            download_urls = [url]
            
            # 检查是否有镜像链接
            if file_info and file_info.get('files'):
                mirror_url = file_info['files'][0].get('mirror_url')
                if mirror_url:
                    download_urls.append(mirror_url)
            
            # 尝试从多个链接下载
            success = False
            for download_url in download_urls:
                try:
                    self.log_message(f"尝试从: {download_url} 下载", "INFO")
                    response = requests.get(download_url, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    # 获取文件大小
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    # 写入文件
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                
                                # 更新下载进度
                                if total_size > 0:
                                    progress = int((downloaded_size / total_size) * 100)
                                    self.root.after(0, lambda p=progress: self.status_var.set(f"下载中... {p}%"))
                    
                    # 下载成功
                    success = True
                    break
                except Exception as e:
                    self.log_message(f"从 {download_url} 下载失败: {str(e)}", "WARNING")
                    continue
            
            if not success:
                raise Exception("所有下载链接都失败了，请稍后再试")
            
            # 下载完成
            self.root.after(0, lambda: self.status_var.set("下载完成，准备汉化流程..."))
            self.root.after(0, lambda: self.log_message(f"下载完成: {file_name}", "SUCCESS"))
            
            # 开始汉化流程
            self.root.after(0, lambda: self.start_localization_process(file_path, file_info))
        except requests.exceptions.RequestException as e:
            error_msg = f"下载失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
        except Exception as e:
            error_msg = f"发生错误: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
    
    def start_localization_process(self, file_path, file_info=None):
        """开始汉化流程"""
        self.status_var.set("准备汉化流程...")
        
        # 构建项目名称
        project_name = f"汉化 - {file_path.stem}"
        if file_info:
            version = file_info.get('version_number', '')
            if version:
                project_name = f"汉化 - {file_path.stem} (v{version})"
        
        self.log_message(f"开始汉化流程: {project_name}")
        
        # 创建临时mods目录
        import tempfile
        from pathlib import Path
        
        temp_mods_dir = tempfile.mkdtemp()
        
        # 将下载的文件复制到临时mods目录
        import shutil
        mod_file_path = Path(temp_mods_dir) / file_path.name
        shutil.copy2(file_path, mod_file_path)
        
        # 更新项目信息
        self.project_type = "mod"
        self.project_name = project_name
        self.project_info = {
            "mods_dir": temp_mods_dir,
            "output_dir": self.project_info.get('output_dir')
        }
        
        # 先保存配置（不包含临时目录），然后再设置运行时需要的 mods_dir
        from utils import config_manager
        config = config_manager.load_config()
        config['output_dir'] = self.project_info.get('output_dir')
        config_manager.save_config(config)  # 保存时不包含 temp_mods_dir
        config['mods_dir'] = temp_mods_dir  # 仅在运行时使用，不保存
        
        # 开始汉化流程
        self._prepare_ui_for_workflow(1)
        from core.orchestrator import Orchestrator
        self.orchestrator = Orchestrator(
            settings=config,
            update_progress=self.update_progress,
            root_window=self.root,
            log_callback=self.log_message
        )
        # 传递停止事件
        self.orchestrator.stop_event = self.stop_event
        
        # 保存_launch_workbench方法的引用
        self.orchestrator._launch_workbench = lambda data: self._show_workbench_view(
            data, 
            self.orchestrator.namespace_formats, 
            self.orchestrator.raw_english_files, 
            config, 
            None, 
            "完成并生成资源包",
            save_session_after=True
        )
        
        # 启动翻译流程
        thread = threading.Thread(target=self.orchestrator.run_translation_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _load_project(self):
        path = filedialog.askopenfilename(
            title="选择一个项目存档文件",
            filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path: return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            required_keys = ['workbench_data', 'namespace_formats', 'raw_english_files']
            if not all(k in save_data for k in required_keys):
                raise ValueError("存档文件格式不正确或已损坏。")

            self.project_type = "mod"
            self.project_name = Path(path).stem
            self.log_message(f"成功加载项目: {Path(path).name}", "SUCCESS")
            self.log_message("所有个人设置将保持不变，使用您本地的配置。", "INFO")
            self.main_window.update_tab_title(self.tab_id, self.project_name)

            self._prepare_ui_for_workflow(1)
            settings = config_manager.load_config()
            self.orchestrator = Orchestrator(
                settings, self.update_progress, self.root,
                log_callback=self.log_message,
                save_data=save_data, project_path=path
            )
            # 传递停止事件
            self.orchestrator.stop_event = self.stop_event

            def launch_loaded_workbench(data):
                self._show_workbench_view(data, self.orchestrator.namespace_formats, self.orchestrator.raw_english_files, settings, path, "完成并生成资源包", save_session_after=True)
            self.orchestrator._launch_workbench = launch_loaded_workbench
            
            thread = threading.Thread(target=self.orchestrator.run_workflow, daemon=True)
            self.add_background_thread(thread)
            thread.start()

        except Exception as e:
            ui_utils.show_error("加载失败", f"无法加载或解析项目文件：\n{e}", parent=self.root)
            logging.error(f"加载项目文件 '{path}' 失败: {e}", exc_info=True)

    def _prepare_ui_for_workflow(self, stage: int):
        if self.workbench_instance:
            self.workbench_instance.pack_forget()
        else:
            self._clear_content_frame()
    
        if hasattr(self, 'loading_frame') and self.loading_frame and self.loading_frame.winfo_exists():
            self.loading_frame.destroy()
            
        self.loading_frame = ttk.Frame(self.content_frame)
        self.loading_frame.pack(expand=True)
        ttk.Label(self.loading_frame, text="正在处理中，请稍候...", font="-size 14").pack(pady=10)
        self.root.update_idletasks()
        
        # 移除自动展开日志的功能，保留日志清除功能
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        
        if stage == 1: self.status_var.set("准备开始处理翻译...")
        else: self.status_var.set("准备开始生成...")
        self.progress_var.set(0)

    def _reset_ui_after_workflow(self, final_status: str):
        if hasattr(self, 'loading_frame') and self.loading_frame and self.loading_frame.winfo_exists():
            self.loading_frame.destroy()
            self.loading_frame = None
    
        if final_status == "success":
            self.log_message("流程执行完毕！", "SUCCESS")
            self.progress_bar.config(bootstyle="success")
        elif final_status == "cancelled":
            self.log_message("流程已被用户取消", "WARNING")
            self.progress_bar.config(bootstyle="secondary")
        else:
            self.log_message(f"流程因错误中断", "CRITICAL")
            self.progress_bar.config(bootstyle="danger")
    
        if self.workbench_instance:
            self.workbench_instance.pack(fill="both", expand=True)
        else:
            self._show_welcome_view()

    def _continue_to_build_phase(self):
        if not self.orchestrator:
            ui_utils.show_error("内部错误", "Orchestrator实例丢失，无法继续生成。", parent=self.root)
            self._reset_ui_after_workflow("error")
            return

        config = config_manager.load_config()
        presets = config.get("pack_settings_presets", {})
        if not presets:
            ui_utils.show_error("操作失败", "没有可用的资源包生成预案。\n请在“配置”菜单中打开设置面板创建一个预案。", parent=self.root)
            self._reset_ui_after_workflow("cancelled")
            return

        dialog = PackPresetDialog(self.root, presets)
        chosen_preset_name = dialog.result

        if chosen_preset_name is None:
            self.log_message("生成操作已取消", "INFO")
            self._reset_ui_after_workflow("cancelled")
            return

        final_pack_settings = presets.get(chosen_preset_name, {}).copy()
        final_pack_settings['preset_name'] = chosen_preset_name
        final_pack_settings['pack_as_zip'] = config.get("pack_as_zip", False)

        self._prepare_ui_for_workflow(stage=2)
        thread = threading.Thread(target=self.orchestrator.run_build_phase, args=(final_pack_settings,), daemon=True)
        self.add_background_thread(thread)
        thread.start()

class MainWindow:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title(f"Minecraft 整合包汉化工坊 Pro - v{__version__}")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        self.settings_window = None
        self.find_replace_window = None
        self.project_tabs = {}
        self.close_tab_map = {}
        self.tab_counter = 0
        # 标签拖拽相关属性
        self.dragged_tab_index = None
        self.dragged_tab_id = None
        self.dragged_tab_pos = None

        self._create_menu()
        self._create_widgets()
        
        # 在创建完所有组件后再更新菜单状态
        self.update_menu_state()

        from utils.logger_setup import setup_logging
        setup_logging(self._dispatch_log_to_active_tab)

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind_all("<Control-f>", self._open_find_replace)
        self.check_initial_config()
        
        self.root.bind("<Map>", self._apply_initial_theme, add="+")
        
        self._load_session_on_startup()

    def _apply_initial_theme(self, event=None):
        set_title_bar_theme(self.root, self.root.style)
        self.root.unbind("<Map>")

    def _on_closing(self):
        self._save_current_session()
        if self.find_replace_window and self.find_replace_window.winfo_exists():
            self.find_replace_window.destroy()
        self.root.destroy()

    def _save_current_session(self):
        active_tabs = list(self.project_tabs.values())
        if active_tabs:
            session_manager.save_session(active_tabs)
        else:
            session_manager.clear_session()

    def _load_session_on_startup(self):
        # 先加载索引文件，获取所有标签页的信息
        index_data = session_manager.load_index_only()
        if index_data and index_data.get("tabs"):
            tab_count = len(index_data["tabs"])
            self._dispatch_log_to_active_tab(f"检测到 {tab_count} 个未关闭的标签页，正在恢复...", "INFO")
            
            # 移除初始标签页
            initial_tab_id = list(self.project_tabs.keys())[0]
            project_tab_ids = [tid for tid in self.notebook.tabs() if tid in self.project_tabs]
            try:
                closed_project_index = project_tab_ids.index(initial_tab_id)
            except ValueError:
                closed_project_index = 0
            
            # 直接移除标签页，不调用 _save_current_session()
            self.notebook.forget(initial_tab_id)
            del self.project_tabs[initial_tab_id]
            
            # 移除对应的关闭标签页
            close_tab_id = next((cid for cid, tid in self.close_tab_map.items() if tid == initial_tab_id), None)
            if close_tab_id:
                self.notebook.forget(close_tab_id)
                del self.close_tab_map[close_tab_id]
            
            # 只根据索引文件创建所有标签页，不加载任何内容
            for tab_uuid, tab_name in index_data["tabs"].items():
                new_tab = self._add_new_tab(select_tab=False)
                # 设置标签页名称
                self.update_tab_title(new_tab.tab_id, tab_name)
                # 保存标签页UUID，以便后续切换时加载
                new_tab.tab_uuid = tab_uuid
            
            self._dispatch_log_to_active_tab(f"已创建 {tab_count} 个标签页，未加载任何标签页内容", "INFO")
        else:
            self._dispatch_log_to_active_tab("欢迎使用整合包汉化工坊！", "INFO")

    def _create_menu(self):
        """创建Windows原生菜单栏"""
        current_theme = self.root.style.theme_use()
        is_dark = current_theme == "darkly"
        
        # 直接使用主题的具体颜色值
        if is_dark:
            # 暗黑模式颜色
            menu_bg = "#1a1a1a"
            menu_fg = "#ffffff"
            active_bg = "#404040"
            active_fg = "#ffffff"
        else:
            # 亮色模式颜色
            menu_bg = "#f0f0f0"
            menu_fg = "#000000"
            active_bg = "#d0d0d0"
            active_fg = "#000000"
        
        # 创建主菜单，并直接设置颜色
        self.menu_bar = Menu(self.root, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.root.config(menu=self.menu_bar)
        
        # 文件菜单，并直接设置颜色
        self.file_menu = Menu(self.menu_bar, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.menu_bar.add_cascade(label="文件", menu=self.file_menu)
        self.file_menu.add_command(label="新建项目", command=self._add_new_tab)
        self.file_menu.add_command(label="返回欢迎页", command=self._reset_active_tab)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="关闭标签页", command=lambda: self._close_tab_by_id(self.notebook.select()))
        
        # 编辑菜单，并直接设置颜色
        self.edit_menu = Menu(self.menu_bar, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.menu_bar.add_cascade(label="编辑", menu=self.edit_menu)
        self.edit_menu.add_command(label="撤销 (Ctrl+Z)", command=lambda: self._call_workbench_method('undo'))
        self.edit_menu.add_command(label="重做 (Ctrl+Y)", command=lambda: self._call_workbench_method('redo'))
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="查找和替换 (Ctrl+F)", command=self._open_find_replace)

        # 工具菜单，并直接设置颜色
        self.tools_menu = Menu(self.menu_bar, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.menu_bar.add_cascade(label="工具", menu=self.tools_menu)
        self.tools_menu.add_command(label="查询词典", command=lambda: self._call_workbench_method('_open_dict_search'))
        self.tools_menu.add_separator()
        self.tools_menu.add_command(label="添加到个人词典", command=lambda: self._call_workbench_method('_add_to_user_dictionary'))
        
        # 全局工具菜单已整合到工具菜单中
        from gui.user_dictionary_editor import UserDictionaryEditor
        # 在工具菜单中添加编辑个人词典选项
        self.tools_menu.add_command(label="管理个人词典", command=lambda: UserDictionaryEditor(self.root))
        
        # 视图菜单已移除，功能已整合到底栏

        # 设置菜单，并直接设置颜色
        self.settings_menu = Menu(self.menu_bar, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.menu_bar.add_cascade(label="设置", menu=self.settings_menu)
        self.settings_menu.add_command(label="打开设置面板", command=self.open_settings_window)
        
        # 帮助菜单，并直接设置颜色
        self.help_menu = Menu(self.menu_bar, tearoff=0, 
                            bg=menu_bg, fg=menu_fg,
                            activebackground=active_bg, activeforeground=active_fg)
        self.menu_bar.add_cascade(label="帮助", menu=self.help_menu)
        self.help_menu.add_command(label="项目主页", command=lambda: webbrowser.open("https://github.com/blibilijojo/Modpack-Localizer"))
        self.help_menu.add_command(label="检查更新", command=lambda: self.start_update_check(user_initiated=True))
        self.help_menu.add_separator()
        self.help_menu.add_command(label="关于", command=self._show_about)
    
    def _update_menu_theme(self):
        """更新菜单主题以适配暗黑模式"""
        # 重新创建整个菜单，以便应用新的主题颜色
        self._create_menu()
        # 更新菜单状态
        self.update_menu_state()
        # 刷新窗口以确保变更生效
        self.root.update_idletasks()
    
    def update_menu_state(self, event=None):
        """更新菜单状态"""
        current_tab = self._get_current_tab()
        
        if current_tab:
            # 检查是否需要加载标签页状态
            if not current_tab.workbench_instance and not current_tab._is_fully_loaded:
                # 如果有 _restored_state_data，直接加载
                if current_tab._restored_state_data:
                    current_tab._lazy_load_workbench()
                # 如果没有 _restored_state_data 但有 tab_uuid，加载状态
                elif current_tab.tab_uuid:
                    tab_state = session_manager.load_tab_state(current_tab.tab_uuid)
                    if tab_state:
                        current_tab.restore_from_state(tab_state)
        
        state = "normal" if current_tab and current_tab.workbench_instance else "disabled"
        
        # 为编辑菜单的每个命令设置状态
        self.edit_menu.entryconfig(0, state=state)  # 撤销
        self.edit_menu.entryconfig(1, state=state)  # 重做
        self.edit_menu.entryconfig(3, state=state)  # 查找和替换
        
        # 为工具菜单的每个命令设置状态
        self.tools_menu.entryconfig(0, state=state)  # 查询词典
        self.tools_menu.entryconfig(2, state=state)  # 存入个人词典
        self.tools_menu.entryconfig(3, state="normal")  # 编辑个人词典 - 始终可用
        
        if self.find_replace_window and self.find_replace_window.winfo_exists():
            self.find_replace_window.lift()

    def start_update_check(self, user_initiated=False):
        if not getattr(sys, 'frozen', False):
            if user_initiated:
                messagebox.showinfo("提示", "此功能仅在打包后的 .exe 程序中可用。")
            return

        logging.info("准备启动后台更新检查线程...")
        update_thread = threading.Thread(target=self._check_for_updates_thread, args=(user_initiated,), daemon=True)
        update_thread.start()

    def _check_for_updates_thread(self, user_initiated):
        import utils.update_checker as update_checker
        from _version import __version__
        
        update_info = update_checker.check_for_updates(__version__)
        if update_info:
            self.root.after(0, self._show_update_dialog, update_info)
        elif user_initiated:
            self.root.after(0, lambda: messagebox.showinfo("检查更新", "恭喜，您使用的已是最新版本！"))

    def _show_update_dialog(self, update_info: dict):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"发现新版本: {update_info['version']}")
        dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)

        message_frame = ttk.Frame(dialog, padding=20)
        message_frame.pack(fill="x")
        
        message_text = (f"一个新版本 ({update_info['version']}) 可用！\n\n" "是否立即下载并安装更新？")
        ttk.Label(message_frame, text=message_text, justify="left").pack(anchor="w")

        progress_frame = ttk.Frame(dialog, padding=(20, 10))
        progress_frame.pack(fill="x")
        self.status_label = ttk.Label(progress_frame, text="准备就绪")
        self.status_label.pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress_frame, length=300, mode='determinate')
        self.progress_bar.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill="x")
        
        def on_update():
            self.update_btn.config(state="disabled"); self.later_btn.config(state="disabled")
            threading.Thread(target=self._start_update_process, args=(update_info,), daemon=True).start()

        self.update_btn = ttk.Button(btn_frame, text="立即更新", command=on_update, bootstyle="success")
        self.update_btn.pack(side="right", padx=5)
        self.later_btn = ttk.Button(btn_frame, text="稍后提醒", command=dialog.destroy)
        self.later_btn.pack(side="right")
        
    def _update_progress_ui(self, status, percentage, speed):
        self.status_label.config(text=f"{status}... {int(percentage)}% ({speed})")
        self.progress_bar['value'] = percentage

    def _start_update_process(self, update_info: dict):
        import sys
        import subprocess
        import os
        from pathlib import Path
        import utils.update_checker as update_checker
        
        current_exe_path = Path(sys.executable)
        exe_dir = current_exe_path.parent
        
        new_exe_temp_path = current_exe_path.with_suffix(current_exe_path.suffix + ".new")
        old_exe_backup_path = current_exe_path.with_suffix(current_exe_path.suffix + ".old")

        # 1. 下载新版本
        download_ok = update_checker.download_update(update_info["asset_url"], new_exe_temp_path,
                                                     lambda s, p, sp: self.root.after(0, self._update_progress_ui, s, p, sp))
        if not download_ok:
            self.root.after(0, lambda: messagebox.showerror("更新失败", "下载新版本失败，请检查网络或稍后重试。", parent=self.root))
            self.root.after(0, self.later_btn.master.master.destroy)
            return

        # 2. 定位并释放内置的 updater.exe
        try:
            # sys._MEIPASS 只有在打包后的exe中才存在
            updater_path = Path(sys._MEIPASS) / "updater.exe"
            if not updater_path.exists():
                 raise FileNotFoundError("关键更新组件 'updater.exe' 未被打包进主程序！")
        except AttributeError:
            # 如果是直接运行 .py 文件进行开发调试，则无法使用此功能
            self.root.after(0, lambda: messagebox.showerror("开发模式", "更新功能只能在打包后的 .exe 程序中使用。"))
            return
        except FileNotFoundError as e:
            self.root.after(0, lambda: messagebox.showerror("更新错误", str(e)))
            return

        # 3. 准备启动更新器所需的所有命令行参数
        pid = os.getpid()
        command = [
            str(updater_path),
            str(pid),                # 参数1: 主程序的进程ID
            str(current_exe_path),   # 参数2: 当前(旧版)exe的完整路径
            str(new_exe_temp_path),  # 参数3: 已下载的新版exe的完整路径
            str(old_exe_backup_path) # 参数4: 用于备份旧版的路径
        ]

        # 4. 启动 updater.exe 作为一个完全分离的、独立的进程
        subprocess.Popen(command, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)

        # 5. 主程序安排自己退出，将控制权完全交给更新器
        self.root.after(100, self.root.destroy)

    def _show_about(self):
        """显示关于对话框"""
        from _version import __version__
        about_text = f"Minecraft 整合包汉化工坊 Pro\n\n版本: v{__version__}\n\nGitHub: https://github.com/blibilijojo/Modpack-Localizer\n\n用于快速汉化 Minecraft 整合包和模组的工具。"
        messagebox.showinfo("关于", about_text, parent=self.root)

    def _toggle_theme(self):
        current_theme = self.root.style.theme_use()
        new_theme = "darkly" if current_theme == "litera" else "litera"
        self.root.style.theme_use(new_theme)
        
        config = config_manager.load_config()
        config["theme"] = new_theme
        config_manager.save_config(config)
        
        for tab in self.project_tabs.values():
            tab._update_log_tag_colors()
            if tab.workbench_instance:
                tab.workbench_instance._update_theme_colors()

        self.root.update_idletasks()
        
        # 关键修复：在Windows平台上，我们需要重新创建窗口来确保菜单栏颜色正确
        # 首先保存当前窗口状态
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        # 设置标题栏主题
        set_title_bar_theme(self.root, self.root.style)
        if self.settings_window and self.settings_window.winfo_exists():
            set_title_bar_theme(self.settings_window, self.root.style)
        if self.find_replace_window and self.find_replace_window.winfo_exists():
            set_title_bar_theme(self.find_replace_window, self.root.style)
        
        # 隐藏并重新显示窗口，这会触发Windows重新绘制窗口，包括菜单栏
        self.root.withdraw()
        self.root.deiconify()
        
        # 恢复窗口位置和大小
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # 更新菜单主题
        self._update_menu_theme()

    def _call_workbench_method(self, method_name):
        current_tab = self._get_current_tab()
        if current_tab and current_tab.workbench_instance:
            method = getattr(current_tab.workbench_instance, method_name, None)
            if callable(method):
                method()

    def open_settings_window(self):
        # 从当前活动的ProjectTab实例中获取workbench_instance
        workbench_instance = None
        current_tab_id = self.notebook.select()
        if current_tab_id and current_tab_id in self.project_tabs:
            project_tab = self.project_tabs[current_tab_id]
            if hasattr(project_tab, 'workbench_instance'):
                workbench_instance = project_tab.workbench_instance
        
        if self.settings_window and self.settings_window.winfo_exists():
            # 如果窗口已存在，更新workbench_instance
            self.settings_window.workbench_instance = workbench_instance
            self.settings_window.lift()
            self.settings_window.focus_set()
            return

        self.settings_window = SettingsWindow(self.root, workbench_instance=workbench_instance)
        self.settings_window.transient(self.root)

    def _create_widgets(self):
        self.notebook = ttk.Notebook(self.root, padding=(5, 5, 0, 0))
        self.notebook.pack(fill="both", expand=True)

        self.notebook.bind("<ButtonPress-1>", self._on_tab_click)
        self.notebook.bind("<<NotebookTabChanged>>", self.update_menu_state)
        
        # 拖拽相关事件绑定
        self.notebook.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        self.notebook.bind("<B1-Motion>", self._on_drag_motion)
        self.notebook.bind("<ButtonRelease-1>", self._on_drag_end)

        self.add_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.add_tab_frame, text='+')
        self.notebook.tab(self.add_tab_frame, padding=[4, 1, 4, 1])

        self._add_new_tab()

    def _on_tab_click(self, event):
        try:
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
            clicked_tab_id = self.notebook.tabs()[clicked_tab_index]
        except tk.TclError:
            # 当鼠标在按钮边缘时，index调用可能失败，此时直接返回break阻止后续处理
            return "break"

        add_tab_id = self.notebook.tabs()[-1]

        if clicked_tab_id == add_tab_id:
            self.notebook.after(10, self._add_new_tab)
            return "break"

        if clicked_tab_id in self.close_tab_map:
            project_tab_to_close = self.close_tab_map[clicked_tab_id]
            self.notebook.after(10, lambda: self._close_tab_by_id(project_tab_to_close))
            return "break"
        
        # 如果点击的是项目标签，不返回break，允许事件继续传播到拖拽处理
        if clicked_tab_id in self.project_tabs:
            return

    def _add_new_tab(self, select_tab=True):
        self.tab_counter += 1
        
        project_tab = ProjectTab(self.notebook, self.root, self)
        
        insert_pos = len(self.notebook.tabs()) - 1
        self.notebook.insert(insert_pos, project_tab.frame, text="新项目")
        
        tab_id = self.notebook.tabs()[insert_pos]
        project_tab.tab_id = tab_id
        self.project_tabs[tab_id] = project_tab
        
        close_tab_frame = ttk.Frame(self.notebook)
        self.notebook.insert(insert_pos + 1, close_tab_frame, text='x')
        close_tab_id = self.notebook.tabs()[insert_pos + 1]
        self.notebook.tab(close_tab_id, padding=[4, 1, 4, 1])
        self.close_tab_map[close_tab_id] = tab_id

        if select_tab:
            self.notebook.select(tab_id)
            # 确保标签页内容正确显示
            self.notebook.update_idletasks()
            project_tab.frame.update_idletasks()
            if project_tab.content_frame:
                project_tab.content_frame.update_idletasks()
            self.update_menu_state()
        return project_tab
    
    def _reset_active_tab(self):
        current_tab = self._get_current_tab()
        if current_tab:
            current_tab._show_welcome_view()

    def _get_current_tab(self):
        try:
            selected_id = self.notebook.select()
            return self.project_tabs.get(selected_id)
        except (tk.TclError, IndexError):
            return None

    def _dispatch_log_to_active_tab(self, message, level):
        active_tab = self._get_current_tab()
        if active_tab:
            active_tab.log_message(message, level)
        elif not self.project_tabs:
            self.root.after(50, lambda: self._dispatch_log_to_active_tab(message, level))
        else:
            try:
                first_tab_id = list(self.project_tabs.keys())[0]
                self.project_tabs[first_tab_id].log_message(message, level)
            except (IndexError, KeyError):
                 pass

    def _close_tab_by_id(self, project_tab_id_to_close, force=False):
        if not project_tab_id_to_close or project_tab_id_to_close not in self.project_tabs:
            return

        tab_to_close = self.project_tabs[project_tab_id_to_close]

        if len(self.project_tabs) <= 1 and not force:
            if tab_to_close.workbench_instance:
                tab_to_close.workbench_instance._on_close_request(force_close=False, on_confirm=self._reset_active_tab)
            else:
                self._reset_active_tab()
            return

        project_tab_ids = [tid for tid in self.notebook.tabs() if tid in self.project_tabs]
        
        try:
            closed_project_index = project_tab_ids.index(project_tab_id_to_close)
        except ValueError:
            return

        if closed_project_index == len(project_tab_ids) - 1:
            target_project_index = closed_project_index - 1
        else:
            target_project_index = closed_project_index
        
        if target_project_index >= 0:
            tab_id_to_select = project_tab_ids[target_project_index]
        else:
            tab_id_to_select = None

        # 停止标签页的所有后台线程
        tab_to_close.stop_all_threads()
        
        if tab_to_close.workbench_instance:
            tab_to_close.workbench_instance._on_close_request(force_close=True)
        
        close_tab_id_to_remove = None
        for close_id, proj_id in self.close_tab_map.items():
            if proj_id == project_tab_id_to_close:
                close_tab_id_to_remove = close_id
                break
        
        if close_tab_id_to_remove:
            self.notebook.forget(close_tab_id_to_remove)
            del self.close_tab_map[close_tab_id_to_remove]
        
        self.notebook.forget(project_tab_id_to_close)
        del self.project_tabs[project_tab_id_to_close]
        
        if tab_id_to_select:
            try:
                self.notebook.select(tab_id_to_select)
            except tk.TclError:
                # 如果要选择的标签页不存在，跳过选择操作
                pass
        
        if not self.project_tabs and not force:
             self._add_new_tab()

        self.update_menu_state()
        self._save_current_session()
        
    def _open_github_download_ui(self):
        """打开GitHub下载UI"""
        # 获取当前选中的标签页
        current_tab_id = self.notebook.select()
        if current_tab_id in self.project_tabs:
            project_tab = self.project_tabs[current_tab_id]
            
            # 清空内容框架
            project_tab._clear_content_frame()
            
            # 加载GitHub配置
            from utils import config_manager
            config = config_manager.load_config()
            # 正确获取GitHub配置，使用github_repo和github_token键
            github_config = {
                'repo': config.get('github_repo', ''),
                'token': config.get('github_token', '')
            }
            
            # 导入GitHubDownloadUI
            from gui.github_download_ui import GitHubDownloadUI
            
            # 创建GitHubDownloadUI实例，使用标签页的内容框架作为父容器
            download_ui = GitHubDownloadUI(project_tab.content_frame, self, github_config)
            download_ui.pack(fill="both", expand=True)
            
            # 更新标签页标题
            self.update_tab_title(current_tab_id, "从GitHub下载")
        
    def _on_drag_start(self, event):
        """开始拖拽标签"""
        try:
            # 获取点击的标签索引
            tab_index = self.notebook.index(f"@{event.x},{event.y}")
            all_tabs = self.notebook.tabs()
            
            # 确保不是最后一个标签(+)和关闭标签
            if tab_index == len(all_tabs) - 1:
                self.dragged_tab_index = None
                self.dragged_tab_id = None
                return
            
            clicked_tab_id = all_tabs[tab_index]
            
            # 只有项目标签可以拖拽
            if clicked_tab_id in self.project_tabs:
                self.dragged_tab_index = tab_index
                self.dragged_tab_id = clicked_tab_id
                self.dragged_tab_pos = (event.x, event.y)
            else:
                self.dragged_tab_index = None
                self.dragged_tab_id = None
        except tk.TclError:
            self.dragged_tab_index = None
            self.dragged_tab_id = None
    
    def _on_drag_motion(self, event):
        """拖拽标签过程"""
        if self.dragged_tab_index is None or self.dragged_tab_id is None:
            return
        
        try:
            # 获取当前鼠标位置对应的标签索引
            target_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        
        all_tabs = self.notebook.tabs()
        
        # 不能拖到最后一个标签(+)
        if target_index == len(all_tabs) - 1:
            return
        
        # 不能拖到关闭标签上
        target_tab_id = all_tabs[target_index]
        if target_tab_id in self.close_tab_map:
            return
        
        # 如果拖到了新的位置，立即重新排列
        if target_index != self.dragged_tab_index:
            self._reorder_tabs(target_index)
    
    def _on_drag_end(self, event):
        """结束拖拽"""
        self.dragged_tab_index = None
        self.dragged_tab_id = None
        self.dragged_tab_pos = None
        # 移除标签页切换时的缓存保存
    
    def _reorder_tabs(self, target_index):
        """重新排列标签，使用Tcl命令直接操作标签位置，避免不必要的刷新"""
        if self.dragged_tab_id is None:
            return
        
        # 获取所有标签的ID列表
        all_tabs = self.notebook.tabs()
        
        # 检查拖拽的标签是否仍在notebook中
        if self.dragged_tab_id not in all_tabs:
            return
        
        # 获取关闭标签
        close_tab_id = None
        for cid, pid in self.close_tab_map.items():
            if pid == self.dragged_tab_id:
                close_tab_id = cid
                break
        
        if close_tab_id is None:
            return
        
        # 检查关闭标签是否仍在notebook中
        if close_tab_id not in all_tabs:
            return
        
        # 获取当前拖拽标签和关闭标签的索引
        dragged_idx = all_tabs.index(self.dragged_tab_id)
        close_idx = all_tabs.index(close_tab_id)
        
        # 确保关闭标签在拖拽标签后面
        assert close_idx == dragged_idx + 1, "关闭标签必须紧跟在项目标签后面"
        
        # 计算新的位置
        # 目标位置不能是最后一个标签(+)
        if target_index >= len(all_tabs) - 1:
            target_index = len(all_tabs) - 2
        
        # 如果目标位置等于当前位置，不需要移动
        if target_index == dragged_idx:
            return
        
        # 构建新的标签顺序
        new_order = list(all_tabs)
        
        # 移除当前位置的项目标签和关闭标签
        del new_order[close_idx]
        del new_order[dragged_idx]
        
        # 在新位置插入项目标签和关闭标签
        new_order.insert(target_index, self.dragged_tab_id)
        new_order.insert(target_index + 1, close_tab_id)
        
        # 使用Tcl命令重新排列标签，避免不必要的刷新
        # 获取notebook的Tcl命令前缀
        notebook_tcl = self.notebook._w
        
        # 保存当前选中的标签
        current_selected = self.notebook.select()
        
        # 遍历新顺序，重新排列标签
        for i, tab_id in enumerate(new_order):
            # 使用Tcl命令直接设置标签位置
            self.notebook.tk.call(notebook_tcl, "insert", i, tab_id)
        
        # 恢复选中的标签
        if current_selected in new_order:
            self.notebook.select(current_selected)
        
        # 更新拖拽标签的索引
        self.dragged_tab_index = target_index

    def update_tab_title(self, tab_id, new_title):
        if tab_id in self.project_tabs and new_title:
            try:
                clean_title = re.sub(r'[\\/*?:"<>|]', "", new_title)
                current_tab = self.project_tabs.get(tab_id)
                if current_tab:
                    current_tab.project_name = clean_title

                display_title = clean_title if len(clean_title) <= 20 else clean_title[:17] + "..."
                self.notebook.tab(tab_id, text=display_title)
            except tk.TclError:
                pass

    def check_initial_config(self):
        config = config_manager.load_config()
        api_services = config.get('api_services', [])
        has_valid_keys = False
        for service in api_services:
            keys = service.get('keys', [])
            if keys and any(keys):
                has_valid_keys = True
                break
        if not has_valid_keys:
            self.root.after(100, lambda: self._dispatch_log_to_active_tab("提醒: AI API密钥为空，请在""配置""菜单中打开设置面板进行配置，否则AI翻译功能将不可用。", "WARNING"))
    
    def _open_find_replace(self, event=None):
        active_tab = self._get_current_tab()
        if not active_tab or not active_tab.workbench_instance:
            self.root.bell()
            return
            
        if self.find_replace_window and self.find_replace_window.winfo_exists():
            self.find_replace_window.lift()
            self.find_replace_window.focus_set()
        else:
            config = config_manager.load_config()
            initial_settings = config.get("find_replace_settings", {})
            self.find_replace_window = FindReplaceDialog(self.root, self._handle_find_replace_action, initial_settings)

    def _handle_find_replace_action(self, action, params):
        config = config_manager.load_config()
        config["find_replace_settings"] = params
        config_manager.save_config(config)

        if action == "close":
            self.find_replace_window = None
            return

        active_tab = self._get_current_tab()
        if not active_tab or not active_tab.workbench_instance:
            return
        
        workbench = active_tab.workbench_instance

        if action == "find":
            workbench.find_next(params)
        elif action == "replace":
            workbench.replace_current_and_find_next(params)
        elif action == "replace_all":
            workbench.replace_all(params)