import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils, custom_widgets
from gui.tab_pack_settings import TabPackSettings
from services.ai_translator import AITranslator
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
        self.github_proxy_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.advanced_tab_frame = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.basic_tab_frame, text=" 基础设置 ")
        self.notebook.add(self.ai_tab_frame, text=" AI 翻译 ")
        self.notebook.add(self.resource_pack_tab_frame, text=" 资源包 ")
        self.notebook.add(self.pack_settings_tab_frame, text=" 生成预案 ")
        self.notebook.add(self.github_proxy_tab_frame, text=" 网络代理 ")
        self.notebook.add(self.advanced_tab_frame, text=" 高级 ")

        # AI设置相关变量初始化
        self.api_keys_text = None
        self.prompt_text = None
        
        self._create_basic_tab_content(self.basic_tab_frame)
        self._create_ai_tab_content(self.ai_tab_frame)
        self._create_resource_pack_tab_content(self.resource_pack_tab_frame)
        self._create_pack_settings_tab_content(self.pack_settings_tab_frame)
        self._create_github_proxy_tab_content(self.github_proxy_tab_frame)
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
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self.pack_settings_manager = TabPackSettings(container)

    def _create_basic_settings(self, parent):
        # 基础设置框架
        frame = tk_ttk.LabelFrame(parent, text="基础设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(0, weight=1)

        # 输出设置分组
        output_frame = tk_ttk.LabelFrame(frame, text="输出设置", padding="10")
        output_frame.pack(fill="x", pady=(0, 10))
        output_frame.columnconfigure(1, weight=1)

        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
        self._create_path_entry(output_frame, "默认输出文件夹:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")

        self.pack_as_zip_var = tk.BooleanVar(value=self.config.get("pack_as_zip", False))
        zip_check = ttk.Checkbutton(output_frame, text="打包为.zip压缩包", variable=self.pack_as_zip_var, bootstyle="primary")
        zip_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(zip_check, "开启后, 将直接生成一个.zip格式的资源包文件, 而不是文件夹。")

        # 翻译匹配设置分组
        matching_frame = tk_ttk.LabelFrame(frame, text="翻译匹配设置", padding="10")
        matching_frame.pack(fill="x", pady=(0, 10))
        matching_frame.columnconfigure(0, weight=1)

        self.use_origin_name_lookup_var = tk.BooleanVar(value=self.config.get("use_origin_name_lookup", True))
        origin_check = ttk.Checkbutton(matching_frame, text="启用原文匹配", variable=self.use_origin_name_lookup_var, bootstyle="primary")
        origin_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(origin_check, "推荐开启。\n当key查找失败时，尝试使用英文原文进行二次查找。\n能极大提升词典利用率，但可能在极少数情况下导致误翻。")

        # 网络设置分组
        network_frame = tk_ttk.LabelFrame(frame, text="网络设置", padding="10")
        network_frame.pack(fill="x")
        network_frame.columnconfigure(0, weight=1)

        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_github_proxy", True))
        proxy_check = ttk.Checkbutton(network_frame, text="使用代理加速下载", variable=self.use_proxy_var, bootstyle="primary")
        proxy_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(proxy_check, "开启后，在下载社区词典或程序更新时会自动使用内置的代理服务。")

        # 绑定设置保存事件
        self.use_origin_name_lookup_var.trace_add("write", lambda *args: self._save_all_settings())
        self.use_proxy_var.trace_add("write", lambda *args: self._save_all_settings())
        self.pack_as_zip_var.trace_add("write", lambda *args: self._save_all_settings())

    def _create_github_proxy_tab_content(self, parent):
        """创建GitHub代理设置选项卡内容"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        
        # 初始化代理数据
        self.proxy_data = {}
        
        # GitHub代理设置框架
        frame = tk_ttk.LabelFrame(container, text="GitHub代理设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 说明文本
        ttk.Label(frame, text="管理GitHub加速代理URL，用于加速GitHub资源下载。", wraplength=700).pack(anchor="w", pady=5)
        
        # 代理表格区域
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建Treeview表格
        columns = ("url", "speed")
        self.proxy_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题和宽度
        self.proxy_tree.heading("url", text="代理URL", anchor="w")
        self.proxy_tree.heading("speed", text="速度")
        
        self.proxy_tree.column("url", width=300, anchor="w")
        self.proxy_tree.column("speed", width=100, anchor="center")
        
        # 添加滚动条
        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.proxy_tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.proxy_tree.xview)
        self.proxy_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # 布局
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        self.proxy_tree.pack(side="left", fill="both", expand=True)
        
        # 绑定事件
        self.proxy_tree.bind("<Double-1>", self._edit_proxy)
        
        # 加载代理列表
        self._load_proxy_list()
        
        # 操作按钮区域
        button_frame = ttk.LabelFrame(frame, text="操作", padding="10")
        button_frame.pack(fill="x", pady=5)
        button_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="button")
        
        # 第一行按钮：添加、删除、编辑
        ttk.Button(button_frame, text="一键添加预设代理", command=self._add_preset_proxies, bootstyle="success").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="删除选中", command=self._remove_selected_proxy, bootstyle="danger-outline").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="编辑选中", command=self._edit_proxy, bootstyle="warning-outline").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="清空", command=lambda: self._clear_proxies(), bootstyle="secondary-outline").grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # 第二行按钮：测试功能
        ttk.Button(button_frame, text="测试选中代理", command=self._test_selected_proxy, bootstyle="info-outline").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="批量测试速度", command=self._batch_test_speed, bootstyle="info-outline").grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="清空测试结果", command=self._clear_test_results, bootstyle="secondary-outline").grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        
        # 添加新代理区域
        add_proxy_frame = ttk.LabelFrame(frame, text="添加新代理", padding="10")
        add_proxy_frame.pack(fill="x", pady=5)
        add_proxy_frame.columnconfigure(1, weight=1)
        
        ttk.Label(add_proxy_frame, text="代理URL:", width=10).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.new_proxy_var = tk.StringVar(value="")
        ttk.Entry(add_proxy_frame, textvariable=self.new_proxy_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(add_proxy_frame, text="添加", command=self._add_proxy, bootstyle="success-outline").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
    
    def _refresh_ui_from_config(self):
        """从配置中刷新UI"""
        super()._refresh_ui_from_config()
        
        # 重新加载代理列表
        if hasattr(self, 'proxy_tree'):
            self._load_proxy_list()
    
    def _clear_proxies(self):
        """清空所有代理"""
        if messagebox.askyesno("确认清空", "确定要清空所有代理吗？"):
            self.proxy_tree.delete(*self.proxy_tree.get_children())
            self.config["github_proxies"] = []
            config_manager.save_config(self.config)
    
    def _load_proxy_list(self):
        """加载代理列表"""
        # 清除现有数据
        for item in self.proxy_tree.get_children():
            self.proxy_tree.delete(item)
        
        # 加载配置中的代理
        proxies = self.config.get("github_proxies", [])
        for proxy_url in proxies:
            # 初始化速度数据
            self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
    
    def _save_proxy_list(self):
        """保存代理列表"""
        proxies = []
        for item in self.proxy_tree.get_children():
            proxy_url = self.proxy_tree.item(item)['values'][0]
            proxies.append(proxy_url)
        
        self.config["github_proxies"] = proxies
        config_manager.save_config(self.config)    
    
    def _add_proxy(self):
        """添加新代理"""
        proxy_url = self.new_proxy_var.get().strip()
        if not proxy_url:
            return
        
        # 验证URL格式
        if not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
            ui_utils.show_error("格式错误", "代理URL必须以http://或https://开头")
            return
        
        # 检查是否已存在
        for item in self.proxy_tree.get_children():
            existing_proxy = self.proxy_tree.item(item)['values'][0]
            if existing_proxy == proxy_url:
                ui_utils.show_warning("已存在", "该代理URL已存在")
                return
        
        # 添加到表格
        self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
        self.new_proxy_var.set("")
        self._save_proxy_list()
    
    def _remove_selected_proxy(self):
        """删除选中的代理"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            return
        
        for item in selected_items:
            self.proxy_tree.delete(item)
        
        self._save_proxy_list()
    
    def _create_advanced_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="高级设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 重置设置分组
        reset_frame = tk_ttk.LabelFrame(frame, text="重置设置", padding="10")
        reset_frame.pack(fill="x", pady=5)
        reset_frame.columnconfigure(0, weight=1)
        
        ttk.Label(reset_frame, text="将所有设置恢复为默认值:", wraplength=600).pack(anchor="w", pady=5)
        reset_btn = ttk.Button(reset_frame, text="重置为默认设置", command=self._reset_settings, bootstyle="danger-outline")
        reset_btn.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(reset_btn, "警告：此操作将清除所有自定义设置，包括API密钥和路径设置。")
        
        # 重置设置分组
        reset_frame = tk_ttk.LabelFrame(frame, text="重置设置", padding="10")
        reset_frame.pack(fill="x", pady=5)
        reset_frame.columnconfigure(0, weight=1)
        
        ttk.Label(reset_frame, text="将所有设置恢复为默认值:", wraplength=600).pack(anchor="w", pady=5)
        reset_btn = ttk.Button(reset_frame, text="重置为默认设置", command=self._reset_settings, bootstyle="danger-outline")
        reset_btn.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(reset_btn, "警告：此操作将清除所有自定义设置，包括API密钥和路径设置。")

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
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_combobox_focus_in(event):
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_combobox_focus_out(event):
            # 立即取消文字选中状态，不使用延迟
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        # 绑定事件
        log_level_combobox.bind('<<ComboboxSelected>>', on_combobox_select)
        log_level_combobox.bind('<FocusIn>', on_combobox_focus_in)
        log_level_combobox.bind('<FocusOut>', on_combobox_focus_out)
        
        # 添加日志级别的实际影响说明
        ttk.Label(frame, text="提示：日志级别越低，生成的日志文件越大，但包含的信息越详细；级别越高，日志文件越小，但只记录重要信息。").pack(anchor="w", pady=5, padx=0, fill="x")
        ttk.Label(frame, text="日志文件默认保存在程序运行目录下，可用于排查程序运行中遇到的问题。").pack(anchor="w", pady=5, padx=0, fill="x")

    def _create_resource_pack_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="资源包设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_path", ""))
        # 添加trace事件监听器，确保值变化时自动保存
        self.community_dict_var.trace_add("write", lambda *args: self._save_all_settings())
        dict_path_frame = ttk.Frame(frame)
        dict_path_frame.pack(fill="x", pady=5)
        dict_label = ttk.Label(dict_path_frame, text="社区词典文件:", width=15)
        dict_label.pack(side="left")
        custom_widgets.ToolTip(dict_label, "可选。一个包含补充翻译的 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var, takefocus=False)
        dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        # 防止自动选中文本
        dict_entry.after_idle(dict_entry.selection_clear)
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_file(self.community_dict_var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")]), bootstyle="primary-outline")
        browse_btn.pack(side="left")
        self.download_dict_button = ttk.Button(dict_path_frame, text="检查/更新", command=self._check_and_update_dict_async, bootstyle="info")
        self.download_dict_button.pack(side="left", padx=(5, 5))

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
        api_entry = ttk.Entry(frame, textvariable=self.api_endpoint_var, takefocus=False)
        api_entry.pack(fill="x", pady=2)
        # 防止自动选中文本
        api_entry.after_idle(api_entry.selection_clear)
        
        def _on_text_change(event):
            # 重置修改标志
            event.widget.edit_modified(False)
            # 保存所有设置
            self._save_all_settings()
        
        self.api_keys_text.bind("<<Modified>>", _on_text_change)
        self.api_endpoint_var.trace_add("write", lambda *args: self._save_all_settings())
    
    def _create_ai_parameters_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="AI 参数设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        frame.columnconfigure(0, weight=1)
        
        self.model_var = tk.StringVar(value=self.config.get("model", "请先获取模型"))
        self.current_model_list = self.config.get("model_list", [])

        # 模型设置分组
        model_frame = tk_ttk.LabelFrame(frame, text="模型设置", padding="10")
        model_frame.pack(fill='x', pady=5)
        model_frame.columnconfigure(1, weight=1)
        
        ttk.Label(model_frame, text="AI 模型:", width=12).grid(row=0, column=0, sticky="w", pady=5)
        self.model_option_menu = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", values=self.current_model_list)
        if not self.current_model_list: self.model_option_menu.config(state="disabled")
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
            self._save_all_settings()
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

    def _save_all_settings(self, *args):
        config = config_manager.load_config()
        config["output_dir"] = self.output_dir_var.get()
        config["community_dict_path"] = self.community_dict_var.get()
        config["community_pack_paths"] = list(self.packs_listbox.get(0, tk.END))
        
        config["use_origin_name_lookup"] = self.use_origin_name_lookup_var.get()
        config["use_github_proxy"] = self.use_proxy_var.get()
        config["pack_as_zip"] = self.pack_as_zip_var.get()
        config["log_level"] = self.log_level_var.get()
        
        # 保存代理列表
        proxies = []
        if hasattr(self, 'proxy_tree'):
            for item in self.proxy_tree.get_children():
                proxy_url = self.proxy_tree.item(item)['values'][0]
                proxies.append(proxy_url)
            config["github_proxies"] = proxies
        
        raw_text = self.api_keys_text.get("1.0", "end-1c")
        text_with_newlines = raw_text.replace(',', '\n')
        config["api_keys"] = [key.strip() for key in text_with_newlines.split('\n') if key.strip()]
        config["api_keys_raw"] = raw_text
        config["api_endpoint"] = self.api_endpoint_var.get().strip()

        config["model"] = self.model_var.get()
        config["model_list"] = self.current_model_list
        
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
        
        if hasattr(self, 'prompt_text'):
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert(tk.END, self.config.get("prompt", config_manager.DEFAULT_PROMPT))
        
        # 更新社区包列表
        self.packs_listbox.delete(0, tk.END)
        for path in self.config.get("community_pack_paths", []):
            self.packs_listbox.insert(tk.END, path)
        
        # 更新GitHub代理列表
        if hasattr(self, 'proxy_tree'):
            self._load_proxy_list()
        
        # 更新AI参数spinbox值
        spinbox_keys = [
            "ai_max_threads", "ai_max_retries", 
            "ai_retry_rate_limit_cooldown", "ai_retry_initial_delay", 
            "ai_retry_max_delay", "ai_retry_backoff_factor"
        ]
        for key in spinbox_keys:
            var = getattr(self, f"{key}_var", None)
            if var:
                var.set(self.config.get(key, config_manager.DEFAULT_CONFIG.get(key)))
        
        # 确保所有输入控件在更新后不会自动选中文本
        self.after_idle(self._clear_all_selections)
    
    def _clear_all_selections(self):
        """清除所有输入控件的选中状态"""
        # 清除所有输入控件的选中状态
        for widget in self.winfo_children():
            self._clear_widget_selection(widget)
    
    def _clear_widget_selection(self, widget):
        """递归清除控件及其子控件的选中状态"""
        if hasattr(widget, 'selection_clear'):
            try:
                widget.selection_clear()
            except tk.TclError:
                pass
        
        # 处理子控件
        for child in widget.winfo_children():
            self._clear_widget_selection(child)

    def _create_path_entry(self, parent, label_text, var, browse_type, tooltip):
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill="x", pady=5)
        label = ttk.Label(row_frame, text=label_text, width=15)
        label.pack(side="left")
        custom_widgets.ToolTip(label, tooltip)
        entry = ttk.Entry(row_frame, textvariable=var, takefocus=False)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        var.trace_add("write", lambda *args: self._save_all_settings())
        browse_cmd = lambda: ui_utils.browse_directory(var) if browse_type == "directory" else ui_utils.browse_file(var)
        ttk.Button(row_frame, text="浏览...", command=browse_cmd, bootstyle="primary-outline").pack(side="left")
        # 防止自动选中文本
        entry.after_idle(entry.selection_clear)

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
        
        var.trace_add("write", self._save_all_settings)
        # 防止自动选中文本
        spinbox.after_idle(spinbox.selection_clear)
        return container

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
        service_config = config_manager.load_config()
        api_keys = service_config.get('api_keys', [])
        if not api_keys or not any(api_keys):
            ui_utils.show_error("操作失败", "请先在“设置”中输入至少一个有效的API密钥")
            return
        
        self.fetch_models_button.config(state="disabled", text="获取中...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
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
    
    def _reset_settings(self):
        """
        将所有设置重置为默认值
        """
        from tkinter import messagebox
        result = messagebox.askyesnocancel(
            "重置设置",
            "警告：此操作将清除所有自定义设置，包括API密钥、路径设置和AI参数等。\n\n是否确定要重置所有设置？",
            icon="warning"
        )
        
        if result:
            try:
                # 加载默认配置
                default_config = config_manager.DEFAULT_CONFIG
                # 保存默认配置
                config_manager.save_config(default_config)
                # 刷新UI
                self.config = default_config
                self._refresh_ui_from_config()
                ui_utils.show_info("重置成功", "所有设置已恢复为默认值")
            except Exception as e:
                ui_utils.show_error("重置失败", f"重置设置时发生错误：{str(e)}")

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

    def _create_term_database(self):
        """
        从社区词典创建术语库
        """
        import sqlite3
        from core.term_database import TermDatabase
        import threading
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor
        import re
        from collections import deque
        import time
        import os
        import math
        
        community_dict_path = self.community_dict_var.get()
        if not community_dict_path:
            ui_utils.show_error("错误", "请先配置社区词典文件路径。")
            return
        
        try:
            # 显示确认对话框
            if not messagebox.askyesno("确认创建", 
                                      "确定要从社区词典创建术语库吗？\n这将导入单词数量为1-2个的术语到术语库中。", 
                                      parent=self):
                return
            
            # 创建进度对话框
            from gui.dialogs import DownloadProgressDialog
            progress_dialog = DownloadProgressDialog(self, title="创建术语库")
            
            # 定义创建线程函数
            def create_thread_func():
                try:
                    # 步骤1: 连接社区词典数据库
                    progress_dialog.update_progress("连接数据库", 0, "")
                    
                    with sqlite3.connect(f"file:{community_dict_path}?mode=ro", uri=True) as conn:
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                        
                        # 步骤2: 加载术语库和现有术语
                        progress_dialog.update_progress("加载术语库", 10, "")
                        
                        term_db = TermDatabase()
                        existing_terms = term_db.get_all_terms()
                        existing_originals = {term["original"].lower() for term in existing_terms}
                        
                        # 步骤3: 查询总条目数，用于进度显示
                        progress_dialog.update_progress("获取总条目数", 20, "")
                        
                        # 先查询总条目数，让用户知道要处理多少数据
                        cursor.execute("SELECT COUNT(*) FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL")
                        total_dict_entries = cursor.fetchone()[0]
                        progress_dialog.update_progress("准备数据", 30, f"共 {total_dict_entries} 条数据")
                        
                        # 步骤4: 配置多线程参数
                        progress_dialog.update_progress("配置线程", 40, "")
                        
                        # 优化1: 根据系统CPU核心数动态调整线程数量
                        num_threads = os.cpu_count() or 4
                        # 限制最大线程数为8，避免过多线程导致系统资源竞争
                        num_threads = min(num_threads, 8)
                        # 确保至少有2个线程
                        num_threads = max(num_threads, 2)
                        
                        # 优化2: 根据线程数和数据量计算最佳批次大小
                        # 每个批次大小在1000-5000条之间，平衡内存使用和并行效率
                        batch_size = math.ceil(total_dict_entries / num_threads)
                        batch_size = max(1000, min(5000, batch_size))
                        
                        # 优化3: 预编译SQL查询，避免重复编译
                        sql = "SELECT ORIGIN_NAME, TRANS_NAME FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL"
                        
                        # 简化验证逻辑，使用更高效的实现
                        def is_valid_term(original):
                            """快速验证术语是否为1-2个单词"""
                            if not original:
                                return False
                            # 使用更快的字符串操作替代split()
                            space_count = original.count(' ')
                            return 0 <= space_count <= 1
                        
                        # 定义线程处理函数
                        def process_batch(batch_rows, batch_id, result_queue):
                            """处理数据批次"""
                            batch_import_count = 0
                            batch_skipped_count = 0
                            batch_terms = []
                            
                            # 每个线程都有自己的临时去重集合，避免全局锁
                            thread_skipped = set()
                            thread_skipped.update(existing_originals)  # 预先加载现有术语
                            
                            for row in batch_rows:
                                original = row["ORIGIN_NAME"].strip()
                                translation = row["TRANS_NAME"].strip()
                                
                                if original and translation:
                                    if is_valid_term(original):
                                        original_lower = original.lower()
                                        # 检查是否已存在（使用局部集合快速判断）
                                        if original_lower not in thread_skipped:
                                            batch_terms.append((original, translation))
                                            batch_import_count += 1
                                            thread_skipped.add(original_lower)
                                        else:
                                            batch_skipped_count += 1
                                    else:
                                        batch_skipped_count += 1
                                else:
                                    batch_skipped_count += 1
                            
                            # 将结果放入队列
                            result_queue.append((batch_id, batch_terms, batch_import_count, batch_skipped_count))
                        
                        # 步骤5: 执行多线程处理
                        progress_dialog.update_progress("多线程处理", 50, f"使用 {num_threads} 线程")
                        
                        # 结果队列，用于收集各线程结果
                        result_queue = deque()
                        
                        # 使用线程池执行多线程处理
                        with ThreadPoolExecutor(max_workers=num_threads) as executor:
                            # 执行SQL查询，获取所有数据
                            cursor.execute(sql)
                            all_rows = cursor.fetchall()
                            
                            # 将数据分成多个批次
                            batches = [all_rows[i:i+batch_size] for i in range(0, len(all_rows), batch_size)]
                            
                            # 提交所有批次任务
                            futures = []
                            for i, batch in enumerate(batches):
                                future = executor.submit(process_batch, batch, i, result_queue)
                                futures.append(future)
                            
                            # 监控进度
                            completed_batches = 0
                            total_batches = len(futures)
                            
                            while completed_batches < total_batches:
                                completed_batches = sum(1 for f in futures if f.done())
                                current_progress = 50 + (35 * completed_batches // total_batches)  # 50%-85%
                                progress_dialog.update_progress("处理数据", current_progress, f"已完成 {completed_batches}/{total_batches} 个批次")
                                time.sleep(0.2)  # 更频繁的进度更新，让用户感觉更流畅
                            
                            # 等待所有任务完成
                            concurrent.futures.wait(futures)
                        
                        # 步骤6: 合并结果
                        progress_dialog.update_progress("合并结果", 85, "")
                        
                        import_count = 0
                        skipped_count = 0
                        all_terms_to_add = []
                        
                        # 按批次ID排序，确保顺序正确
                        sorted_results = sorted(result_queue, key=lambda x: x[0])
                        
                        # 合并所有结果
                        for batch_id, batch_terms, batch_import, batch_skip in sorted_results:
                            all_terms_to_add.extend(batch_terms)
                            import_count += batch_import
                            skipped_count += batch_skip
                        
                        # 步骤7: 优化的分批次导入
                        progress_dialog.update_progress("导入术语", 90, "")
                        
                        if all_terms_to_add:
                            # 优化4: 根据数据量动态调整导入批次大小
                            # 数据量越大，批次越大，减少IO操作次数
                            import_batch_size = min(1000, max(200, len(all_terms_to_add) // 10))
                            
                            # 优化5: 预创建所有批次，减少循环内计算
                            import_batches = [all_terms_to_add[i:i+import_batch_size] for i in range(0, len(all_terms_to_add), import_batch_size)]
                            
                            for i, batch in enumerate(import_batches):
                                # 直接调用批量导入方法，避免创建临时字典
                                term_db.add_terms_batch([{"original": orig, "translation": trans} for orig, trans in batch])
                                # 更新进度
                                batch_progress = (i / len(import_batches)) * 10
                                progress_dialog.update_progress("导入术语", 90 + int(batch_progress), f"已导入 {min((i + 1) * import_batch_size, len(all_terms_to_add))}/{len(all_terms_to_add)} 个术语")
                        
                        # 关闭进度对话框
                        self.after(0, progress_dialog.close_dialog)
                        
                        # 显示结果
                        self.after(0, lambda: ui_utils.show_info(
                            "创建成功", 
                            f"术语库创建完成！\n成功导入 {import_count} 个术语，跳过 {skipped_count} 个条目。\n使用 {num_threads} 线程并行处理，大幅提高了导入速度。"
                        ))
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.after(0, progress_dialog.close_dialog)
                    self.after(0, lambda: ui_utils.show_error(
                        "创建失败", 
                        f"创建术语库时发生错误：{str(e)}"
                    ))
            
            # 启动创建线程
            threading.Thread(target=create_thread_func, daemon=True).start()
            
        except Exception as e:
            ui_utils.show_error("错误", f"创建术语库时发生错误：{str(e)}")

    def _load_proxy_list(self):
        """加载代理列表"""
        # 清除现有数据
        for item in self.proxy_tree.get_children():
            self.proxy_tree.delete(item)
        
        # 加载配置中的代理
        proxies = self.config.get("github_proxies", [])
        for proxy_url in proxies:
            # 初始化速度数据
            self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
    
    def _save_proxy_list(self):
        """保存代理列表"""
        proxies = []
        for item in self.proxy_tree.get_children():
            proxy_url = self.proxy_tree.item(item)['values'][0]
            proxies.append(proxy_url)
        
        self.config["github_proxies"] = proxies
        config_manager.save_config(self.config)
    
    def _add_preset_proxies(self):
        """一键添加预设的四个GitHub加速代理"""
        preset_proxies = [
            "https://gh-proxy.org/",
            "https://hk.gh-proxy.org/",
            "https://cdn.gh-proxy.org/",
            "https://edgeone.gh-proxy.org/"
        ]
        
        added_count = 0
        existing_proxies = [self.proxy_tree.item(item)['values'][0] for item in self.proxy_tree.get_children()]
        
        for proxy_url in preset_proxies:
            if proxy_url not in existing_proxies:
                # 添加到表格
                self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
                added_count += 1
                existing_proxies.append(proxy_url)
        
        if added_count > 0:
            self._save_proxy_list()
            ui_utils.show_info("添加成功", f"已添加 {added_count} 个预设代理")
        else:
            ui_utils.show_warning("已存在", "所有预设代理已存在")
    
    def _edit_proxy(self, event=None):
        """编辑选中的代理"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            return
        
        item = selected_items[0]
        current_proxy = self.proxy_tree.item(item)['values'][0]
        
        # 创建编辑对话框
        edit_window = ttk.Toplevel(self)
        edit_window.title("编辑代理")
        edit_window.geometry("500x150")
        edit_window.resizable(False, False)
        edit_window.transient(self)
        edit_window.grab_set()
        
        # 设置对话框位置
        x = self.winfo_rootx() + self.winfo_width() // 2 - 250
        y = self.winfo_rooty() + self.winfo_height() // 2 - 75
        edit_window.geometry(f"500x150+{x}+{y}")
        
        # 代理URL输入
        ttk.Label(edit_window, text="代理URL:", font=('', 10, 'bold')).pack(pady=10)
        edit_var = tk.StringVar(value=current_proxy)
        edit_entry = ttk.Entry(edit_window, textvariable=edit_var, width=60)
        edit_entry.pack(pady=5)
        edit_entry.focus_set()
        edit_entry.select_range(0, tk.END)
        
        # 按钮框架
        btn_frame = ttk.Frame(edit_window)
        btn_frame.pack(pady=10)
        
        def save_edit():
            new_proxy = edit_var.get().strip()
            if not new_proxy:
                ui_utils.show_error("错误", "代理URL不能为空")
                return
            
            # 验证URL格式
            if not (new_proxy.startswith("http://") or new_proxy.startswith("https://")):
                ui_utils.show_error("格式错误", "代理URL必须以http://或https://开头")
                return
            
            # 检查是否已存在（排除当前编辑项）
            existing_proxies = [self.proxy_tree.item(i)['values'][0] for i in self.proxy_tree.get_children() if i != item]
            if new_proxy in existing_proxies:
                ui_utils.show_warning("已存在", "该代理URL已存在")
                return
            
            # 更新表格项
            current_values = self.proxy_tree.item(item)['values']
            self.proxy_tree.item(item, values=(new_proxy, current_values[1]))
            self._save_proxy_list()
            edit_window.destroy()
        
        ttk.Button(btn_frame, text="保存", command=save_edit, bootstyle="success").pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=edit_window.destroy, bootstyle="danger-outline").pack(side="left", padx=10)
    

    
    def _test_proxy_speed(self, proxy_url):
        """测试单个代理的速度，使用多线程下载"""
        try:
            import time
            import concurrent.futures
            
            # 使用最新版本的社区词典文件作为测试资源，修复URL格式
            test_url = proxy_url.rstrip('/') + "/github.com/VM-Chinese-translate-group/i18n-Dict-Extender/releases/latest/download/Dict-Sqlite.db"
            
            total_bytes = 0
            start_time = time.time()
            max_download = 10 * 1024 * 1024  # 10MB
            timeout = 10  # 10秒超时
            
            # 获取文件大小和初始响应
            response = requests.get(test_url, timeout=10, stream=True)
            response.raise_for_status()
            
            # 计算每个线程要下载的数据范围
            file_size = int(response.headers.get('content-length', max_download))
            file_size = min(file_size, max_download)  # 限制最大下载量
            response.close()
            
            # 定义每个线程的下载范围
            num_threads = 4
            chunk_size = max(8192, file_size // num_threads)
            
            def download_chunk(start, end):
                """下载文件的一个块"""
                nonlocal total_bytes
                headers = {'Range': f'bytes={start}-{end}'}
                try:
                    with requests.get(test_url, headers=headers, timeout=timeout, stream=True) as r:
                        r.raise_for_status()
                        chunk_total = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                chunk_total += len(chunk)
                                # 检查总下载量是否超过限制
                                if total_bytes + chunk_total > max_download:
                                    chunk_total = max_download - total_bytes
                                    break
                                # 检查是否超时
                                if time.time() - start_time > timeout:
                                    break
                        total_bytes += chunk_total
                except Exception:
                    pass
            
            # 计算下载范围
            ranges = []
            for i in range(num_threads):
                start = i * chunk_size
                end = min((i + 1) * chunk_size - 1, file_size - 1)
                if start < file_size:
                    ranges.append((start, end))
            
            # 使用线程池进行多线程下载
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(download_chunk, start, end) for start, end in ranges]
                # 等待所有任务完成或超时
                concurrent.futures.wait(futures, timeout=timeout - (time.time() - start_time))
            
            elapsed_time = time.time() - start_time
            
            if elapsed_time == 0 or total_bytes == 0:
                return "--"
            
            speed_bps = total_bytes / elapsed_time
            if speed_bps > 1024 * 1024:
                return f"{speed_bps / (1024 * 1024):.2f} MB/s"
            elif speed_bps > 1024:
                return f"{speed_bps / 1024:.1f} KB/s"
            else:
                return f"{speed_bps:.0f} B/s"
        except Exception as e:
            logging.warning(f"速度测试失败: {e}")
            return "--"
    
    def _test_selected_proxy(self):
        """测试选中代理的速度"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            return
        
        # 禁用按钮
        self._disable_proxy_buttons()
        
        def test_worker():
            for item in selected_items:
                proxy_url = self.proxy_tree.item(item)['values'][0]
                
                # 测试速度
                speed = self._test_proxy_speed(proxy_url)
                
                # 更新UI
                if self.winfo_exists():
                    self.after(0, lambda i=item, url=proxy_url, s=speed: self.proxy_tree.item(i, values=(url, s)))
            # 启用按钮
            if self.winfo_exists():
                self.after(0, self._enable_proxy_buttons)
        
        threading.Thread(target=test_worker, daemon=True).start()
    

    
    def _batch_test_speed(self):
        """批量测试所有代理的速度，单个代理依次测试"""
        # 禁用按钮
        self._disable_proxy_buttons()
        
        def main_worker():
            # 首先在主线程获取代理列表
            proxy_list = []
            
            def get_proxies():
                nonlocal proxy_list
                if hasattr(self, 'proxy_tree') and self.winfo_exists():
                    for item in self.proxy_tree.get_children():
                        try:
                            proxy_url = self.proxy_tree.item(item)['values'][0]
                            proxy_list.append((item, proxy_url))
                        except (tk.TclError, IndexError):
                            pass
            
            self.after(0, get_proxies)
            
            # 等待获取代理列表
            import time
            time.sleep(0.1)
            
            # 依次测试每个代理（每个代理内部是多线程下载）
            for item, proxy_url in proxy_list:
                # 测试速度（内部已使用多线程下载）
                speed = self._test_proxy_speed(proxy_url)
                
                # 更新UI
                if hasattr(self, 'proxy_tree') and self.winfo_exists():
                    try:
                        self.after(0, lambda i=item, url=proxy_url, s=speed: 
                                 self.proxy_tree.item(i, values=(url, s)) if self.proxy_tree.exists(i) else None)
                    except tk.TclError:
                        pass
            
            # 启用按钮
            if hasattr(self, 'proxy_tree') and self.winfo_exists():
                self.after(0, self._enable_proxy_buttons)
        
        threading.Thread(target=main_worker, daemon=True).start()
    
    def _clear_test_results(self):
        """清空所有测试结果"""
        # 检查组件是否存在
        if not hasattr(self, 'proxy_tree') or not self.proxy_tree.winfo_exists():
            return
        
        try:
            for item in self.proxy_tree.get_children():
                if self.proxy_tree.exists(item):
                    proxy_url = self.proxy_tree.item(item)['values'][0]
                    self.proxy_tree.item(item, values=(proxy_url, "--"))
        except tk.TclError:
            # 组件可能已被销毁
            pass
    
    def _disable_proxy_buttons(self):
        """禁用代理操作按钮"""
        if hasattr(self, 'proxy_tree'):
            for widget in self.winfo_children():
                self._disable_widget_buttons(widget)
    
    def _enable_proxy_buttons(self):
        """启用代理操作按钮"""
        if hasattr(self, 'proxy_tree'):
            for widget in self.winfo_children():
                self._enable_widget_buttons(widget)
    
    def _disable_widget_buttons(self, widget):
        """递归禁用控件及其子控件中的按钮"""
        if isinstance(widget, ttk.Button):
            widget.config(state="disabled")
        
        for child in widget.winfo_children():
            self._disable_widget_buttons(child)
    
    def _enable_widget_buttons(self, widget):
        """递归启用控件及其子控件中的按钮"""
        if isinstance(widget, ttk.Button):
            widget.config(state="normal")
        
        for child in widget.winfo_children():
            self._enable_widget_buttons(child)
    
    def _dict_update_worker(self):
        try:
            remote_info = self._get_remote_dict_info()
            if not remote_info:
                self.after(0, lambda: ui_utils.show_error("检查失败", "无法获取远程词典版本信息。"))
                return

            # 获取本地词典路径和配置中的版本
            local_dict_path = self.community_dict_var.get()
            local_version = self.config.get("last_dict_version", "0.0.0")
            
            # 检查是否未安装词典
            is_dict_installed = local_dict_path and Path(local_dict_path).exists()
            
            # 比较版本
            remote_version = remote_info["version"]
            if is_dict_installed and local_version == remote_version:
                self.after(0, lambda: ui_utils.show_info("检查完成", f"社区词典已是最新版本 ({local_version})。"))
                return
            
            # 显示更新提示
            msg = f"发现新词典版本: {remote_version}"
            if not is_dict_installed:
                msg += "\n您尚未安装社区词典，是否立即下载？"
            else:
                msg += f" (当前: {local_version})\n是否立即下载更新？"
                
            if not messagebox.askyesno("更新提示", msg):
                return
            
            from gui.dialogs import DownloadProgressDialog
            progress_dialog = DownloadProgressDialog(self, title="下载社区词典")
            STABLE_PROXY_URL = "https://lucky-moth-20.deno.dev/"
            DEST_FILE = Path("Dict-Sqlite.db").resolve()
            
            use_proxy = self.config.get("use_github_proxy", True)
            final_url = f"{STABLE_PROXY_URL}{remote_info['url']}" if use_proxy else remote_info["url"]
            
            from utils import update_checker
            ok = update_checker.download_update(final_url, DEST_FILE, lambda s, p, sp: progress_dialog.update_progress(s, p, sp), None)
            progress_dialog.close_dialog()

            if ok:
                # 下载成功，更新配置
                self.config["last_dict_version"] = remote_version
                self.config["community_dict_path"] = str(DEST_FILE)
                config_manager.save_config(self.config)
                self.after(0, lambda: self.community_dict_var.set(str(DEST_FILE)))
                self.after(0, lambda: ui_utils.show_info("更新成功", f"社区词典已更新到版本 {remote_version}！"))
            else:
                self.after(0, lambda: ui_utils.show_error("下载失败", "下载新版词典时发生错误。"))
        finally:
            if self.winfo_exists():
                self.after(0, lambda: self.download_dict_button.config(state="normal", text="检查/更新"))