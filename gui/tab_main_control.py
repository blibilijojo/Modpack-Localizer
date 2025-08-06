# gui/tab_main_control.py

import tkinter as tk
from tkinter import filedialog
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
import json # Ensure json is imported for JSONDecodeError check
from gui.custom_widgets import ToolTip
from utils import config_manager
import logging

class PackSettingsDialog(tk.Toplevel):
    # ... (此内部类无需任何改动) ...
    def __init__(self, parent, presets_dict):
        super().__init__(parent)
        self.title("选择资源包元数据")
        self.parent = parent
        self.result = None
        self.presets = presets_dict

        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        self.geometry(f"400x200+{parent_x + (parent_width - 400) // 2}+{parent_y + (parent_height - 200) // 2}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        self.choice_var = tk.StringVar(value="current")

        rb_current = ttk.Radiobutton(main_frame, text="使用当前“资源包设置”选项卡中的自定义设置", variable=self.choice_var, value="current", command=self._toggle_preset_combo)
        rb_current.pack(anchor="w")
        
        rb_preset_frame = ttk.Frame(main_frame)
        rb_preset_frame.pack(fill="x", anchor="w", pady=(10, 0))
        rb_preset = ttk.Radiobutton(rb_preset_frame, text="从预案列表中选择:", variable=self.choice_var, value="preset", command=self._toggle_preset_combo)
        rb_preset.pack(side="left")

        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(rb_preset_frame, textvariable=self.preset_var, state="disabled", values=list(self.presets.keys()))
        if self.presets:
            self.preset_var.set(list(self.presets.keys())[0])
        self.preset_combo.pack(side="left", fill="x", expand=True, padx=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side="bottom", fill="x", pady=(20, 0))
        
        ok_btn = ttk.Button(btn_frame, text="确认", command=self.on_ok, bootstyle="success")
        ok_btn.pack(side="right")
        cancel_btn = ttk.Button(btn_frame, text="取消", command=self.on_cancel, bootstyle="secondary")
        cancel_btn.pack(side="right", padx=10)
        
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.wait_window(self)

    def _toggle_preset_combo(self):
        if self.choice_var.get() == "preset":
            self.preset_combo.config(state="readonly")
        else:
            self.preset_combo.config(state="disabled")

    def on_ok(self):
        if self.choice_var.get() == "current":
            self.result = {"source": "current"}
        else:
            preset_name = self.preset_var.get()
            if not preset_name:
                ui_utils.show_error("选择错误", "请选择一个有效的预案")
                return
            self.result = {"source": "preset", "name": preset_name, "data": self.presets[preset_name]}
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()

class TabMainControl:
    def __init__(self, parent, ai_service_tab, ai_parameters_tab, pack_settings_tab):
        self.frame = ttk.Frame(parent, padding="10")
        self.ai_service_tab = ai_service_tab
        self.ai_parameters_tab = ai_parameters_tab
        self.pack_settings_tab = pack_settings_tab
        self.root = parent.winfo_toplevel()
        self.config = config_manager.load_config()

        path_frame = ttk.LabelFrame(self.frame, text="路径设置", padding="10")
        path_frame.pack(fill="x", expand=False)
        
        self.mods_dir_var = tk.StringVar(value=self.config.get("mods_dir", ""))
        self._create_path_entry(path_frame, "Mods 文件夹:", self.mods_dir_var, "directory", "包含所有.jar模组文件的文件夹")
        
        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_path", ""))
        
        dict_path_frame = ttk.Frame(path_frame)
        dict_path_frame.pack(fill="x", pady=5)
        
        dict_label = ttk.Label(dict_path_frame, text="社区词典文件:", width=15)
        dict_label.pack(side="left")
        ToolTip(dict_label, "可选。一个包含补充翻译的 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var)
        dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.community_dict_var.trace_add("write", lambda *args: self._save_config())
        
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_file(self.community_dict_var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")]), bootstyle="primary-outline")
        browse_btn.pack(side="left")

        self.download_dict_button = ttk.Button(dict_path_frame, text="下载最新", command=self._download_community_dict_async, bootstyle="info")
        self.download_dict_button.pack(side="left", padx=(5, 0))
        ToolTip(self.download_dict_button, "从GitHub仓库下载最新的社区词典文件。\n文件将保存到程序目录下。")

        proxy_frame = ttk.Frame(path_frame)
        proxy_frame.pack(fill="x", padx=5, pady=(0, 5))
        
        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_github_proxy", True))
        proxy_check = ttk.Checkbutton(proxy_frame, text="使用 GitHub 代理加速词典下载", variable=self.use_proxy_var, bootstyle="primary")
        proxy_check.pack(side="left", padx=(105, 0)) # Align with entry boxes
        ToolTip(proxy_check, "开启后，在下载社区词典时会自动检测并使用可用的CDN代理，解决国内访问GitHub困难的问题。")
        self.use_proxy_var.trace_add("write", lambda *args: self._save_config())
        
        packs_frame = ttk.LabelFrame(path_frame, text="第三方汉化包列表 (优先级由上至下)", padding="10")
        packs_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        list_container = ttk.Frame(packs_frame)
        list_container.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_container, orient="vertical")
        self.packs_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, selectmode="extended", height=6)
        scrollbar.config(command=self.packs_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.packs_listbox.pack(side="left", fill="both", expand=True)

        for path in self.config.get("community_pack_paths", []):
            self.packs_listbox.insert(tk.END, path)

        list_btn_frame = ttk.Frame(packs_frame)
        list_btn_frame.pack(fill="x", pady=(5,0))

        add_btn = ttk.Button(list_btn_frame, text="✚ 添加", command=self._add_packs, bootstyle="success-outline", width=8)
        ToolTip(add_btn, "添加一个或多个第三方汉化资源包(.zip)")
        add_btn.pack(side="left", padx=2)
        remove_btn = ttk.Button(list_btn_frame, text="✖ 移除", command=self._remove_packs, bootstyle="danger-outline", width=8)
        remove_btn.pack(side="left", padx=2)
        
        spacer = ttk.Frame(list_btn_frame)
        spacer.pack(side="left", fill="x", expand=True)

        up_btn = ttk.Button(list_btn_frame, text="▲ 上移", command=lambda: self._move_pack(-1), bootstyle="info-outline", width=8)
        up_btn.pack(side="left", padx=2)
        down_btn = ttk.Button(list_btn_frame, text="▼ 下移", command=lambda: self._move_pack(1), bootstyle="info-outline", width=8)
        down_btn.pack(side="left", padx=2)

        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
        self._create_path_entry(path_frame, "输出文件夹:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")

        self.start_button = ttk.Button(self.frame, text="--- 开始智能汉化更新 ---", command=self.start_workflow_prompt, bootstyle="success")
        self.start_button.pack(fill="x", pady=20, ipady=10)
        self._create_log_frame()

    def _save_config(self):
        """Saves all path settings from the UI to the config file."""
        self.config["mods_dir"] = self.mods_dir_var.get()
        self.config["output_dir"] = self.output_dir_var.get()
        self.config["community_dict_path"] = self.community_dict_var.get()
        self.config["community_pack_paths"] = list(self.packs_listbox.get(0, tk.END))
        self.config["use_github_proxy"] = self.use_proxy_var.get() # Save proxy setting
        config_manager.save_config(self.config)

    def _create_path_entry(self, parent, label_text, var, browse_type, tooltip):
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill="x", pady=5)
        label = ttk.Label(row_frame, text=label_text, width=15)
        label.pack(side="left")
        ToolTip(label, tooltip)
        entry = ttk.Entry(row_frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        var.trace_add("write", lambda *args: self._save_config())
        
        def browse_and_save():
            if browse_type == "directory":
                ui_utils.browse_directory(var)
            elif browse_type == "file":
                ui_utils.browse_file(var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")])
            else: 
                ui_utils.browse_file(var, [("ZIP压缩包", "*.zip")])
        
        ttk.Button(row_frame, text="浏览...", command=browse_and_save, bootstyle="primary-outline").pack(side="left")

    def start_workflow_prompt(self):
        self.config = config_manager.load_config()
        presets = self.config.get("pack_settings_presets", {})
        
        dialog = PackSettingsDialog(self.root, presets)
        choice = dialog.result

        if choice is None:
            self.log_message("操作已取消", "INFO")
            return

        if choice["source"] == "current":
            pack_settings = self.pack_settings_tab.get_current_settings()
        else:
            pack_settings = choice["data"]
            self.log_message(f"已选择预案 '{choice['name']}' 的资源包设置", "INFO")
        
        self.start_workflow(pack_settings)

    def start_workflow(self, pack_settings: dict):
        self._prepare_ui_for_workflow()
        
        try:
            self._save_config()
            service_settings = self.ai_service_tab.get_and_save_settings()
            param_settings = self.ai_parameters_tab.get_and_save_settings()
            
            settings = {**service_settings, **param_settings}
            
            settings['mods_dir'] = self.config.get("mods_dir", "")
            settings['output_dir'] = self.config.get("output_dir", "")
            settings['community_dict_path'] = self.config.get("community_dict_path", "")
            settings['zip_paths'] = self.config.get("community_pack_paths", [])
            settings['pack_settings'] = pack_settings
            
            if not all([settings['mods_dir'], settings['output_dir']]):
                 raise ValueError("Mods文件夹和输出文件夹路径不能为空！")

            orchestrator = Orchestrator(settings, self.update_progress)
            
            def workflow_wrapper():
                try:
                    orchestrator.run_workflow()
                except Exception as e:
                    self.update_progress(f"发生致命错误: {e}", -1)
            
            threading.Thread(target=workflow_wrapper, daemon=True).start()
            
        except Exception as e:
            self.update_progress(f"启动失败: {e}", -1)

    def _add_packs(self):
        paths = filedialog.askopenfilenames(title="选择一个或多个第三方汉化包", filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")])
        for path in paths:
            if path not in self.packs_listbox.get(0, tk.END):
                self.packs_listbox.insert(tk.END, path)
        self._save_config()

    def _remove_packs(self):
        selected_indices = self.packs_listbox.curselection()
        for i in reversed(selected_indices):
            self.packs_listbox.delete(i)
        self._save_config()

    def _move_pack(self, direction):
        selected_indices = self.packs_listbox.curselection()
        if not selected_indices:
            return
        
        indices = sorted(list(selected_indices), reverse=(direction < 0))
        for i in indices:
            if 0 <= i + direction < self.packs_listbox.size():
                text = self.packs_listbox.get(i)
                self.packs_listbox.delete(i)
                self.packs_listbox.insert(i + direction, text)
                self.packs_listbox.selection_set(i + direction)
        self._save_config()

    def _prepare_ui_for_workflow(self):
        self.start_button.config(state="disabled")
        self.open_output_button.config(state="disabled")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        self.progress_bar.config(bootstyle="success-striped")
        self.status_var.set("准备开始...")
        self.progress_var.set(0)

    def _reset_ui_after_workflow(self, success=True):
        self.start_button.config(state="normal")
        if success:
            self.open_output_button.config(state="normal")
            self.log_message("流程执行完毕！资源包已生成", "SUCCESS")
        else:
            self.log_message("流程因错误中断", "CRITICAL")
            self.progress_bar.config(bootstyle="danger-striped")

    def update_progress(self, message, percentage):
        def _update():
            self.status_var.set(message)
            if percentage >= 0:
                self.progress_var.set(percentage)
            
            if percentage == 100:
                self._reset_ui_after_workflow(success=True)
            elif percentage == -1:
                self._reset_ui_after_workflow(success=False)
        try:
            if self.frame.winfo_exists():
                self.root.after(0, _update)
        except RuntimeError:
            pass
            
    def get_log_frame(self):
        return self.log_frame_container

    def _create_log_frame(self):
        self.log_frame_container = ttk.Frame(self.root)
        log_frame = ttk.LabelFrame(self.log_frame_container, text="状态与日志", padding="10")
        log_frame.pack(fill="both", expand=True)
        progress_frame = ttk.Frame(log_frame)
        progress_frame.pack(fill="x", pady=(0, 5))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, bootstyle="success-striped")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.open_output_button = ttk.Button(progress_frame, text="📂 打开", command=self._open_output_dir, state="disabled", bootstyle="info-outline", width=6)
        self.open_output_button.grid(row=0, column=1, padx=(10, 0))
        ToolTip(self.open_output_button, "打开输出文件夹")
        self.status_var = tk.StringVar(value="准备就绪")
        status_label = ttk.Label(log_frame, textvariable=self.status_var, anchor="center")
        status_label.pack(fill="x", anchor="center", pady=(5, 0))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled", wrap="word", font=("Consolas", 9), relief="flat")
        self.log_text.pack(fill="both", expand=True, pady=5)
        self.log_text.tag_config("INFO", foreground="gray")
        self.log_text.tag_config("WARNING", foreground="#ff8c00")
        self.log_text.tag_config("ERROR", foreground="red")
        self.log_text.tag_config("CRITICAL", foreground="red", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("SUCCESS", foreground="green")
        self.log_text.tag_config("NORMAL", foreground="black")

    def log_message(self, message, level="NORMAL"):
        def _log():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, message + "\n", level)
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        try:
            if self.frame.winfo_exists():
                self.root.after(0, _log)
        except RuntimeError:
            pass

    def _open_output_dir(self):
        output_path = self.output_dir_var.get()
        if output_path and os.path.isdir(output_path):
            try:
                if sys.platform == "win32":
                    os.startfile(output_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", output_path])
                else:
                    subprocess.Popen(["xdg-open", output_path])
            except Exception as e:
                ui_utils.show_error("打开失败", f"无法打开文件夹：{e}")
        else:
            ui_utils.show_error("路径无效", "输出文件夹路径不存在或无效")
    
    def _download_community_dict_async(self):
        self.download_dict_button.config(state="disabled", text="下载中...")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _find_available_proxy(self) -> str | None:
        """
        Finds a working GitHub proxy by testing them in random order.
        A proxy is considered working if it can successfully access the GitHub API rate_limit endpoint.
        Returns the base URL of the working proxy (e.g., "gh-proxy.com").
        """
        proxies = self.config.get("github_proxies", [])
        if not proxies:
            logging.warning("GitHub代理列表为空。")
            return None
        
        random.shuffle(proxies)
        
        # This is the original GitHub API URL, which will be proxied
        CHECK_API_URL_ORIGINAL = "https://api.github.com/rate_limit" 
        
        for proxy_base_url in proxies:
            # Construct the full URL that goes through the CDN proxy
            # Example: https://gh-proxy.com/https://api.github.com/rate_limit
            proxied_check_url = f"https://{proxy_base_url}/{CHECK_API_URL_ORIGINAL}"
            logging.info(f"正在测试GitHub代理: {proxy_base_url}...")
            try:
                # Use a GET request with a short timeout
                response = requests.get(proxied_check_url, timeout=5) 
                
                if response.status_code == 200:
                    try:
                        # Ensure it's a valid JSON response from GitHub API
                        # Some proxies might return 200 but with garbage content.
                        response.json() 
                        logging.info(f"代理 {proxy_base_url} 可用！")
                        return proxy_base_url
                    except json.JSONDecodeError:
                        logging.warning(f"代理 {proxy_base_url} 返回非JSON响应，可能无法正确代理API请求。")
                        continue # Try the next one
                else:
                    logging.warning(f"代理 {proxy_base_url} 测试失败，状态码: {response.status_code}")
            except (requests.exceptions.RequestException, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logging.warning(f"代理 {proxy_base_url} 测试失败: {e}")
                continue # Try the next one
        
        logging.error("所有GitHub代理均测试失败。")
        return None

    def _download_worker(self):
        """
        Performs the download logic, using CDN proxy if enabled and available.
        """
        # Original GitHub API URL for latest release
        GITHUB_API_RELEASE_URL = "https://api.github.com/repos/blibilijojo/i18n-Dict-Extender/releases/latest"
        DEST_FILE = Path("Dict-Sqlite.db").resolve()
        
        chosen_proxy_base = None
        if self.use_proxy_var.get():
            logging.info("已启用GitHub代理，正在寻找可用CDN代理...")
            chosen_proxy_base = self._find_available_proxy()
            if not chosen_proxy_base:
                error_message = "下载社区词典失败: 所有CDN代理均不可用。\n请尝试关闭代理后重试，或检查网络连接。"
                self.root.after(0, self._update_ui_after_download, False, error_message)
                return

        try:
            # Determine the URL for fetching release data (proxied or direct)
            api_fetch_url = f"https://{chosen_proxy_base}/{GITHUB_API_RELEASE_URL}" if chosen_proxy_base else GITHUB_API_RELEASE_URL
            
            logging.info(f"正在向GitHub API发送请求: {api_fetch_url}")
            response = requests.get(api_fetch_url, timeout=15)
            response.raise_for_status() # Raises HTTPError for 4xx/5xx responses
            release_data = response.json()
            
            # Get the direct download URL for the asset from GitHub's response
            asset_download_url_original = None
            for asset in release_data.get("assets", []):
                if asset.get("name") == "Dict-Sqlite.db":
                    asset_download_url_original = asset.get("browser_download_url")
                    break
            
            if not asset_download_url_original:
                raise ValueError("在最新的Release中未找到'Dict-Sqlite.db'文件。")
            
            # Determine the final download URL (proxied or direct)
            # Example proxied URL: https://gh-proxy.com/https://github.com/blibilijojo/.../Dict-Sqlite.db
            final_download_url = f"https://{chosen_proxy_base}/{asset_download_url_original}" if chosen_proxy_base else asset_download_url_original
            
            logging.info(f"成功找到下载链接，开始下载: {final_download_url}")

            with requests.get(final_download_url, stream=True, timeout=60) as r:
                r.raise_for_status() # Raises HTTPError for 4xx/5xx responses during file download
                with open(DEST_FILE, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            logging.info(f"文件已成功下载到: {DEST_FILE}")
            self.root.after(0, self._update_ui_after_download, True, str(DEST_FILE))

        except requests.exceptions.RequestException as e:
            # Catch all requests-related exceptions (HTTPError, ConnectionError, Timeout, etc.)
            error_message = f"下载社区词典失败: 网络或CDN代理错误 - {e}"
            logging.error(error_message, exc_info=True)
            self.root.after(0, self._update_ui_after_download, False, error_message)
        except Exception as e:
            # Catch other general errors (e.g., JSON parsing failure, file not found in release)
            error_message = f"下载社区词典失败: {e}"
            logging.error(error_message, exc_info=True)
            self.root.after(0, self._update_ui_after_download, False, error_message)

    def _update_ui_after_download(self, success: bool, message: str):
        self.download_dict_button.config(state="normal", text="下载最新")
        if success:
            self.community_dict_var.set(message)
            ui_utils.show_info("下载成功", f"社区词典已更新！\n路径已自动设置为:\n{message}")
        else:
            ui_utils.show_error("下载失败", message)