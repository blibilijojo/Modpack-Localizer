import tkinter as tk
from tkinter import scrolledtext, ttk as tk_ttk, messagebox
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets
from services.ai_translator import AITranslator
import threading

class AISettings:
    """AI翻译设置组件"""
    
    # 服务模板
    SERVICE_TEMPLATES = {
        "OpenAI": {
            "endpoint": "https://api.openai.com/v1",
            "name": "OpenAI"
        },
        "Gemini": {
            "endpoint": "https://generativelanguage.googleapis.com/v1beta",
            "name": "Gemini"
        },
        "Claude": {
            "endpoint": "https://api.anthropic.com/v1",
            "name": "Claude"
        },
        "自定义": {
            "endpoint": "",
            "name": "自定义服务"
        }
    }
    
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 服务列表
        self.api_services = self.config.get("api_services", [])
        self.current_service_index = -1
        self.is_loading_service = False
        self._saving_service = False
        
        # 创建变量
        self._create_variables()
        
        # 创建UI
        self._create_widgets()
        
        # 初始化
        self._populate_service_list()
    
    def _create_variables(self):
        """创建所有变量"""
        # 性能参数变量
        self.ai_max_threads_var = tk.IntVar(value=self.config.get("ai_max_threads", 4))
        self.ai_max_retries_var = tk.IntVar(value=self.config.get("ai_max_retries", 3))
        self.ai_retry_rate_limit_cooldown_var = tk.DoubleVar(value=self.config.get("ai_retry_rate_limit_cooldown", 60.0))
        self.ai_retry_initial_delay_var = tk.DoubleVar(value=self.config.get("ai_retry_initial_delay", 2.0))
        self.ai_retry_max_delay_var = tk.DoubleVar(value=self.config.get("ai_retry_max_delay", 120.0))
        self.ai_retry_backoff_factor_var = tk.DoubleVar(value=self.config.get("ai_retry_backoff_factor", 2.0))
        
        # 绑定变量变化事件
        self._bind_variables()
    
    def _bind_variables(self):
        """绑定变量变化事件"""
        variables = [
            self.ai_max_threads_var, self.ai_max_retries_var,
            self.ai_retry_rate_limit_cooldown_var, self.ai_retry_initial_delay_var,
            self.ai_retry_max_delay_var, self.ai_retry_backoff_factor_var
        ]
        
        for var in variables:
            var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        """创建主界面"""
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建选项卡控件
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 创建服务管理选项卡
        service_tab = ttk.Frame(notebook)
        notebook.add(service_tab, text=" 服务管理 ")
        self._create_service_management_tab(service_tab)
        
        # 创建参数设置选项卡
        params_tab = ttk.Frame(notebook)
        notebook.add(params_tab, text=" 参数设置 ")
        self._create_parameters_tab(params_tab)
    
    def _create_service_management_tab(self, parent):
        """创建服务管理选项卡"""
        # 使用PanedWindow实现左右分栏
        paned = tk_ttk.PanedWindow(parent, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 左侧：服务列表
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        self._create_service_list_panel(left_frame)
        
        # 右侧：服务详情
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        self._create_service_detail_panel(right_frame)
    
    def _create_service_list_panel(self, parent):
        """创建服务列表面板"""
        frame = tk_ttk.LabelFrame(parent, text="API 服务列表", padding="5")
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 工具栏
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 5))
        
        # 添加服务按钮
        add_btn = ttk.Button(toolbar, text="添加服务", command=self._show_add_service_menu, bootstyle="success-outline")
        add_btn.pack(side="left", padx=2)
        
        # 删除服务按钮
        delete_btn = ttk.Button(toolbar, text="删除", command=self._delete_service, bootstyle="danger-outline")
        delete_btn.pack(side="left", padx=2)
        
        # 刷新按钮
        refresh_btn = ttk.Button(toolbar, text="刷新", command=self._populate_service_list, bootstyle="info-outline")
        refresh_btn.pack(side="left", padx=2)
        
        # 服务列表框架
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True)
        
        # 创建Treeview显示服务列表
        columns = ("name", "status", "threads")
        self.service_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题
        self.service_tree.heading("name", text="服务名称")
        self.service_tree.heading("status", text="状态")
        self.service_tree.heading("threads", text="线程数")
        
        # 设置列宽
        self.service_tree.column("name", width=120, minwidth=80)
        self.service_tree.column("status", width=60, minwidth=40)
        self.service_tree.column("threads", width=60, minwidth=40)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.service_tree.yview)
        self.service_tree.configure(yscrollcommand=scrollbar.set)
        
        self.service_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定选择事件
        self.service_tree.bind("<<TreeviewSelect>>", self._on_service_tree_select)
        
        # 排序按钮框架
        order_frame = ttk.Frame(frame)
        order_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Button(order_frame, text="上移", command=self._move_service_up, bootstyle="info-outline").pack(side="left", padx=2)
        ttk.Button(order_frame, text="下移", command=self._move_service_down, bootstyle="info-outline").pack(side="left", padx=2)
    
    def _create_service_detail_panel(self, parent):
        """创建服务详情面板"""
        self.detail_frame = tk_ttk.LabelFrame(parent, text="服务详情", padding="10")
        self.detail_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 初始提示
        self.no_selection_label = ttk.Label(self.detail_frame, text="请从左侧列表选择一个服务", font=("", 10))
        self.no_selection_label.pack(expand=True)
        
        # 服务详情容器（初始隐藏）
        self.detail_container = ttk.Frame(self.detail_frame)
        
        # 服务名称
        name_frame = ttk.Frame(self.detail_container)
        name_frame.pack(fill="x", pady=5)
        ttk.Label(name_frame, text="服务名称:", width=12).pack(side="left")
        self.service_name_var = tk.StringVar()
        name_entry = ttk.Entry(name_frame, textvariable=self.service_name_var, takefocus=False)
        name_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        # API地址
        endpoint_frame = ttk.Frame(self.detail_container)
        endpoint_frame.pack(fill="x", pady=5)
        ttk.Label(endpoint_frame, text="API地址:", width=12).pack(side="left")
        self.service_endpoint_var = tk.StringVar()
        endpoint_entry = ttk.Entry(endpoint_frame, textvariable=self.service_endpoint_var, takefocus=False)
        endpoint_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        # API密钥
        keys_frame = ttk.Frame(self.detail_container)
        keys_frame.pack(fill="x", pady=5)
        ttk.Label(keys_frame, text="API密钥:", width=12).pack(anchor="nw")
        
        keys_help = ttk.Label(keys_frame, text="(多个密钥用换行或逗号分隔)", font=("", 8), bootstyle="secondary")
        keys_help.pack(anchor="w")
        
        self.service_keys_text = scrolledtext.ScrolledText(keys_frame, height=4, wrap=tk.WORD)
        self.service_keys_text.pack(fill="x", pady=2)
        
        # 模型选择
        model_frame = ttk.Frame(self.detail_container)
        model_frame.pack(fill="x", pady=5)
        ttk.Label(model_frame, text="翻译模型:", width=12).pack(side="left")
        self.service_model_var = tk.StringVar(value="请先获取模型")
        self.service_model_combo = ttk.Combobox(model_frame, textvariable=self.service_model_var, state="readonly")
        self.service_model_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.service_model_combo.bind("<<ComboboxSelected>>", lambda e: (self.service_model_combo.selection_clear(), self.service_model_combo.icursor(0)))
        
        # 线程数
        threads_frame = ttk.Frame(self.detail_container)
        threads_frame.pack(fill="x", pady=5)
        ttk.Label(threads_frame, text="并发线程数:", width=12).pack(side="left")
        self.service_max_threads_var = tk.StringVar(value="4")
        threads_spin = ttk.Spinbox(threads_frame, from_=1, to=32, textvariable=self.service_max_threads_var, width=10, takefocus=False)
        threads_spin.pack(side="left", padx=5)
        
        # 操作按钮
        button_frame = ttk.Frame(self.detail_container)
        button_frame.pack(fill="x", pady=10)
        
        self.fetch_models_button = ttk.Button(button_frame, text="获取模型", command=self._fetch_models_async, bootstyle="info-outline")
        self.fetch_models_button.pack(side="left", padx=2)
        
        ttk.Button(button_frame, text="测试连接", command=self._test_connection, bootstyle="success-outline").pack(side="left", padx=2)
        
        ttk.Button(button_frame, text="保存更改", command=self._save_current_service, bootstyle="primary-outline").pack(side="left", padx=2)
        
        # 绑定事件
        self._bind_detail_events()
    
    def _bind_detail_events(self):
        """绑定详情面板事件"""
        def on_name_change(*args):
            if not self.is_loading_service and not self._saving_service:
                self._save_current_service(update_list=True)
        
        def on_change(*args):
            if not self.is_loading_service and not self._saving_service:
                self._save_current_service(update_list=False)
        
        self.service_name_var.trace_add("write", on_name_change)
        self.service_endpoint_var.trace_add("write", on_change)
        self.service_max_threads_var.trace_add("write", on_change)
        self.service_model_var.trace_add("write", on_change)
        
        def on_keys_change(event):
            event.widget.edit_modified(False)
            if not self.is_loading_service and not self._saving_service:
                self._save_current_service(update_list=False)
        
        self.service_keys_text.bind("<<Modified>>", on_keys_change)
    
    def _create_parameters_tab(self, parent):
        """创建参数设置选项卡"""
        # 滚动容器
        scrollable = custom_widgets.ScrollableFrame(parent)
        scrollable.pack(fill="both", expand=True)
        main_frame = scrollable.scrollable_frame
        
        # 性能设置
        perf_frame = tk_ttk.LabelFrame(main_frame, text="  性能设置", padding="15")
        perf_frame.pack(fill="x", pady=(10, 8), padx=10)
        
        perf_desc = ttk.Label(perf_frame, text="控制翻译任务的并发行为，提高处理速度", bootstyle="secondary")
        perf_desc.pack(anchor="w", pady=(0, 8))
        
        # 最大并发线程数
        self._create_spinbox_row(perf_frame, "最大并发线程数", self.ai_max_threads_var, 
                                 (1, 32), "同时发送API请求的最大数量，建议不超过API服务商的速率限制")
        
        # 重试设置
        retry_frame = tk_ttk.LabelFrame(main_frame, text="  重试与容错", padding="15")
        retry_frame.pack(fill="x", pady=8, padx=10)
        
        retry_desc = ttk.Label(retry_frame, text="翻译请求失败时的自动重试策略，合理设置可显著提升翻译成功率", bootstyle="secondary")
        retry_desc.pack(anchor="w", pady=(0, 8))
        
        self._create_spinbox_row(retry_frame, "最大重试次数", self.ai_max_retries_var,
                                 (0, 114514), "单个翻译批次失败后的最大重试次数，0表示不重试，114514表示无限重试")
        
        ttk.Separator(retry_frame, orient="horizontal").pack(fill="x", pady=8)
        
        # 延迟策略子组
        delay_header = ttk.Label(retry_frame, text="延迟退避策略")
        delay_header.pack(anchor="w", pady=(2, 6))
        
        self._create_spinbox_row(retry_frame, "速率限制冷却", self.ai_retry_rate_limit_cooldown_var,
                                 (1.0, 300.0), "因速率限制失败后，单个密钥的冷却时间（秒）", suffix="秒", is_float=True)
        
        self._create_spinbox_row(retry_frame, "初始重试延迟", self.ai_retry_initial_delay_var,
                                 (0.1, 60.0), "常规错误第一次重试前的等待时间（秒）", suffix="秒", is_float=True)
        
        self._create_spinbox_row(retry_frame, "最大重试延迟", self.ai_retry_max_delay_var,
                                 (1.0, 600.0), "指数退避策略中，最长的单次等待时间上限（秒）", suffix="秒", is_float=True)
        
        self._create_spinbox_row(retry_frame, "延迟退避因子", self.ai_retry_backoff_factor_var,
                                 (1.0, 5.0), "指数退避的乘数，大于1以实现延迟递增，推荐2.0", is_float=True)
    
    def _create_spinbox_row(self, parent, label_text, var, range_val, tooltip, suffix="", is_float=False):
        """创建带标签和微调框的行"""
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        frame.columnconfigure(1, weight=1)
        
        # 左侧标签 + 问号提示区
        label = ttk.Label(frame, text=label_text, width=16, anchor="w")
        label.grid(row=0, column=0, sticky="w")
        custom_widgets.ToolTip(label, tooltip)
        
        # 输入区
        spinbox = ttk.Spinbox(frame, from_=range_val[0], to=range_val[1], 
                             textvariable=var,
                             increment=0.1 if is_float else 1, takefocus=False)
        spinbox.grid(row=0, column=1, sticky="ew", padx=(10, 2))
        
        # 单位后缀
        if suffix:
            ttk.Label(frame, text=suffix, bootstyle="secondary").grid(row=0, column=2, sticky="w")
    
    def _populate_service_list(self):
        """填充服务列表"""
        # 清空列表
        for item in self.service_tree.get_children():
            self.service_tree.delete(item)
        
        # 填充服务
        for i, service in enumerate(self.api_services):
            name = service.get("name", f"服务{i+1}")
            keys_count = len(service.get("keys", []))
            max_threads = service.get("max_threads", 4)
            
            # 状态显示
            status = f"{keys_count}个密钥" if keys_count > 0 else "无密钥"
            
            self.service_tree.insert("", "end", iid=str(i), values=(name, status, max_threads))
    
    def _on_service_tree_select(self, event):
        """服务树选择事件"""
        selection = self.service_tree.selection()
        if not selection:
            return
        
        index = int(selection[0])
        
        # 如果正在保存中，跳过（避免selection_set触发的重复调用）
        if self._saving_service:
            return
        
        # 如果选中的索引与当前索引相同，跳过（避免selection_set触发的重复调用）
        if index == self.current_service_index:
            return
        
        self._load_service_details(index)
    
    def _load_service_details(self, index):
        """加载服务详情"""
        if index < 0 or index >= len(self.api_services):
            return
        
        # 防止递归调用
        if self.is_loading_service:
            return
        
        # 如果当前有选中的服务，先保存（不更新列表，避免触发选择事件循环）
        if self.current_service_index != -1 and self.current_service_index != index:
            self._save_current_service(update_list=False)
        
        # 设置加载标志
        self.is_loading_service = True
        
        try:
            # 隐藏提示，显示详情容器
            self.no_selection_label.pack_forget()
            self.detail_container.pack(fill="both", expand=True)
            
            # 更新详情框架标题
            service = self.api_services[index]
            self.detail_frame.configure(text=f"服务详情 - {service.get('name', f'服务{index+1}')}")
            
            # 填充详情
            self.service_name_var.set(service.get("name", ""))
            self.service_endpoint_var.set(service.get("endpoint", ""))
            
            # 填充密钥
            self.service_keys_text.delete("1.0", tk.END)
            self.service_keys_text.insert(tk.END, service.get("keys_raw", ""))
            
            # 填充模型
            model_list = service.get("model_list", [])
            self.service_model_combo["values"] = model_list
            if model_list:
                self.service_model_combo.set(service.get("model", model_list[0]))
                self.service_model_combo.configure(state="readonly")
            else:
                self.service_model_combo.set("请先获取模型")
                self.service_model_combo.configure(state="disabled")
            
            # 填充线程数
            self.service_max_threads_var.set(str(service.get("max_threads", 4)))
            
            # 更新当前索引
            self.current_service_index = index
            
        finally:
            self.is_loading_service = False
    
    def _save_current_service(self, update_list=True):
        """保存当前服务设置"""
        if self.current_service_index == -1 or self.current_service_index >= len(self.api_services):
            return
        
        # 防止重复调用
        if self._saving_service:
            return
        
        self._saving_service = True
        
        try:
            index = self.current_service_index
            service = self.api_services[index]
            
            # 更新服务信息
            service["name"] = self.service_name_var.get().strip() or "新服务"
            service["endpoint"] = self.service_endpoint_var.get().strip()
            
            # 处理密钥
            keys_text = self.service_keys_text.get("1.0", "end-1c")
            text_with_newlines = keys_text.replace(',', '\n')
            keys = [key.strip() for key in text_with_newlines.split('\n') if key.strip()]
            service["keys"] = keys
            service["keys_raw"] = '\n'.join(keys)
            
            # 更新模型
            model = self.service_model_var.get()
            if model and model != "请先获取模型":
                service["model"] = model
            
            # 更新线程数
            try:
                max_threads_str = self.service_max_threads_var.get().strip()
                service["max_threads"] = int(max_threads_str) if max_threads_str else 4
            except (tk.TclError, ValueError):
                service["max_threads"] = 4
            
            # 只在需要时更新列表显示
            if update_list:
                self._populate_service_list()
                
                # 重新选中当前项（解绑事件防止循环）
                if str(index) in self.service_tree.get_children():
                    self.service_tree.unbind("<<TreeviewSelect>>")
                    self.service_tree.selection_set(str(index))
                    self.service_tree.bind("<<TreeviewSelect>>", self._on_service_tree_select)
            
            # 保存配置
            self.save_callback()
        finally:
            self._saving_service = False
    
    def _show_add_service_menu(self):
        """显示添加服务菜单"""
        menu = tk.Menu(self.parent, tearoff=0)
        
        for template_name, template_data in self.SERVICE_TEMPLATES.items():
            menu.add_command(label=template_name, 
                           command=lambda t=template_name: self._add_service_from_template(t))
        
        # 获取按钮位置
        menu.tk_popup(self.parent.winfo_pointerx(), self.parent.winfo_pointery())
    
    def _add_service_from_template(self, template_name):
        """从模板添加服务"""
        template = self.SERVICE_TEMPLATES.get(template_name, self.SERVICE_TEMPLATES["自定义"])
        
        new_service = {
            "name": f"{template['name']}{len(self.api_services) + 1}",
            "endpoint": template["endpoint"],
            "keys": [],
            "keys_raw": "",
            "model": "请先获取模型",
            "max_threads": 4,
            "model_list": []
        }
        
        self.api_services.append(new_service)
        self._populate_service_list()
        
        # 选中新添加的服务
        new_index = len(self.api_services) - 1
        if str(new_index) in self.service_tree.get_children():
            self.service_tree.selection_set(str(new_index))
        
        self.save_callback()
    
    def _delete_service(self):
        """删除选中的服务"""
        selection = self.service_tree.selection()
        if not selection:
            ui_utils.show_error("操作失败", "请先选择一个服务")
            return
        
        index = int(selection[0])
        
        # 确认删除
        if not messagebox.askyesno("确认删除", f"确定要删除服务 '{self.api_services[index].get('name', f'服务{index+1}')}' 吗？"):
            return
        
        # 删除服务
        self.api_services.pop(index)
        
        # 清空详情
        if self.detail_container.winfo_ismapped():
            self.detail_container.pack_forget()
            self.no_selection_label.pack(expand=True)
            self.detail_frame.configure(text="服务详情")
        
        self.current_service_index = -1
        
        # 更新列表
        self._populate_service_list()
        self.save_callback()
    
    def _move_service_up(self):
        """上移服务"""
        selection = self.service_tree.selection()
        if not selection:
            return
        
        index = int(selection[0])
        if index > 0:
            self.api_services[index], self.api_services[index - 1] = \
                self.api_services[index - 1], self.api_services[index]
            self._populate_service_list()
            self.service_tree.unbind("<<TreeviewSelect>>")
            self.service_tree.selection_set(str(index - 1))
            self.service_tree.bind("<<TreeviewSelect>>", self._on_service_tree_select)
            self.current_service_index = index - 1
            self.save_callback()
    
    def _move_service_down(self):
        """下移服务"""
        selection = self.service_tree.selection()
        if not selection:
            return
        
        index = int(selection[0])
        if index < len(self.api_services) - 1:
            self.api_services[index], self.api_services[index + 1] = \
                self.api_services[index + 1], self.api_services[index]
            self._populate_service_list()
            self.service_tree.unbind("<<TreeviewSelect>>")
            self.service_tree.selection_set(str(index + 1))
            self.service_tree.bind("<<TreeviewSelect>>", self._on_service_tree_select)
            self.current_service_index = index + 1
            self.save_callback()
    
    def _fetch_models_async(self):
        """异步获取模型列表"""
        if self.current_service_index == -1:
            ui_utils.show_error("操作失败", "请先选择一个服务")
            return
        
        service = self.api_services[self.current_service_index]
        keys = service.get('keys', [])
        
        if not keys or not any(keys):
            ui_utils.show_error("操作失败", "请先输入至少一个有效的API密钥")
            return
        
        # 创建临时配置
        service_config = {
            "endpoint": service.get("endpoint", ""),
            "keys": service.get("keys", [])
        }
        
        # 禁用按钮并开始获取
        self.fetch_models_button.configure(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_models_worker, 
                        args=(self.current_service_index, service_config), 
                        daemon=True).start()
    
    def _fetch_models_worker(self, service_index, service_config):
        """获取模型的工作线程"""
        try:
            api_services = [{"endpoint": service_config.get("endpoint"), 
                           "keys": service_config.get("keys", [])}]
            translator = AITranslator(api_services)
            model_list = translator.fetch_models()
            
            if self.parent.winfo_exists():
                self.parent.after(0, self._update_models_ui, service_index, model_list)
        except Exception as e:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: ui_utils.show_error("获取失败", str(e)))
        finally:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.fetch_models_button.configure(
                    state="normal", text="获取模型"))
    
    def _update_models_ui(self, service_index, model_list):
        """更新模型列表UI"""
        if model_list and 0 <= service_index < len(self.api_services):
            self.api_services[service_index]["model_list"] = model_list
            
            # 如果当前选中的是该服务，更新下拉框
            if self.current_service_index == service_index:
                self.service_model_combo["values"] = model_list
                if model_list:
                    self.service_model_combo.set(model_list[0])
                    self.service_model_combo.configure(state="readonly")
            
            self.save_callback()
            ui_utils.show_info("成功", f"成功获取 {len(model_list)} 个模型！")
        else:
            ui_utils.show_error("失败", "未能获取到任何可用模型\n请检查密钥、网络或服务器地址")
    
    def _test_connection(self):
        """测试连接"""
        if self.current_service_index == -1:
            ui_utils.show_error("操作失败", "请先选择一个服务")
            return
        
        service = self.api_services[self.current_service_index]
        keys = service.get('keys', [])
        
        if not keys or not any(keys):
            ui_utils.show_error("操作失败", "请先输入至少一个有效的API密钥")
            return
        
        # 创建测试配置
        service_config = {
            "endpoint": service.get("endpoint", ""),
            "keys": [keys[0]]  # 只用第一个密钥测试
        }
        
        # 开始测试
        threading.Thread(target=self._test_connection_worker, 
                        args=(service_config,), daemon=True).start()
    
    def _test_connection_worker(self, service_config):
        """测试连接的工作线程"""
        try:
            api_services = [{"endpoint": service_config.get("endpoint"), 
                           "keys": service_config.get("keys", [])}]
            translator = AITranslator(api_services)
            
            # 尝试获取模型列表作为连接测试
            model_list = translator.fetch_models()
            
            if self.parent.winfo_exists():
                if model_list:
                    self.parent.after(0, lambda: ui_utils.show_info(
                        "连接成功", f"成功连接到API服务\n可用模型: {len(model_list)}个"))
                else:
                    self.parent.after(0, lambda: ui_utils.show_warning(
                        "连接警告", "已连接到服务，但未获取到模型列表"))
        except Exception as e:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: ui_utils.show_error("连接失败", str(e)))
    
    def get_config(self):
        """获取配置"""
        # 安全获取浮点数参数
        def safe_get_float(var, default):
            try:
                return var.get()
            except (tk.TclError, ValueError):
                return default
        
        # 安全获取整数参数
        def safe_get_int(var, default):
            try:
                return var.get()
            except (tk.TclError, ValueError):
                return default
        
        config = {
            "api_services": self.api_services,
            "ai_max_threads": safe_get_int(self.ai_max_threads_var, 4),
            "ai_max_retries": safe_get_int(self.ai_max_retries_var, 3),
            "ai_retry_rate_limit_cooldown": safe_get_float(self.ai_retry_rate_limit_cooldown_var, 60.0),
            "ai_retry_initial_delay": safe_get_float(self.ai_retry_initial_delay_var, 2.0),
            "ai_retry_max_delay": safe_get_float(self.ai_retry_max_delay_var, 120.0),
            "ai_retry_backoff_factor": safe_get_float(self.ai_retry_backoff_factor_var, 2.0)
        }
        
        # 保留其他AI相关参数
        other_keys = ["prompt", "use_grounding"]
        for key in other_keys:
            if key in self.config:
                config[key] = self.config[key]
        
        return config