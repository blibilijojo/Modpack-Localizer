import tkinter as tk
from tkinter import scrolledtext, ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets
from services.ai_translator import AITranslator
import threading

class AISettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 创建变量
        self._create_variables()
        
        # 创建UI
        self._create_widgets()
    
    def _create_variables(self):
        # AI服务设置
        self.api_keys_text = None
        self.api_endpoint_var = tk.StringVar(value=self.config.get("api_endpoint", ""))
        
        # AI参数设置
        self.model_var = tk.StringVar(value=self.config.get("model", "请先获取模型"))
        self.current_model_list = self.config.get("model_list", [])
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.api_endpoint_var.trace_add("write", lambda *args: self.save_callback())
        self.model_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建AI服务设置
        self._create_ai_service_settings(main_frame)
        
        # 创建AI参数设置
        self._create_ai_parameters_settings(main_frame)
    
    def _create_ai_service_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 服务设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        
        ttk.Label(frame, text="API 密钥 (多个密钥可用 换行 或 , 分隔):").pack(anchor="w")
        self.api_keys_text = scrolledtext.ScrolledText(frame, height=3, wrap=tk.WORD)
        self.api_keys_text.pack(fill="x", expand=True, pady=2)
        self.api_keys_text.insert(tk.END, self.config.get("api_keys_raw", ""))
        
        ttk.Label(frame, text="自定义API服务器地址 (兼容OpenAI):").pack(anchor="w", pady=(5, 0))
        api_entry = ttk.Entry(frame, textvariable=self.api_endpoint_var, takefocus=False)
        api_entry.pack(fill="x", pady=2)
        # 防止自动选中文本
        api_entry.after_idle(api_entry.selection_clear)
        
        def _on_text_change(event):
            # 重置修改标志
            event.widget.edit_modified(False)
            # 保存所有设置
            self.save_callback()
        
        self.api_keys_text.bind("<<Modified>>", _on_text_change)
    
    def _create_ai_parameters_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 参数设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 模型设置分组
        model_frame = tk_ttk.LabelFrame(frame, text="模型设置", padding="10")
        model_frame.pack(fill='x', pady=5)
        model_frame.columnconfigure(1, weight=1)
        
        ttk.Label(model_frame, text="AI 模型:", width=12).grid(row=0, column=0, sticky="w", pady=5)
        self.model_option_menu = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", values=self.current_model_list)
        if not self.current_model_list: 
            self.model_option_menu.config(state="disabled")
        self.model_option_menu.grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        self.fetch_models_button = ttk.Button(model_frame, text="获取模型列表", command=self._fetch_models_async, bootstyle="info-outline")
        self.fetch_models_button.grid(row=0, column=2, pady=5, padx=5)
        
        # 性能设置分组
        perf_frame = tk_ttk.LabelFrame(frame, text="性能设置", padding="10")
        perf_frame.pack(fill='x', pady=5)
        perf_frame.columnconfigure(1, weight=1)
        perf_frame.columnconfigure(3, weight=1)
        
        self._create_perf_spinbox(perf_frame, "最大并发线程数:", "ai_max_threads", (1, 16), "同时发送API请求的最大数量", is_float=False).grid(row=0, column=0, columnspan=4, sticky="ew", pady=2)
        
        # 重试设置分组
        retry_frame = tk_ttk.LabelFrame(frame, text="重试设置", padding="10")
        retry_frame.pack(fill='x', pady=5)
        retry_frame.columnconfigure(1, weight=1)
        retry_frame.columnconfigure(3, weight=1)
        
        self._create_perf_spinbox(retry_frame, "最大重试次数:", "ai_max_retries", (0, 100), "单个翻译批次失败后的最大重试次数", is_float=False).grid(row=0, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(retry_frame, "速率限制冷却(s):", "ai_retry_rate_limit_cooldown", (1.0, 300.0), "因速率限制失败后，单个密钥的冷却时间", is_float=True).grid(row=0, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(retry_frame, "初始重试延迟(s):", "ai_retry_initial_delay", (0.1, 60.0), "常规错误第一次重试前的等待时间", is_float=True).grid(row=1, column=0, columnspan=2, sticky="ew", pady=2, padx=(0,10))
        self._create_perf_spinbox(retry_frame, "最大重试延迟(s):", "ai_retry_max_delay", (1.0, 600.0), "指数退避策略中，最长的单次等待时间上限", is_float=True).grid(row=1, column=2, columnspan=2, sticky="ew", pady=2)
        self._create_perf_spinbox(retry_frame, "延迟退避因子:", "ai_retry_backoff_factor", (1.0, 5.0), "指数退避的乘数，大于1以实现延迟递增", is_float=True).grid(row=2, column=0, columnspan=4, sticky="ew", pady=2)
        
        # 清除选中状态的事件处理
        def on_model_combobox_select(event):
            self.save_callback()
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_model_combobox_focus_in(event):
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_model_combobox_focus_out(event):
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        # 绑定事件
        self.model_option_menu.bind('<<ComboboxSelected>>', on_model_combobox_select)
        self.model_option_menu.bind('<FocusIn>', on_model_combobox_focus_in)
        self.model_option_menu.bind('<FocusOut>', on_model_combobox_focus_out)
    
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
        
        spinbox = ttk.Spinbox(container, from_=range_val[0], to=range_val[1], textvariable=var, increment=0.1 if is_float else 1, takefocus=False)
        spinbox.pack(side='left', fill='x', expand=True, padx=5)
        
        var.trace_add("write", self.save_callback)
        # 防止自动选中文本
        spinbox.after_idle(spinbox.selection_clear)
        return container
    
    def _fetch_models_async(self):
        service_config = self.config.copy()
        api_keys = service_config.get('api_keys', [])
        if not api_keys or not any(api_keys):
            ui_utils.show_error("操作失败", "请先在“设置”中输入至少一个有效的API密钥")
            return
        
        self.fetch_models_button.config(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()
    
    def _fetch_worker(self):
        try:
            service_config = self.config.copy()
            translator = AITranslator(service_config['api_keys'], service_config.get('api_endpoint'))
            model_list = translator.fetch_models()
            if self.parent.winfo_exists():
                self.parent.after(0, self._update_ui_after_fetch, model_list)
        finally:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.fetch_models_button.config(state="normal", text="获取模型列表"))
    
    def _update_ui_after_fetch(self, model_list):
        if model_list:
            self.current_model_list = model_list
            self.model_option_menu.config(values=self.current_model_list, state="readonly")
            if self.model_var.get() not in self.current_model_list and self.current_model_list:
                self.model_var.set(self.current_model_list[0])
            self.save_callback()
            ui_utils.show_info("成功", f"成功获取 {len(model_list)} 个模型！列表已保存")
        else:
            ui_utils.show_error("失败", "未能获取到任何可用模型\n请检查密钥、网络或服务器地址")
    
    def get_config(self):
        config = {
            "api_endpoint": self.api_endpoint_var.get().strip(),
            "model": self.model_var.get(),
            "model_list": self.current_model_list
        }
        
        # 处理API密钥
        if self.api_keys_text:
            raw_text = self.api_keys_text.get("1.0", "end-1c")
            text_with_newlines = raw_text.replace(',', '\n')
            config["api_keys"] = [key.strip() for key in text_with_newlines.split('\n') if key.strip()]
            config["api_keys_raw"] = raw_text
        
        # 处理性能参数
        spinbox_keys = [
            "ai_max_threads", "ai_max_retries", 
            "ai_retry_rate_limit_cooldown", "ai_retry_initial_delay", 
            "ai_retry_max_delay", "ai_retry_backoff_factor"
        ]
        for key in spinbox_keys:
            var = getattr(self, f"{key}_var", None)
            if var:
                try:
                    config[key] = var.get()
                except (tk.TclError, ValueError):
                    pass
        
        return config
