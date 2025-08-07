import tkinter as tk
import ttkbootstrap as ttk
from tkinter import scrolledtext
import threading
from gui import ui_utils
from services.gemini_translator import GeminiTranslator
from utils import config_manager
from gui.custom_widgets import ToolTip

class TabAiParameters:
    def __init__(self, parent):
        self.frame = ttk.Frame(parent, padding="10")
        self.root = parent.winfo_toplevel()
        
        self.config = config_manager.load_config()
        self.model_var = tk.StringVar()
        self.use_grounding_var = tk.BooleanVar()
        self.current_model_list = []

        param_frame = ttk.LabelFrame(self.frame, text="AI 参数设置 (调整翻译行为)", padding=10)
        param_frame.pack(fill="both", expand=True)

        model_frame = ttk.Frame(param_frame)
        model_frame.pack(fill='x', pady=5)
        model_label = ttk.Label(model_frame, text="AI 模型:")
        model_label.pack(side='left', anchor='w')
        ToolTip(model_label, "选择用于翻译的AI模型\n点击右侧按钮获取可用模型列表")
        self.model_option_menu = ttk.Combobox(model_frame, textvariable=self.model_var, state="disabled")
        self.model_option_menu.pack(side='left', fill='x', expand=True, padx=5)
        self.fetch_models_button = ttk.Button(model_frame, text="获取模型列表", command=self._fetch_models_async, bootstyle="info-outline")
        self.fetch_models_button.pack(side='left')
        
        adv_modes_frame = ttk.Frame(param_frame)
        adv_modes_frame.pack(fill='x', pady=5)

        grounding_check = ttk.Checkbutton(adv_modes_frame, text="启用接地翻译模式 (联网搜索，提高对新术语的准确性)", variable=self.use_grounding_var, bootstyle="primary")
        grounding_check.pack(side="left", anchor='w')
        ToolTip(grounding_check, "开启后，AI在翻译前会先使用Google搜索相关信息\n这能极大提高对新模组、特殊物品名的翻译质量，但可能会稍稍增加翻译时间")
        
        perf_frame = ttk.LabelFrame(param_frame, text="性能与重试设置", padding="10")
        perf_frame.pack(fill='x', expand=True, pady=10)
        perf_frame.columnconfigure(1, weight=1)
        perf_frame.columnconfigure(3, weight=1)
        self._create_perf_spinbox(perf_frame, "翻译批处理大小:", "ai_batch_size", 50, (1, 1000), "单次API请求包含的文本数量").grid(row=0, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(perf_frame, "最大并发线程数:", "ai_max_threads", 4, (1, 16), "同时发送API请求的最大数量").grid(row=0, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(perf_frame, "最大重试次数:", "ai_max_retries", 3, (0, 100), "单个翻译批次失败后的最大重试次数").grid(row=1, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(perf_frame, "重试间隔(秒):", "ai_retry_interval", 2, (0, 60), "每次重试之间的等待时间（秒）").grid(row=1, column=2, columnspan=2, sticky="ew", pady=2)
        
        prompt_frame = ttk.LabelFrame(param_frame, text="AI 翻译提示词 (Prompt) - 当前为 JSON 输出模式", padding="10")
        prompt_frame.pack(fill='both', expand=True, pady=5)
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8, wrap="word")
        self.prompt_text.pack(fill='both', expand=True, side='left', pady=2)
        
        restore_button = ttk.Button(prompt_frame, text="恢复默认", command=self._restore_default_prompt, bootstyle="warning-outline")
        restore_button.pack(side='top', padx=(0,5), anchor='ne')
        ToolTip(restore_button, "将提示词恢复到程序内置的默认值")

        self._load_settings_to_ui()
        self._bind_events()

    def _load_settings_to_ui(self):
        self.config = config_manager.load_config()
        self.use_grounding_var.set(self.config.get("use_grounding", False))
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert(tk.END, self.config.get("prompt", config_manager.DEFAULT_PROMPT))
        self.prompt_text.edit_modified(False)
        for key, default_val in [("ai_batch_size", 50), ("ai_max_threads", 4), ("ai_max_retries", 3), ("ai_retry_interval", 2)]:
            var = getattr(self, f"{key}_var", None)
            if var:
                var.set(self.config.get(key, default_val))
        self._update_model_options(self.config.get("model_list", []))

    def _bind_events(self):
        self.use_grounding_var.trace_add("write", self._auto_save)
        self.model_option_menu.bind('<<ComboboxSelected>>', lambda e: (self._auto_save(), self.model_option_menu.selection_clear()))
        self.model_option_menu.bind('<MouseWheel>', lambda e: "break")
        self.prompt_text.bind("<<Modified>>", self._on_prompt_text_change)
        for key in ["ai_batch_size", "ai_max_threads", "ai_max_retries", "ai_retry_interval"]:
            var = getattr(self, f"{key}_var", None)
            if var:
                var.trace_add("write", self._auto_save)

    def _auto_save(self, *args):
        self.get_and_save_settings()

    def _on_prompt_text_change(self, event=None):
        if self.prompt_text.edit_modified():
            self.get_and_save_settings()
            self.prompt_text.edit_modified(False)

    def _restore_default_prompt(self):
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert(tk.END, config_manager.DEFAULT_PROMPT)

    def get_and_save_settings(self) -> dict:
        def get_spinbox_val(var_name, default_key):
            try:
                val = getattr(self, var_name).get()
                return val
            except (tk.TclError, ValueError):
                default_val = config_manager.DEFAULT_CONFIG.get(default_key)
                getattr(self, var_name).set(default_val)
                return default_val

        param_settings = {
            "model": self.model_var.get(),
            "model_list": self.current_model_list,
            "prompt": self.prompt_text.get("1.0", tk.END).strip(),
            "use_grounding": self.use_grounding_var.get(),
            "ai_batch_size": get_spinbox_val('ai_batch_size_var', 'ai_batch_size'),
            "ai_max_threads": get_spinbox_val('ai_max_threads_var', 'ai_max_threads'),
            "ai_max_retries": get_spinbox_val('ai_max_retries_var', 'ai_max_retries'),
            "ai_retry_interval": get_spinbox_val('ai_retry_interval_var', 'ai_retry_interval'),
        }
        
        full_config = config_manager.load_config()
        full_config.update(param_settings)
        config_manager.save_config(full_config)
        self.config = full_config
        return param_settings

    def _create_perf_spinbox(self, parent, label_text, config_key, default_val, range_val, tooltip):
        container = ttk.Frame(parent)
        label = ttk.Label(container, text=label_text, width=15); label.pack(side='left')
        ToolTip(label, tooltip)
        var = tk.IntVar()
        setattr(self, f"{config_key}_var", var)
        spinbox = ttk.Spinbox(container, from_=range_val[0], to=range_val[1], textvariable=var)
        spinbox.pack(side='left', fill='x', expand=True, padx=5)
        spinbox.bind('<MouseWheel>', lambda e: "break")
        return container

    def _fetch_models_async(self):
        service_config = config_manager.load_config()
        api_keys = service_config.get('api_keys', [])
        if not api_keys or not any(api_keys):
            ui_utils.show_error("操作失败", "请先在“AI 服务”选项卡中输入至少一个有效的API密钥")
            return
        self.fetch_models_button.config(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            service_config = config_manager.load_config()
            translator = GeminiTranslator(service_config['api_keys'], service_config.get('api_endpoint'))
            model_list = translator.fetch_models()
            self.frame.after(0, self._update_ui_after_fetch, model_list)
        finally:
            self.frame.after(0, lambda: self.fetch_models_button.config(state="normal", text="获取模型列表"))

    def _update_ui_after_fetch(self, model_list):
        if model_list:
            self._update_model_options(model_list)
            self.get_and_save_settings()
            ui_utils.show_info("成功", f"成功获取 {len(model_list)} 个模型！列表已保存")
        else:
            ui_utils.show_error("失败", "未能获取到任何可用模型\n请检查密钥、网络或服务器地址")

    def _update_model_options(self, model_list: list[str]):
        self.current_model_list = model_list if model_list else []
        self.model_option_menu.config(values=self.current_model_list)
        if not self.current_model_list:
            self.model_option_menu.config(state="disabled")
        else:
            self.model_option_menu.config(state="readonly")
            
        saved_model = self.config.get("model")
        if saved_model:
            self.model_var.set(saved_model)
        elif self.current_model_list:
            self.model_var.set(self.current_model_list[0])
        else:
            self.model_var.set("请先获取模型")