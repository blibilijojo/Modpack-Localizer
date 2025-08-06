# gui/tab_main_control.py

import tkinter as tk
from tkinter import filedialog, Toplevel
import ttkbootstrap as ttk
from tkinter import scrolledtext
from gui import ui_utils
from core.orchestrator import Orchestrator
import threading
import requests
from pathlib import Path
import os
import sys
import subprocess
import random
import json
import time
from gui.custom_widgets import ToolTip
from utils import config_manager
import logging

class DownloadProgressDialog(Toplevel):
    def __init__(self, parent, title="下载中"):
        super().__init__(parent)
        self.title(title); self.transient(parent); self.grab_set(); self.resizable(False, False)
        main_frame = ttk.Frame(self, padding=20); main_frame.pack(fill="both", expand=True)
        self.status_label = ttk.Label(main_frame, text="正在连接..."); self.status_label.pack(fill="x", pady=5)
        self.progress_bar = ttk.Progressbar(main_frame, length=300, mode='determinate'); self.progress_bar.pack(fill="x", pady=5)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
    def update_progress(self, status: str, percentage: float, speed: str):
        def _update(): self.status_label.config(text=f"{status}... {int(percentage)}% ({speed})"); self.progress_bar['value'] = percentage
        self.after(0, _update)
    def close_dialog(self): self.after(100, self.destroy)

class PackSettingsDialog(Toplevel):
    def __init__(self, parent, presets_dict):
        super().__init__(parent)
        self.title("选择资源包元数据"); self.parent = parent; self.result = None; self.presets = presets_dict
        parent_x, parent_y, parent_width, parent_height = parent.winfo_x(), parent.winfo_y(), parent.winfo_width(), parent.winfo_height()
        self.geometry(f"400x200+{parent_x + (parent_width - 400) // 2}+{parent_y + (parent_height - 200) // 2}")
        self.resizable(False, False); self.transient(parent); self.grab_set()
        main_frame = ttk.Frame(self, padding=20); main_frame.pack(fill="both", expand=True)
        self.choice_var = tk.StringVar(value="current")
        ttk.Radiobutton(main_frame, text="使用当前“资源包设置”选项卡中的自定义设置", variable=self.choice_var, value="current", command=self._toggle_preset_combo).pack(anchor="w")
        rb_preset_frame = ttk.Frame(main_frame); rb_preset_frame.pack(fill="x", anchor="w", pady=(10, 0))
        ttk.Radiobutton(rb_preset_frame, text="从预案列表中选择:", variable=self.choice_var, value="preset", command=self._toggle_preset_combo).pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(rb_preset_frame, textvariable=self.preset_var, state="disabled", values=list(self.presets.keys()))
        if self.presets: self.preset_var.set(list(self.presets.keys())[0])
        self.preset_combo.pack(side="left", fill="x", expand=True, padx=5)
        btn_frame = ttk.Frame(main_frame); btn_frame.pack(side="bottom", fill="x", pady=(20, 0))
        ttk.Button(btn_frame, text="确认", command=self.on_ok, bootstyle="success").pack(side="right")
        ttk.Button(btn_frame, text="取消", command=self.on_cancel, bootstyle="secondary").pack(side="right", padx=10)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel); self.wait_window(self)
    def _toggle_preset_combo(self): self.preset_combo.config(state="readonly" if self.choice_var.get() == "preset" else "disabled")
    def on_ok(self):
        if self.choice_var.get() == "current": self.result = {"source": "current"}
        else:
            preset_name = self.preset_var.get()
            if not preset_name: ui_utils.show_error("选择错误", "请选择一个有效的预案"); return
            self.result = {"source": "preset", "name": preset_name, "data": self.presets[preset_name]}
        self.destroy()
    def on_cancel(self): self.result = None; self.destroy()

class TabMainControl:
    def __init__(self, parent, ai_service_tab, ai_parameters_tab, pack_settings_tab):
        self.frame = ttk.Frame(parent, padding="10"); self.ai_service_tab = ai_service_tab; self.ai_parameters_tab = ai_parameters_tab; self.pack_settings_tab = pack_settings_tab
        self.root = parent.winfo_toplevel(); self.config = config_manager.load_config()
        path_frame = ttk.LabelFrame(self.frame, text="路径设置", padding="10"); path_frame.pack(fill="x", expand=False)
        self.mods_dir_var = tk.StringVar(value=self.config.get("mods_dir", "")); self._create_path_entry(path_frame, "Mods 文件夹:", self.mods_dir_var, "directory", "包含所有.jar模组文件的文件夹")
        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_path", ""))
        dict_path_frame = ttk.Frame(path_frame); dict_path_frame.pack(fill="x", pady=5)
        dict_label = ttk.Label(dict_path_frame, text="社区词典文件:", width=15); dict_label.pack(side="left"); ToolTip(dict_label, "可选。一个包含补充翻译的 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var); dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.community_dict_var.trace_add("write", lambda *args: self._save_config())
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_file(self.community_dict_var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")]), bootstyle="primary-outline"); browse_btn.pack(side="left")
        self.download_dict_button = ttk.Button(dict_path_frame, text="检查/更新词典", command=self._check_and_update_dict_async, bootstyle="info"); self.download_dict_button.pack(side="left", padx=(5, 0)); ToolTip(self.download_dict_button, "检查云端是否有新版本的社区词典，并按需下载。")
        proxy_frame = ttk.Frame(path_frame); proxy_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_github_proxy", True))
        proxy_check = ttk.Checkbutton(proxy_frame, text="使用 GitHub 代理加速词典下载", variable=self.use_proxy_var, bootstyle="primary"); proxy_check.pack(side="left", padx=(105, 0)); ToolTip(proxy_check, "开启后，在下载社区词典时会自动使用内置的代理服务，解决国内访问GitHub困难的问题。")
        self.use_proxy_var.trace_add("write", lambda *args: self._save_config())
        packs_frame = ttk.LabelFrame(path_frame, text="第三方汉化包列表 (优先级由上至下)", padding="10"); packs_frame.pack(fill="both", expand=True, pady=(10, 0))
        list_container = ttk.Frame(packs_frame); list_container.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical")
        self.packs_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, selectmode="extended", height=6); scrollbar.config(command=self.packs_listbox.yview); scrollbar.pack(side="right", fill="y"); self.packs_listbox.pack(side="left", fill="both", expand=True)
        for path in self.config.get("community_pack_paths", []): self.packs_listbox.insert(tk.END, path)
        list_btn_frame = ttk.Frame(packs_frame); list_btn_frame.pack(fill="x", pady=(5,0))
        add_btn = ttk.Button(list_btn_frame, text="✚ 添加", command=self._add_packs, bootstyle="success-outline", width=8); ToolTip(add_btn, "添加一个或多个第三方汉化资源包(.zip)"); add_btn.pack(side="left", padx=2)
        remove_btn = ttk.Button(list_btn_frame, text="✖ 移除", command=self._remove_packs, bootstyle="danger-outline", width=8); remove_btn.pack(side="left", padx=2)
        spacer = ttk.Frame(list_btn_frame); spacer.pack(side="left", fill="x", expand=True)
        up_btn = ttk.Button(list_btn_frame, text="▲ 上移", command=lambda: self._move_pack(-1), bootstyle="info-outline", width=8); up_btn.pack(side="left", padx=2)
        down_btn = ttk.Button(list_btn_frame, text="▼ 下移", command=lambda: self._move_pack(1), bootstyle="info-outline", width=8); down_btn.pack(side="left", padx=2)
        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", "")); self._create_path_entry(path_frame, "输出文件夹:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")
        self.start_button = ttk.Button(self.frame, text="--- 开始智能汉化更新 ---", command=self.start_workflow_prompt, bootstyle="success"); self.start_button.pack(fill="x", pady=20, ipady=10)
        self._create_log_frame()
    def _save_config(self): self.config["mods_dir"] = self.mods_dir_var.get(); self.config["output_dir"] = self.output_dir_var.get(); self.config["community_dict_path"] = self.community_dict_var.get(); self.config["community_pack_paths"] = list(self.packs_listbox.get(0, tk.END)); self.config["use_github_proxy"] = self.use_proxy_var.get(); config_manager.save_config(self.config)
    def _create_path_entry(self, parent, label_text, var, browse_type, tooltip):
        row_frame = ttk.Frame(parent); row_frame.pack(fill="x", pady=5)
        label = ttk.Label(row_frame, text=label_text, width=15); label.pack(side="left"); ToolTip(label, tooltip)
        entry = ttk.Entry(row_frame, textvariable=var); entry.pack(side="left", fill="x", expand=True, padx=5)
        var.trace_add("write", lambda *args: self._save_config())
        def browse():
            if browse_type == "directory": ui_utils.browse_directory(var)
            elif browse_type == "file": ui_utils.browse_file(var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")])
            else: ui_utils.browse_file(var, [("ZIP压缩包", "*.zip")])
        ttk.Button(row_frame, text="浏览...", command=browse, bootstyle="primary-outline").pack(side="left")
    def start_workflow_prompt(self):
        self.config = config_manager.load_config(); presets = self.config.get("pack_settings_presets", {})
        dialog = PackSettingsDialog(self.root, presets); choice = dialog.result
        if choice is None: self.log_message("操作已取消", "INFO"); return
        pack_settings = self.pack_settings_tab.get_current_settings() if choice["source"] == "current" else choice["data"]
        if choice["source"] != "current": self.log_message(f"已选择预案 '{choice['name']}' 的资源包设置", "INFO")
        self.start_workflow(pack_settings)
    def start_workflow(self, pack_settings: dict):
        self._prepare_ui_for_workflow()
        try:
            self._save_config(); settings = {**self.ai_service_tab.get_and_save_settings(), **self.ai_parameters_tab.get_and_save_settings()}
            settings.update({'mods_dir': self.config.get("mods_dir", ""), 'output_dir': self.config.get("output_dir", ""), 'community_dict_path': self.config.get("community_dict_path", ""), 'zip_paths': self.config.get("community_pack_paths", []), 'pack_settings': pack_settings})
            if not all([settings['mods_dir'], settings['output_dir']]): raise ValueError("Mods文件夹和输出文件夹路径不能为空！")
            from core.orchestrator import Orchestrator
            orchestrator = Orchestrator(settings, self.update_progress)
            threading.Thread(target=orchestrator.run_workflow, daemon=True).start()
        except Exception as e: self.update_progress(f"启动失败: {e}", -1)
    def _add_packs(self):
        paths = filedialog.askopenfilenames(title="选择一个或多个第三方汉化包", filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")])
        for path in paths:
            if path not in self.packs_listbox.get(0, tk.END): self.packs_listbox.insert(tk.END, path)
        self._save_config()
    def _remove_packs(self):
        selected_indices = self.packs_listbox.curselection()
        for i in reversed(selected_indices): self.packs_listbox.delete(i)
        self._save_config()
    def _move_pack(self, direction):
        indices = self.packs_listbox.curselection()
        if not indices: return
        for i in sorted(list(indices), reverse=(direction < 0)):
            if 0 <= i + direction < self.packs_listbox.size():
                text = self.packs_listbox.get(i)
                self.packs_listbox.delete(i); self.packs_listbox.insert(i + direction, text)
                self.packs_listbox.selection_set(i + direction)
        self._save_config()
    def _prepare_ui_for_workflow(self): self.start_button.config(state="disabled"); self.open_output_button.config(state="disabled"); self.log_text.config(state="normal"); self.log_text.delete("1.0", tk.END); self.log_text.config(state="disabled"); self.progress_bar.config(bootstyle="success-striped"); self.status_var.set("准备开始..."); self.progress_var.set(0)
    def _reset_ui_after_workflow(self, success=True):
        self.start_button.config(state="normal")
        if success: self.open_output_button.config(state="normal"); self.log_message("流程执行完毕！资源包已生成", "SUCCESS")
        else: self.log_message("流程因错误中断", "CRITICAL"); self.progress_bar.config(bootstyle="danger-striped")
    def update_progress(self, message, percentage):
        def _update():
            self.status_var.set(message)
            if percentage >= 0: self.progress_var.set(percentage)
            if percentage == 100: self._reset_ui_after_workflow(success=True)
            elif percentage == -1: self._reset_ui_after_workflow(success=False)
        try:
            if self.frame.winfo_exists(): self.root.after(0, _update)
        except RuntimeError: pass
    def get_log_frame(self): return self.log_frame_container
    def _create_log_frame(self):
        self.log_frame_container = ttk.Frame(self.root)
        log_frame = ttk.LabelFrame(self.log_frame_container, text="状态与日志", padding="10"); log_frame.pack(fill="both", expand=True)
        progress_frame = ttk.Frame(log_frame); progress_frame.pack(fill="x", pady=(0, 5)); progress_frame.columnconfigure(0, weight=1)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, bootstyle="success-striped"); self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.open_output_button = ttk.Button(progress_frame, text="📂 打开", command=self._open_output_dir, state="disabled", bootstyle="info-outline", width=6); self.open_output_button.grid(row=0, column=1, padx=(10, 0)); ToolTip(self.open_output_button, "打开输出文件夹")
        self.status_var = tk.StringVar(value="准备就绪"); status_label = ttk.Label(log_frame, textvariable=self.status_var, anchor="center"); status_label.pack(fill="x", anchor="center", pady=(5, 0))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled", wrap="word", font=("Consolas", 9), relief="flat"); self.log_text.pack(fill="both", expand=True, pady=5)
        for level, color in [("INFO", "gray"), ("WARNING", "#ff8c00"), ("ERROR", "red"), ("SUCCESS", "green"), ("NORMAL", "black")]: self.log_text.tag_config(level, foreground=color)
        self.log_text.tag_config("CRITICAL", foreground="red", font=("Consolas", 9, "bold"))
    def log_message(self, message, level="NORMAL"):
        def _log(): self.log_text.config(state="normal"); self.log_text.insert(tk.END, message + "\n", level); self.log_text.see(tk.END); self.log_text.config(state="disabled")
        try:
            if self.frame.winfo_exists(): self.root.after(0, _log)
        except RuntimeError: pass
    def _open_output_dir(self):
        output_path = self.output_dir_var.get()
        if not (output_path and os.path.isdir(output_path)): ui_utils.show_error("路径无效", "输出文件夹路径不存在或无效"); return
        try:
            if sys.platform == "win32": os.startfile(output_path)
            elif sys.platform == "darwin": subprocess.Popen(["open", output_path])
            else: subprocess.Popen(["xdg-open", output_path])
        except Exception as e: ui_utils.show_error("打开失败", f"无法打开文件夹：{e}")
    
    def _check_and_update_dict_async(self):
        self.download_dict_button.config(state="disabled", text="检查中...")
        threading.Thread(target=self._dict_update_worker, daemon=True).start()

    def _get_remote_dict_info(self) -> dict | None:
        api_url = "https://api.github.com/repos/blibilijojo/i18n-Dict-Extender/releases/latest"
        logging.info(f"正在直接请求GitHub API获取词典信息: {api_url}")
        try:
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            version = data.get("tag_name")
            url = next((asset.get("browser_download_url") for asset in data.get("assets", []) if asset.get("name") == "Dict-Sqlite.db"), None)
            if version and url: return {"version": version, "url": url}
        except Exception as e: logging.error(f"获取远程词典信息失败: {e}")
        return None

    def _format_speed(self, speed_bps: float) -> str:
        if speed_bps > 1024 * 1024: return f"{speed_bps / (1024 * 1024):.2f} MB/s"
        return f"{speed_bps / 1024:.1f} KB/s"

    def _dict_update_worker(self):
        try:
            remote_info = self._get_remote_dict_info()
            if not remote_info:
                self.root.after(0, lambda: ui_utils.show_error("检查失败", "无法获取远程词典版本信息，请检查网络连接。"))
                return

            local_version = self.config.get("last_dict_version", "0.0.0")
            remote_version = remote_info["version"]
            
            logging.info(f"本地词典版本: {local_version}, 远程词典版本: {remote_version}")

            if local_version == remote_version:
                self.root.after(0, lambda: ui_utils.show_info("检查完成", f"您的社区词典已是最新版本 ({local_version})。"))
                return
            
            # --- 关键修复：使用 wait_variable 实现线程同步 ---
            msg = f"发现新的社区词典版本: {remote_version}\n(您当前的版本: {local_version})\n\n是否立即下载更新？"
            
            user_wants_to_update = tk.BooleanVar()
            
            def ask_on_main_thread():
                # 这个函数将在主线程中执行，安全地显示对话框
                result = ui_utils.show_warning("发现新版本", msg)
                user_wants_to_update.set(result)

            self.root.after(0, ask_on_main_thread)
            # 后台线程在这里暂停，等待主线程的 ask_on_main_thread 函数设置 user_wants_to_update 变量
            self.root.wait_variable(user_wants_to_update)

            # 当用户点击按钮后，wait_variable 结束，我们可以在这里获取结果
            if not user_wants_to_update.get():
                logging.info("用户选择不更新社区词典。")
                return # 线程结束

            # --- 用户同意更新，继续执行下载 ---
            progress_dialog = DownloadProgressDialog(self.root, title="下载社区词典")
            
            STABLE_PROXY_URL = "https://lucky-moth-20.deno.dev/"
            DEST_FILE = Path("Dict-Sqlite.db").resolve()
            
            final_download_url = remote_info["url"]
            if self.use_proxy_var.get():
                final_download_url = f"{STABLE_PROXY_URL}{remote_info['url']}"
            
            from utils import update_checker
            download_ok = update_checker.download_update(final_download_url, DEST_FILE, 
                lambda s, p, sp: progress_dialog.update_progress(s, p, sp))

            progress_dialog.close_dialog()

            if download_ok:
                self.config["last_dict_version"] = remote_version
                self.config["community_dict_path"] = str(DEST_FILE)
                config_manager.save_config(self.config)
                self.root.after(0, lambda: self.community_dict_var.set(str(DEST_FILE)))
                self.root.after(0, lambda: ui_utils.show_info("更新成功", f"社区词典已成功更新到版本 {remote_version}！"))
            else:
                self.root.after(0, lambda: ui_utils.show_error("下载失败", "下载新版词典时发生错误，请检查网络或代理后重试。"))

        finally:
            self.root.after(0, lambda: self.download_dict_button.config(state="normal", text="检查/更新词典"))