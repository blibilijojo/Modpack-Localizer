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
        self.api_services = self.config.get("api_services", [])
        self.current_service_index = -1  # 跟踪当前选中的服务索引
        self.is_loading_service = False  # 标志：是否正在加载服务设置
        
        # AI参数设置
        self.model_var = tk.StringVar(value=self.config.get("model", "请先获取模型"))
        self.current_model_list = self.config.get("model_list", [])
        
        # 初始化性能参数变量
        self.ai_max_threads_var = tk.IntVar(value=self.config.get("ai_max_threads", 4))
        self.ai_max_retries_var = tk.IntVar(value=self.config.get("ai_max_retries", 3))
        self.ai_retry_rate_limit_cooldown_var = tk.DoubleVar(value=self.config.get("ai_retry_rate_limit_cooldown", 60.0))
        self.ai_retry_initial_delay_var = tk.DoubleVar(value=self.config.get("ai_retry_initial_delay", 2.0))
        self.ai_retry_max_delay_var = tk.DoubleVar(value=self.config.get("ai_retry_max_delay", 120.0))
        self.ai_retry_backoff_factor_var = tk.DoubleVar(value=self.config.get("ai_retry_backoff_factor", 2.0))
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.model_var.trace_add("write", lambda *args: self.save_callback())
        
        # 绑定性能参数变量变化事件
        self.ai_max_threads_var.trace_add("write", lambda *args: self.save_callback())
        self.ai_max_retries_var.trace_add("write", lambda *args: self.save_callback())
        self.ai_retry_rate_limit_cooldown_var.trace_add("write", lambda *args: self.save_callback())
        self.ai_retry_initial_delay_var.trace_add("write", lambda *args: self.save_callback())
        self.ai_retry_max_delay_var.trace_add("write", lambda *args: self.save_callback())
        self.ai_retry_backoff_factor_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建选项卡控件
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 创建服务设置选项卡
        service_tab = ttk.Frame(notebook)
        notebook.add(service_tab, text="服务设置")
        self._create_ai_service_settings(service_tab)
        
        # 创建参数设置选项卡
        params_tab = ttk.Frame(notebook)
        notebook.add(params_tab, text="参数设置")
        self._create_ai_parameters_settings(params_tab)
    
    def _create_ai_service_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 服务设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        
        # 服务列表
        ttk.Label(frame, text="API 服务列表:").pack(anchor="w")
        
        # 服务列表框架
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=2)
        
        # 创建服务列表
        self.service_listbox = tk.Listbox(list_frame, height=5)
        self.service_listbox.pack(side="left", fill="both", expand=True, padx=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.service_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.service_listbox.config(yscrollcommand=scrollbar.set)
        
        # 添加服务顺序调整按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=5)
        
        # 上移按钮
        up_button = ttk.Button(button_frame, text="上移", command=self._move_service_up, bootstyle="info-outline")
        up_button.pack(side="left", padx=5)
        
        # 下移按钮
        down_button = ttk.Button(button_frame, text="下移", command=self._move_service_down, bootstyle="info-outline")
        down_button.pack(side="left", padx=5)
        
        # 服务详情框架
        detail_frame = ttk.Frame(frame)
        detail_frame.pack(fill="x", pady=5)
        
        # 服务名称输入
        ttk.Label(detail_frame, text="服务名称:").pack(anchor="w")
        self.service_name_var = tk.StringVar(value="新服务")
        name_entry = ttk.Entry(detail_frame, textvariable=self.service_name_var, takefocus=False)
        name_entry.pack(fill="x", pady=2)
        
        # 服务器地址输入
        ttk.Label(detail_frame, text="服务器地址:").pack(anchor="w")
        self.service_endpoint_var = tk.StringVar()
        endpoint_entry = ttk.Entry(detail_frame, textvariable=self.service_endpoint_var, takefocus=False)
        endpoint_entry.pack(fill="x", pady=2)
        
        # API密钥输入
        ttk.Label(detail_frame, text="API 密钥 (多个密钥可用 换行 或 , 分隔):").pack(anchor="w")
        self.service_keys_text = scrolledtext.ScrolledText(detail_frame, height=2, wrap=tk.WORD)
        self.service_keys_text.pack(fill="x", expand=True, pady=2)
        
        # 模型选择
        ttk.Label(detail_frame, text="默认模型:").pack(anchor="w", pady=(5, 0))
        self.service_model_var = tk.StringVar(value="请先获取模型")
        self.service_model_option_menu = ttk.Combobox(detail_frame, textvariable=self.service_model_var, state="readonly", values=self.current_model_list)
        if not self.current_model_list: 
            self.service_model_option_menu.config(state="disabled")
        self.service_model_option_menu.pack(fill="x", pady=2)
        
        # 线程上限设置
        ttk.Label(detail_frame, text="线程上限:").pack(anchor="w", pady=(5, 0))
        self.service_max_threads_var = tk.StringVar(value="4")
        max_threads_entry = ttk.Entry(detail_frame, textvariable=self.service_max_threads_var, takefocus=False)
        max_threads_entry.pack(fill="x", pady=2)
        
        # 绑定事件
        def on_service_model_combobox_select(event):
            # 更新当前服务
            self._update_current_service()
            # 立即取消文字选中状态
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_service_model_combobox_focus_in(event):
            # 立即取消文字选中状态
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_service_model_combobox_focus_out(event):
            # 立即取消文字选中状态
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        self.service_model_option_menu.bind('<<ComboboxSelected>>', on_service_model_combobox_select)
        self.service_model_option_menu.bind('<FocusIn>', on_service_model_combobox_focus_in)
        self.service_model_option_menu.bind('<FocusOut>', on_service_model_combobox_focus_out)
        
        # 绑定线程上限变化事件
        def on_max_threads_change(*args):
            self._update_current_service()
        
        self.service_max_threads_var.trace_add("write", on_max_threads_change)
        
        # 绑定服务名称变化事件
        def on_name_change(*args):
            self._update_current_service()
        
        self.service_name_var.trace_add("write", on_name_change)
        
        # 绑定服务器地址变化事件
        def on_endpoint_change(*args):
            self._update_current_service()
        
        self.service_endpoint_var.trace_add("write", on_endpoint_change)
        
        # 绑定密钥文本变化事件
        def on_keys_text_change(event):
            event.widget.edit_modified(False)
            self._update_current_service()
        
        self.service_keys_text.bind("<<Modified>>", on_keys_text_change)
        
        # 按钮框架
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=5)
        
        # 添加服务按钮
        add_button = ttk.Button(button_frame, text="添加服务", command=self._add_service, bootstyle="success-outline")
        add_button.pack(side="left", padx=5)
        
        # 删除服务按钮
        delete_button = ttk.Button(button_frame, text="删除服务", command=self._delete_service, bootstyle="danger-outline")
        delete_button.pack(side="left", padx=5)
        
        # 清空按钮
        clear_button = ttk.Button(button_frame, text="清空", command=self._clear_service_fields, bootstyle="secondary-outline")
        clear_button.pack(side="left", padx=5)
        
        # 获取模型按钮
        self.fetch_models_button = ttk.Button(button_frame, text="获取模型", command=self._fetch_models_async, bootstyle="info-outline")
        self.fetch_models_button.pack(side="left", padx=5)
        
        # 填充服务列表
        self._populate_service_list()
        
        # 绑定列表选择事件
        self.service_listbox.bind("<<ListboxSelect>>", self._on_service_select)
        

    
    def _populate_service_list(self):
        # 清空列表
        self.service_listbox.delete(0, tk.END)
        
        # 填充服务列表
        for i, service in enumerate(self.api_services):
            name = service.get("name", "").strip() or f"服务{i+1}"
            endpoint = service.get("endpoint", "").strip() or "默认OpenAI"
            keys_count = len(service.get("keys", []))
            max_threads = service.get("max_threads", 4)
            self.service_listbox.insert(tk.END, f"{i+1}. {name} ({endpoint}, {keys_count}个密钥, 线程上限:{max_threads})")
    
    def _add_service(self):
        # 保存当前的选中索引
        current_selected_index = self.current_service_index
        
        # 创建一个新的空服务，使用默认名称
        new_service = {
            "name": f"新服务{len(self.api_services) + 1}",
            "endpoint": "",
            "keys": [],
            "keys_raw": "",
            "model": "请先获取模型",
            "max_threads": 4,  # 使用默认值
            "model_list": []  # 每个服务独立的模型列表
        }
        self.api_services.append(new_service)
        self._populate_service_list()
        
        # 恢复当前的选中状态
        if current_selected_index != -1 and current_selected_index < len(self.api_services):
            self.service_listbox.selection_set(current_selected_index)
            self.service_listbox.activate(current_selected_index)
            self.current_service_index = current_selected_index
        
        # 保存设置
        self.save_callback()
    
    def _update_service(self):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            return
        
        index = selected_index[0]
        
        # 获取服务信息
        endpoint = self.service_endpoint_var.get().strip()
        keys_text = self.service_keys_text.get("1.0", "end-1c")
        model = self.service_model_var.get()
        
        # 处理密钥
        text_with_newlines = keys_text.replace(',', '\n')
        keys = [key.strip() for key in text_with_newlines.split('\n') if key.strip()]
        
        # 更新服务
        if keys:
            self.api_services[index] = {
                "endpoint": endpoint,
                "keys": keys,
                "keys_raw": keys_text,
                "model": model
            }
            self._populate_service_list()
            self.save_callback()
    
    def _delete_service(self):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            return
        
        index = selected_index[0]
        
        # 删除服务
        self.api_services.pop(index)
        self._populate_service_list()
        self._clear_service_fields()
        self.save_callback()
    
    def _move_service_up(self):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            return
        
        index = selected_index[0]
        if index > 0:
            # 交换服务顺序
            self.api_services[index], self.api_services[index - 1] = self.api_services[index - 1], self.api_services[index]
            self._populate_service_list()
            # 重新选中移动后的服务
            self.service_listbox.selection_set(index - 1)
            self.service_listbox.activate(index - 1)
            self.service_listbox.see(index - 1)
            # 更新当前服务索引
            self.current_service_index = index - 1
            self.save_callback()
    
    def _move_service_down(self):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            return
        
        index = selected_index[0]
        if index < len(self.api_services) - 1:
            # 交换服务顺序
            self.api_services[index], self.api_services[index + 1] = self.api_services[index + 1], self.api_services[index]
            self._populate_service_list()
            # 重新选中移动后的服务
            self.service_listbox.selection_set(index + 1)
            self.service_listbox.activate(index + 1)
            self.service_listbox.see(index + 1)
            # 更新当前服务索引
            self.current_service_index = index + 1
            self.save_callback()
    
    def _update_current_service(self):
        # 检查是否正在加载服务设置，如果是则跳过
        if self.is_loading_service:
            return
        
        # 使用 current_service_index 而不是 curselection()
        # 这样在加载新服务设置时就不会触发不必要的保存操作
        if self.current_service_index == -1 or self.current_service_index >= len(self.api_services):
            return
        
        index = self.current_service_index
        # 更新当前服务的设置
        service = self.api_services[index]
        service["name"] = self.service_name_var.get().strip() or "新服务"
        service["endpoint"] = self.service_endpoint_var.get().strip()
        keys_text = self.service_keys_text.get("1.0", "end-1c")
        service["keys"] = [key.strip() for key in keys_text.split('\n') if key.strip()]
        service["keys_raw"] = keys_text
        service["model"] = self.service_model_var.get()
        
        # 安全获取线程上限值，处理空值或非数字的情况
        try:
            max_threads_str = self.service_max_threads_var.get().strip()
            service["max_threads"] = int(max_threads_str) if max_threads_str else 4
        except (tk.TclError, ValueError):
            service["max_threads"] = 4  # 使用默认值
        
        # 更新服务列表显示并保持选择状态
        self._populate_service_list()
        # 恢复选择状态
        if 0 <= index < len(self.api_services):
            self.service_listbox.selection_clear(0, tk.END)  # 先清除所有选择
            self.service_listbox.selection_set(index)  # 设置新的选择
            self.service_listbox.activate(index)  # 激活选中项
            self.service_listbox.see(index)  # 确保选中项可见
        # 保存设置
        self.save_callback()

    def _clear_service_fields(self):
        # 清空服务字段
        self.service_name_var.set("新服务")
        self.service_endpoint_var.set("")
        self.service_keys_text.delete("1.0", tk.END)
        self.service_model_var.set("没选中API服务")
        self.service_max_threads_var.set(4)
        self.service_model_option_menu.config(values=[], state="disabled")
    
    def _on_service_select(self, event):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            return
        
        index = selected_index[0]
        
        # 如果当前有选中的服务，先保存其设置
        if self.current_service_index != -1 and 0 <= self.current_service_index < len(self.api_services):
            # 保存当前服务的设置
            service = self.api_services[self.current_service_index]
            service["name"] = self.service_name_var.get().strip() or "新服务"
            service["endpoint"] = self.service_endpoint_var.get().strip()
            keys_text = self.service_keys_text.get("1.0", "end-1c")
            service["keys"] = [key.strip() for key in keys_text.split('\n') if key.strip()]
            service["keys_raw"] = keys_text
            service["model"] = self.service_model_var.get()
            service["max_threads"] = self.service_max_threads_var.get()
        
        # 获取新选中的服务信息
        service = self.api_services[index]
        
        # 设置加载标志，避免在加载过程中触发不必要的保存操作
        self.is_loading_service = True
        
        try:
            # 填充服务字段
            self.service_name_var.set(service.get("name", "新服务"))
            self.service_endpoint_var.set(service.get("endpoint", ""))
            self.service_keys_text.delete("1.0", tk.END)
            self.service_keys_text.insert(tk.END, service.get("keys_raw", ""))
            self.service_model_var.set(service.get("model", "请先获取模型"))
            self.service_max_threads_var.set(str(service.get("max_threads", 4)))
            
            # 加载服务的模型列表
            model_list = service.get("model_list", [])
            if model_list:
                self.service_model_option_menu.config(values=model_list, state="readonly")
            else:
                self.service_model_option_menu.config(values=[], state="disabled")
        finally:
            # 无论如何都要清除加载标志
            self.is_loading_service = False
        
        # 更新当前服务索引
        self.current_service_index = index
        
        # 保存设置
        self.save_callback()
    
    def _create_ai_parameters_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 参数设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        frame.columnconfigure(0, weight=1)
        
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
    
    def _create_perf_spinbox(self, parent, label_text, config_key, range_val, tooltip, is_float=False):
        container = ttk.Frame(parent)
        label = ttk.Label(container, text=label_text, width=15)
        label.pack(side='left')
        custom_widgets.ToolTip(label, tooltip)
        
        # 使用已初始化的变量
        var_name = f"{config_key}_var"
        var = getattr(self, var_name)
        
        spinbox = ttk.Spinbox(container, from_=range_val[0], to=range_val[1], textvariable=var, increment=0.1 if is_float else 1, takefocus=False)
        spinbox.pack(side='left', fill='x', expand=True, padx=5)
        
        # 防止自动选中文本
        spinbox.after_idle(spinbox.selection_clear)
        return container
    
    def _fetch_models_async(self):
        # 获取选中的服务索引
        selected_index = self.service_listbox.curselection()
        if not selected_index:
            ui_utils.show_error("操作失败", "请先选择一个服务")
            return
        
        index = selected_index[0]
        service = self.api_services[index]
        
        # 检查是否有有效的密钥
        keys = service.get('keys', [])
        if not keys or not any(keys):
            ui_utils.show_error("操作失败", "请先输入至少一个有效的API密钥")
            return
        
        # 创建临时服务配置
        service_config = {
            "endpoint": service.get("endpoint", ""),
            "keys": service.get("keys", []),
            "keys_raw": service.get("keys_raw", "")
        }
        
        # 获取模型列表
        self.fetch_models_button.config(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_worker, args=(index, service_config), daemon=True).start()

    def _fetch_worker(self, service_index, service_config):
        try:
            # 创建仅包含当前服务的api_services列表
            api_services = [{"endpoint": service_config.get("endpoint"), "keys": service_config.get("keys", [])}]
            translator = AITranslator(api_services)
            model_list = translator.fetch_models()
            if self.parent.winfo_exists():
                self.parent.after(0, self._update_ui_after_fetch, service_index, model_list)
        finally:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.fetch_models_button.config(state="normal", text="获取模型"))

    def _update_ui_after_fetch(self, service_index, model_list):
        if model_list:
            # 更新指定服务的模型列表
            if 0 <= service_index < len(self.api_services):
                self.api_services[service_index]["model_list"] = model_list
                
                # 如果当前选中的是该服务，更新服务模型选择下拉框
                selected_index = self.service_listbox.curselection()
                if selected_index and selected_index[0] == service_index:
                    self.service_model_var.set(model_list[0] if model_list else "请先获取模型")
                    self.service_model_option_menu.config(values=model_list, state="readonly")
                
                self.save_callback()
                ui_utils.show_info("成功", f"成功获取 {len(model_list)} 个模型！列表已保存")
        else:
            ui_utils.show_error("失败", "未能获取到任何可用模型\n请检查密钥、网络或服务器地址")
    
    def get_config(self):
        config = {
            "api_services": self.api_services
        }
        
        # 处理性能参数
        performance_keys = [
            "ai_max_threads", "ai_max_retries", 
            "ai_retry_rate_limit_cooldown", "ai_retry_initial_delay", 
            "ai_retry_max_delay", "ai_retry_backoff_factor"
        ]
        for key in performance_keys:
            var = getattr(self, f"{key}_var", None)
            if var:
                try:
                    config[key] = var.get()
                except (tk.TclError, ValueError):
                    # 使用配置中的现有值或默认值
                    config[key] = self.config.get(key, 0)
        
        # 处理批次处理参数
        batch_keys = [
            "ai_batch_size", "ai_batch_count", "ai_batch_items", "ai_batch_words"
        ]
        for key in batch_keys:
            if key in self.config:
                config[key] = self.config[key]
        
        # 处理其他AI相关参数
        other_ai_keys = [
            "prompt", "use_grounding"
        ]
        for key in other_ai_keys:
            if key in self.config:
                config[key] = self.config[key]
        
        return config
