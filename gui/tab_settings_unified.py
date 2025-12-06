import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils, custom_widgets
from utils import config_manager
import threading
import requests
import logging
from pathlib import Path

class UnifiedSettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.config = config_manager.load_config()
        self.log_level_var = tk.StringVar(value=self.config.get("log_level", "INFO"))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.basic_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.ai_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.resource_pack_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.pack_settings_tab_frame = ttk.Frame(self.notebook)
        self.advanced_tab_frame = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.basic_tab_frame, text=" 基础设置 ")
        self.notebook.add(self.ai_tab_frame, text=" AI 翻译设置 ")
        self.notebook.add(self.resource_pack_tab_frame, text=" 资源包管理 ")
        self.notebook.add(self.pack_settings_tab_frame, text=" 生成预案 ")
        self.notebook.add(self.advanced_tab_frame, text=" 高级设置 ")

        self._create_basic_tab_content(self.basic_tab_frame)
        self._create_ai_tab_content(self.ai_tab_frame)
        self._create_resource_pack_tab_content(self.resource_pack_tab_frame)
        self._create_pack_settings_tab_content(self.pack_settings_tab_frame)
        self._create_advanced_tab_content(self.advanced_tab_frame)

    def _create_basic_tab_content(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self._create_basic_settings(container)

    def _create_resource_pack_tab_content(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self._create_resource_pack_settings(container)
        self._create_community_packs_list(container)

    def _create_ai_tab_content(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self._create_ai_service_settings(container)
        self._create_ai_parameters_settings(container)

    def _create_advanced_tab_content(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self._create_log_settings(container)
        self._create_advanced_settings(container)

    def _create_pack_settings_tab_content(self, parent):
        from gui.tab_pack_settings import TabPackSettings
        self.pack_settings_manager = TabPackSettings(parent)

    def _create_basic_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="基础设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
        self._create_path_entry(frame, "默认输出文件夹:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")

        self.pack_as_zip_var = tk.BooleanVar(value=self.config.get("pack_as_zip", False))
        zip_check = ttk.Checkbutton(frame, text="打包为.zip压缩包", variable=self.pack_as_zip_var, bootstyle="primary")
        zip_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(zip_check, "开启后, 将直接生成一个.zip格式的资源包文件, 而不是文件夹。")

        self.use_origin_name_lookup_var = tk.BooleanVar(value=self.config.get("use_origin_name_lookup", True))
        origin_check = ttk.Checkbutton(frame, text="启用原文匹配", variable=self.use_origin_name_lookup_var, bootstyle="primary")
        origin_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(origin_check, "推荐开启。\n当key查找失败时，尝试使用英文原文进行二次查找。\n能极大提升词典利用率，但可能在极少数情况下导致误翻。")

        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_github_proxy", True))
        proxy_check = ttk.Checkbutton(frame, text="使用代理加速下载", variable=self.use_proxy_var, bootstyle="primary")
        proxy_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(proxy_check, "开启后，在下载社区词典或程序更新时会自动使用内置的代理服务。")

        self.use_origin_name_lookup_var.trace_add("write", lambda *args: self._save_all_settings())
        self.use_proxy_var.trace_add("write", lambda *args: self._save_all_settings())
        self.pack_as_zip_var.trace_add("write", lambda *args: self._save_all_settings())

    def _create_advanced_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="高级设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

    def _create_log_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="日志设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

        # 日志设置说明
        ttk.Label(frame, text="日志设置用于控制程序运行时记录的信息详细程度，帮助您调试和了解程序运行状态。").pack(anchor="w", pady=5)
        ttk.Label(frame, text="级别从低到高：DEBUG < INFO < WARNING < ERROR < CRITICAL，级别越高记录的信息越少。").pack(anchor="w", pady=5)

        # 直接显示日志级别含义，让用户一目了然
        log_level_desc_frame = ttk.Frame(frame)
        log_level_desc_frame.pack(fill="x", pady=5)
        log_level_desc = ttk.Label(log_level_desc_frame, 
                                  text="日志级别含义：", 
                                  font=ttk.Style().configure(".").get("font", ())[:2] + ("bold",))
        log_level_desc.pack(anchor="w", pady=2)
        
        # 详细的日志级别说明，直接显示在界面上
        desc_text = """        
DEBUG: 最详细的日志，记录所有程序运行细节（适合开发调试）
INFO: 基本的程序运行信息，如任务开始、完成等（适合普通用户）
WARNING: 警告信息，提示潜在问题但不影响程序运行
ERROR: 错误信息，表示部分功能可能无法正常工作
CRITICAL: 致命错误，程序即将崩溃
        """
        log_level_details = ttk.Label(log_level_desc_frame, 
                                    text=desc_text.strip(), 
                                    justify="left",
                                    wraplength=700)
        log_level_details.pack(anchor="w", pady=5, padx=10)

        log_level_frame = ttk.Frame(frame)
        log_level_frame.pack(fill="x", pady=5)
        log_level_label = ttk.Label(log_level_frame, text="选择日志级别:", width=15)
        log_level_label.pack(side="left")
        custom_widgets.ToolTip(log_level_label, "设置日志记录的详细程度")
        log_level_combobox = ttk.Combobox(log_level_frame, textvariable=self.log_level_var, 
                                         values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                                         state="readonly")
        log_level_combobox.pack(side="left", fill="x", expand=True, padx=5)
        
        # 清除选中状态的事件处理
        def on_combobox_select(event):
            self._save_all_settings()
            # 清除选中状态
            event.widget.after(100, lambda: event.widget.selection_clear())
        
        log_level_combobox.bind('<<ComboboxSelected>>', on_combobox_select)
        
        # 添加日志级别的实际影响说明
        ttk.Label(frame, text="提示：日志级别越低，生成的日志文件越大，但包含的信息越详细；级别越高，日志文件越小，但只记录重要信息。").pack(anchor="w", pady=5, padx=0, fill="x")
        ttk.Label(frame, text="日志文件默认保存在程序运行目录下，可用于排查程序运行中遇到的问题。").pack(anchor="w", pady=5, padx=0, fill="x")

    def _create_resource_pack_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="资源包设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_path", ""))
        dict_path_frame = ttk.Frame(frame)
        dict_path_frame.pack(fill="x", pady=5)
        dict_label = ttk.Label(dict_path_frame, text="社区词典文件:", width=15)
        dict_label.pack(side="left")
        custom_widgets.ToolTip(dict_label, "可选。一个包含补充翻译的 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var)
        dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_file(self.community_dict_var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")]), bootstyle="primary-outline")
        browse_btn.pack(side="left")
        self.download_dict_button = ttk.Button(dict_path_frame, text="检查/更新", command=self._check_and_update_dict_async, bootstyle="info")
        self.download_dict_button.pack(side="left", padx=(5, 0))

    def _create_community_packs_list(self, parent):
        packs_frame = tk_ttk.LabelFrame(parent, text="第三方汉化包列表 (优先级由上至下)", padding="10")
        packs_frame.pack(fill="both", expand=True, pady=(10, 0))
        list_container = ttk.Frame(packs_frame)
        list_container.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical")
        self.packs_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, selectmode="extended", height=4)
        scrollbar.config(command=self.packs_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.packs_listbox.pack(side="left", fill="both", expand=True)
        for path in self.config.get("community_pack_paths", []): self.packs_listbox.insert(tk.END, path)
        
        list_btn_frame = ttk.Frame(packs_frame)
        list_btn_frame.pack(fill="x", pady=(5,0))
        add_btn = ttk.Button(list_btn_frame, text="添加", command=self._add_packs, bootstyle="success-outline", width=8)
        add_btn.pack(side="left", padx=2)
        remove_btn = ttk.Button(list_btn_frame, text="移除", command=self._remove_packs, bootstyle="danger-outline", width=8)
        remove_btn.pack(side="left", padx=2)
        spacer = ttk.Frame(list_btn_frame)
        spacer.pack(side="left", fill="x", expand=True)
        up_btn = ttk.Button(list_btn_frame, text="上移", command=lambda: self._move_pack(-1), bootstyle="info-outline", width=8)
        up_btn.pack(side="left", padx=2)
        down_btn = ttk.Button(list_btn_frame, text="下移", command=lambda: self._move_pack(1), bootstyle="info-outline", width=8)
        down_btn.pack(side="left", padx=2)

    def _create_ai_service_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 服务设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        
        ttk.Label(frame, text="API 密钥 (多个密钥可用 换行 或 , 分隔):").pack(anchor="w")
        self.api_keys_text = scrolledtext.ScrolledText(frame, height=3, width=60)
        self.api_keys_text.pack(fill="x", expand=True, pady=2)
        self.api_keys_text.insert(tk.END, self.config.get("api_keys_raw", ""))

        ttk.Label(frame, text="自定义API服务器地址 (兼容OpenAI):").pack(anchor="w", pady=(5, 0))
        self.api_endpoint_var = tk.StringVar(value=self.config.get("api_endpoint", ""))
        ttk.Entry(frame, textvariable=self.api_endpoint_var).pack(fill="x", pady=2)
        
        self.api_keys_text.bind("<<Modified>>", self._on_text_change)
        self.api_endpoint_var.trace_add("write", lambda *args: self._save_all_settings())
    
    def _create_ai_parameters_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 参数设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        
        self.model_var = tk.StringVar(value=self.config.get("model", "请先获取模型"))
        self.current_model_list = self.config.get("model_list", [])

        model_frame = ttk.Frame(frame)
        model_frame.pack(fill='x', pady=5)
        ttk.Label(model_frame, text="AI 模型:").pack(side='left', anchor='w')
        self.model_option_menu = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", values=self.current_model_list)
        if not self.current_model_list: self.model_option_menu.config(state="disabled")
        self.model_option_menu.pack(side='left', fill='x', expand=True, padx=5)
        self.fetch_models_button = ttk.Button(model_frame, text="获取模型列表", command=self._fetch_models_async, bootstyle="info-outline")
        self.fetch_models_button.pack(side='left')
        
        perf_frame = tk_ttk.LabelFrame(frame, text="性能与重试设置", padding="10")
        perf_frame.pack(fill='x', expand=True, pady=10)
        perf_frame.columnconfigure(1, weight=1)
        perf_frame.columnconfigure(3, weight=1)

        self._create_perf_spinbox(perf_frame, "翻译批处理大小:", "ai_batch_size", (1, 1000), "单次API请求包含的文本数量", is_float=False).grid(row=0, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(perf_frame, "最大并发线程数:", "ai_max_threads", (1, 16), "同时发送API请求的最大数量", is_float=False).grid(row=0, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(perf_frame, "最大重试次数:", "ai_max_retries", (0, 100), "单个翻译批次失败后的最大重试次数", is_float=False).grid(row=1, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(perf_frame, "速率限制冷却(s):", "ai_retry_rate_limit_cooldown", (1.0, 300.0), "因速率限制失败后，单个密钥的冷却时间", is_float=True).grid(row=1, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(perf_frame, "初始重试延迟(s):", "ai_retry_initial_delay", (0.1, 60.0), "常规错误第一次重试前的等待时间", is_float=True).grid(row=2, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(perf_frame, "最大重试延迟(s):", "ai_retry_max_delay", (1.0, 600.0), "指数退避策略中，最长的单次等待时间上限", is_float=True).grid(row=2, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(perf_frame, "延迟退避因子:", "ai_retry_backoff_factor", (1.0, 5.0), "指数退避的乘数，大于1以实现延迟递增", is_float=True).grid(row=3, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        
        self.prompt_text = scrolledtext.ScrolledText(frame, height=5, wrap="word")
        self.prompt_text.pack(fill='both', expand=True, pady=5)
        self.prompt_text.insert(tk.END, self.config.get("prompt", config_manager.DEFAULT_PROMPT))
        
        self.model_option_menu.bind('<<ComboboxSelected>>', lambda e: (self._save_all_settings(), self.model_option_menu.selection_clear()))
        self.prompt_text.bind("<<Modified>>", self._on_text_change)

    def _save_all_settings(self, *args):
        config = config_manager.load_config()
        config["output_dir"] = self.output_dir_var.get()
        config["community_dict_path"] = self.community_dict_var.get()
        config["community_pack_paths"] = list(self.packs_listbox.get(0, tk.END))
        
        config["use_origin_name_lookup"] = self.use_origin_name_lookup_var.get()
        config["use_github_proxy"] = self.use_proxy_var.get()
        config["pack_as_zip"] = self.pack_as_zip_var.get()
        config["log_level"] = self.log_level_var.get()

        raw_text = self.api_keys_text.get("1.0", "end-1c")
        text_with_newlines = raw_text.replace(',', '\n')
        config["api_keys"] = [key.strip() for key in text_with_newlines.split('\n') if key.strip()]
        config["api_keys_raw"] = raw_text
        config["api_endpoint"] = self.api_endpoint_var.get().strip()

        config["model"] = self.model_var.get()
        config["model_list"] = self.current_model_list
        config["prompt"] = self.prompt_text.get("1.0", tk.END).strip()
        
        
        
        spinbox_keys = [
            "ai_batch_size", "ai_max_threads", "ai_max_retries", 
            "ai_retry_rate_limit_cooldown", "ai_retry_initial_delay", 
            "ai_retry_max_delay", "ai_retry_backoff_factor"
        ]
        for key in spinbox_keys:
            var = getattr(self, f"{key}_var", None)
            if var:
                try:
                    config[key] = var.get()
                except (tk.TclError, ValueError):
                    config[key] = config_manager.DEFAULT_CONFIG.get(key)

        config_manager.save_config(config)
        self.config = config

    def _refresh_ui_from_config(self):
        # 更新UI控件的值
        self.output_dir_var.set(self.config.get("output_dir", ""))
        self.community_dict_var.set(self.config.get("community_dict_path", ""))
        self.use_origin_name_lookup_var.set(self.config.get("use_origin_name_lookup", True))
        self.use_proxy_var.set(self.config.get("use_github_proxy", True))
        self.pack_as_zip_var.set(self.config.get("pack_as_zip", False))
        self.log_level_var.set(self.config.get("log_level", "INFO"))
        
        self.api_keys_text.delete("1.0", tk.END)
        self.api_keys_text.insert(tk.END, self.config.get("api_keys_raw", ""))
        self.api_endpoint_var.set(self.config.get("api_endpoint", ""))
        
        self.model_var.set(self.config.get("model", ""))
        self.current_model_list = self.config.get("model_list", [])
        self.model_option_menu.config(values=self.current_model_list)
        
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert(tk.END, self.config.get("prompt", config_manager.DEFAULT_PROMPT))
        
        # 更新社区包列表
        self.packs_listbox.delete(0, tk.END)
        for path in self.config.get("community_pack_paths", []):
            self.packs_listbox.insert(tk.END, path)
        
        
        
        # 更新AI参数spinbox值
        spinbox_keys = [
            "ai_batch_size", "ai_max_threads", "ai_max_retries", 
            "ai_retry_rate_limit_cooldown", "ai_retry_initial_delay", 
            "ai_retry_max_delay", "ai_retry_backoff_factor"
        ]
        for key in spinbox_keys:
            var = getattr(self, f"{key}_var", None)
            if var:
                var.set(self.config.get(key, config_manager.DEFAULT_CONFIG.get(key)))

    def _create_path_entry(self, parent, label_text, var, browse_type, tooltip):
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill="x", pady=5)
        label = ttk.Label(row_frame, text=label_text, width=15)
        label.pack(side="left")
        custom_widgets.ToolTip(label, tooltip)
        entry = ttk.Entry(row_frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        var.trace_add("write", lambda *args: self._save_all_settings())
        browse_cmd = lambda: ui_utils.browse_directory(var) if browse_type == "directory" else ui_utils.browse_file(var)
        ttk.Button(row_frame, text="浏览...", command=browse_cmd, bootstyle="primary-outline").pack(side="left")

    def _create_perf_spinbox(self, parent, label_text, config_key, range_val, tooltip, is_float=False):
        container = ttk.Frame(parent)
        label = ttk.Label(container, text=label_text, width=15)
        label.pack(side='left')
        custom_widgets.ToolTip(label, tooltip)
        
        if is_float:
            var = tk.DoubleVar(value=self.config.get(config_key))
        else:
            var = tk.IntVar(value=self.config.get(config_key))
        setattr(self, f"{config_key}_var", var)
        
        spinbox = ttk.Spinbox(container, from_=range_val[0], to=range_val[1], textvariable=var, increment=0.1 if is_float else 1)
        spinbox.pack(side='left', fill='x', expand=True, padx=5)
        
        var.trace_add("write", self._save_all_settings)
        return container

    def _on_text_change(self, event=None):
        if event.widget.edit_modified():
            self._save_all_settings()
            event.widget.edit_modified(False)

    def _add_packs(self):
        paths = filedialog.askopenfilenames(title="选择一个或多个第三方汉化包", filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")] )
        for path in paths:
            if path not in self.packs_listbox.get(0, tk.END): self.packs_listbox.insert(tk.END, path)
        self._save_all_settings()

    def _remove_packs(self):
        selected_indices = self.packs_listbox.curselection()
        for i in reversed(selected_indices): self.packs_listbox.delete(i)
        self._save_all_settings()

    def _move_pack(self, direction):
        indices = self.packs_listbox.curselection()
        if not indices: return
        for i in sorted(list(indices), reverse=(direction < 0)):
            if 0 <= i + direction < self.packs_listbox.size():
                text = self.packs_listbox.get(i)
                self.packs_listbox.delete(i)
                self.packs_listbox.insert(i + direction, text)
                self.packs_listbox.selection_set(i + direction)
        self._save_all_settings()
        
    def _fetch_models_async(self):
        from services.ai_translator import AITranslator
        service_config = config_manager.load_config()
        api_keys = service_config.get('api_keys', [])
        if not api_keys or not any(api_keys):
            ui_utils.show_error("操作失败", "请先在“设置”中输入至少一个有效的API密钥")
            return
        
        self.fetch_models_button.config(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        from services.ai_translator import AITranslator
        try:
            service_config = config_manager.load_config()
            translator = AITranslator(service_config['api_keys'], service_config.get('api_endpoint'))
            model_list = translator.fetch_models()
            if self.winfo_exists(): self.after(0, self._update_ui_after_fetch, model_list)
        finally:
            if self.winfo_exists(): self.after(0, lambda: self.fetch_models_button.config(state="normal", text="获取模型列表"))

    def _update_ui_after_fetch(self, model_list):
        if model_list:
            self.current_model_list = model_list
            self.model_option_menu.config(values=self.current_model_list, state="readonly")
            if self.model_var.get() not in self.current_model_list and self.current_model_list:
                self.model_var.set(self.current_model_list[0])
            self._save_all_settings()
            ui_utils.show_info("成功", f"成功获取 {len(model_list)} 个模型！列表已保存")
        else:
            ui_utils.show_error("失败", "未能获取到任何可用模型\n请检查密钥、网络或服务器地址")

    def _check_and_update_dict_async(self):
        self.download_dict_button.config(state="disabled", text="检查中...")
        threading.Thread(target=self._dict_update_worker, daemon=True).start()

    def _get_remote_dict_info(self) -> dict | None:
        api_url = "https://api.github.com/repos/VM-Chinese-translate-group/i18n-Dict-Extender/releases/latest"
        try:
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            version = data.get("tag_name")
            url = next((asset.get("browser_download_url") for asset in data.get("assets", []) if asset.get("name") == "Dict-Sqlite.db"), None)
            if version and url: return {"version": version, "url": url}
        except Exception as e: logging.error(f"获取远程词典信息失败: {e}")
        return None

    def _dict_update_worker(self):
        try:
            remote_info = self._get_remote_dict_info()
            if not remote_info:
                self.after(0, lambda: ui_utils.show_error("检查失败", "无法获取远程词典版本信息。"))
                return

            local_version = self.config.get("last_dict_version", "0.0.0")
            if local_version == remote_info["version"]:
                self.after(0, lambda: ui_utils.show_info("检查完成", f"社区词典已是最新版本 ({local_version})。"))
                return

            if not messagebox.askyesno("发现新版本", f"发现新词典版本: {remote_info['version']} (当前: {local_version})。\n是否立即下载更新？"):
                return
            
            from gui.dialogs import DownloadProgressDialog
            progress_dialog = DownloadProgressDialog(self, title="下载社区词典")
            STABLE_PROXY_URL = "https://lucky-moth-20.deno.dev/"
            DEST_FILE = Path("Dict-Sqlite.db").resolve()
            
            use_proxy = self.config.get("use_github_proxy", True)
            final_url = f"{STABLE_PROXY_URL}{remote_info['url']}" if use_proxy else remote_info["url"]
            
            from utils import update_checker
            ok = update_checker.download_update(final_url, DEST_FILE, lambda s, p, sp: progress_dialog.update_progress(s, p, sp))
            progress_dialog.close_dialog()

            if ok:
                self.config["last_dict_version"] = remote_info["version"]
                self.config["community_dict_path"] = str(DEST_FILE)
                config_manager.save_config(self.config)
                self.after(0, lambda: self.community_dict_var.set(str(DEST_FILE)))
                self.after(0, lambda: ui_utils.show_info("更新成功", f"社区词典已更新到版本 {remote_info['version']}！"))
            else:
                self.after(0, lambda: ui_utils.show_error("下载失败", "下载新版词典时发生错误。"))
        finally:
            if self.winfo_exists():
                self.after(0, lambda: self.download_dict_button.config(state="normal", text="检查/更新"))