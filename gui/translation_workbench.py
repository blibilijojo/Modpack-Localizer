import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from collections import defaultdict
import json
from datetime import datetime
from pathlib import Path
import threading
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import copy
import uuid

from utils import config_manager
from services.ai_translator import AITranslator
from gui import ui_utils
from gui.custom_widgets import ToolTip
from gui.find_replace_dialog import FindReplaceDialog
from core.term_database import TermDatabase

class TranslationWorkbench(ttk.Frame):
    def __init__(self, parent_frame, initial_data: dict, namespace_formats: dict, raw_english_files: dict, current_settings: dict, log_callback=None, project_path: str | None = None, finish_button_text: str = "完成", finish_callback=None, cancel_callback=None, project_name: str = "Unnamed_Project", main_window_instance=None, undo_history: dict = None, module_names: list = None):
        super().__init__(parent_frame)
        self.translation_data = initial_data
        self.namespace_formats = namespace_formats
        self.raw_english_files = raw_english_files
        self.current_settings = current_settings
        self.module_names = module_names or []
        self.log_callback = log_callback or (lambda msg, lvl: None)
        self.finish_callback = finish_callback
        self.cancel_callback = cancel_callback
        self.project_name = project_name
        self.main_window = main_window_instance

        # 初始化术语库
        self.term_db = TermDatabase()
        
        # 术语提示优化：防抖机制
        self._term_update_id = None
        self._last_term_update_time = 0
        self._term_update_delay = 100  # 延迟100ms执行术语匹配
        
        # 术语匹配结果缓存 - 使用OrderedDict实现LRU缓存
        from collections import OrderedDict
        self._term_match_cache = OrderedDict()
        self._term_cache_max_size = 1000  # 缓存最大条目数
        
        # 术语搜索线程控制
        self._current_term_thread = None
        self._term_search_cancelled = False
        self._current_search_id = 0
        
        # AI翻译取消控制
        self._ai_translation_cancelled = False
        # 当前的AI翻译器实例
        self._current_translator = None
        # 当前的AI翻译线程池
        self._current_ai_executor = None
        
        # 线程池管理
        from concurrent.futures import ThreadPoolExecutor
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ModpackLocalizer")

        self.final_translations = None
        self.current_selection_info = None
        self.sort_column = '#0'
        self.sort_reverse = False
        self.original_headings = {}
        
        self.current_project_path = project_path
        self.is_dirty = False
        
        # 操作记录系统
        self.operation_history = []  # 操作历史记录
        self.max_history_size = 100   # 最大历史记录数量
        self.last_operation_time = 0  # 上次操作时间
        self.operation_merge_window = 2.0  # 操作合并窗口（秒）
        self.current_state_index = 0  # 当前状态在操作历史中的索引
        
        # 操作类型定义
        self.OPERATION_TYPES = {
            'INIT': '初始化',
            'EDIT': '文本编辑',
            'REPLACE': '替换操作',
            'REPLACE_ALL': '全部替换',
            'IMPORT': '导入数据',
            'AI_TRANSLATION': 'AI翻译',
            'BATCH_PROCESS': '批量处理',
            'DICTIONARY_ADD': '添加词典',
            'REDO': '重做操作',
            'OTHER': '其他操作'
        }
        
        self.finish_button_text = finish_button_text

        # 新增UI优化相关状态
        self._is_navigating = False
        self._last_navigation_time = 0
        self._keyboard_shortcuts_enabled = True
        self._double_click_to_approve = self.current_settings.get('double_click_to_approve', True)
        self._enter_to_navigate = self.current_settings.get('enter_to_navigate', True)
        self._focus_on_translate = self.current_settings.get('focus_on_translate', True)
        
        # 翻译控制台功能整合相关变量
        self._current_mode = "workbench"  # "workbench" 或 "comprehensive"
        self._comprehensive_ui = None

        self._create_widgets()
        
        # 立即设置初始sash位置，确保在所有情况下都能保持1:3的比例
        self._set_initial_sash_position()
        # 同时在idle时再次检查，确保窗口完全初始化后比例正确
        self.after_idle(self._set_initial_sash_position)
        
        # 初始化操作历史（不记录为用户操作）
        # 添加初始状态作为历史记录的基础
        import uuid
        initial_state = {
            'id': str(uuid.uuid4()),
            'type': 'INIT',
            'description': '初始化',
            'timestamp': datetime.now().isoformat(),
            'target_iid': None,
            'details': {'project_name': self.project_name},
            'state': {}
        }
        self.operation_history = [initial_state]
        self._update_history_buttons()
        self.bind_all("<Control-z>", self.undo)
        self.bind_all("<Control-y>", self.redo)
        self.bind_all("<Control-s>", lambda e: self._save_project())

        self._setup_treeview_tags()
        self._populate_namespace_tree()
        self._update_ui_state(interactive=True, item_selected=False)
        self._set_dirty(False)

    def get_state(self):
        return {
            "project_name": self.project_name,
            "workbench_data": self.translation_data,
            "namespace_formats": self.namespace_formats,
            "raw_english_files": self.raw_english_files,
            "current_project_path": self.current_project_path,
        }

    def _set_initial_sash_position(self):
        try:
            self.update_idletasks()
            width = self.winfo_width()
            # 设置为窗口宽度的25%，保持1:3的比例，但不小于330像素，确保能显示所有列
            initial_pos = max(int(width * 0.25), 330)
            if initial_pos > 50:
                self.main_pane.sashpos(0, initial_pos)
        except tk.TclError:
            pass

    def _create_widgets(self):
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True, padx=5, pady=(5, 0))

        self.left_frame = ttk.Frame(self.main_pane, padding=5)
        ttk.Label(self.left_frame, text="模组/任务列表", bootstyle="primary").pack(anchor="w", pady=(0, 5))
        
        # 创建左侧项目列表
        self.ns_tree = ttk.Treeview(self.left_frame, columns=("pending", "completed"), show="tree headings")
        
        # 添加垂直滚动条
        v_scrollbar = ttk.Scrollbar(self.left_frame, orient=tk.VERTICAL, command=self.ns_tree.yview)
        self.ns_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # 定义列配置，调整项目列宽度，让已翻译列能正常显示
        column_config = {
            "#0": {"text": "项目", "width": 150, "minwidth": 120, "stretch": True},
            "pending": {"text": "待翻译", "width": 80, "minwidth": 80, "stretch": False, "anchor": "center"},
            "completed": {"text": "已翻译", "width": 80, "minwidth": 80, "stretch": False, "anchor": "center"}
        }
        
        # 配置列标题和属性
        for col, config in column_config.items():
            self.original_headings[col] = config["text"]
            self.ns_tree.heading(col, text=config["text"], command=lambda c=col: self._sort_by_column(c))
            column_kwargs = {
                'minwidth': config["minwidth"],
                'stretch': config["stretch"],
                'anchor': config.get("anchor", "w")
            }
            if config.get("width") is not None:
                column_kwargs['width'] = config["width"]
            self.ns_tree.column(col, **column_kwargs)
        
        # 布局Treeview和滚动条
        self.ns_tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        
        # 初始绑定事件处理函数
        self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        
        # 添加到主面板
        self.main_pane.add(self.left_frame, weight=1)

        right_frame_container = ttk.Frame(self.main_pane)
        self.main_pane.add(right_frame_container, weight=3)
        
        # 保存右侧容器引用，用于切换
        self.right_frame_container = right_frame_container
        
        # 创建工作区UI容器
        self.workbench_ui_container = ttk.Frame(right_frame_container)
        self.workbench_ui_container.pack(fill="both", expand=True)
        
        right_pane = ttk.PanedWindow(self.workbench_ui_container, orient=tk.VERTICAL)
        right_pane.pack(fill="both", expand=True)

        table_container = ttk.Frame(right_pane, padding=5)
        self.trans_tree = ttk.Treeview(table_container, columns=("key", "english", "chinese", "source"), show="headings")
        self.trans_tree.heading("key", text="原文键", command=lambda: self._sort_items_by_default_order())
        self.trans_tree.column("key", width=200, stretch=False)
        self.trans_tree.heading("english", text="原文"); self.trans_tree.column("english", width=250, stretch=True)
        self.trans_tree.heading("chinese", text="译文"); self.trans_tree.column("chinese", width=250, stretch=True)
        self.trans_tree.heading("source", text="来源", command=lambda: self._sort_items_by_source())
        self.trans_tree.column("source", width=120, stretch=False)
        self.trans_items_sort_reverse = False
        self.source_sort_reverse = False
        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y"); self.trans_tree.pack(fill="both", expand=True)
        self.trans_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        right_pane.add(table_container, weight=3)
        
        editor_frame = tk_ttk.LabelFrame(right_pane, text="翻译编辑器", padding=10)
        editor_frame.columnconfigure(1, weight=1)
        # 创建原文和术语提示的并列布局
        content_frame = ttk.Frame(editor_frame)
        content_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # 左侧：原文显示
        en_container = ttk.Frame(content_frame)
        en_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        en_container.rowconfigure(1, weight=1)
        en_container.columnconfigure(0, weight=1)
        
        ttk.Label(en_container, text="原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=0, pady=0)
        
        style = ttk.Style.get_instance()
        theme_bg_color = style.lookup('TFrame', 'background')
        theme_fg_color = style.lookup('TLabel', 'foreground')
        self.en_text_display = scrolledtext.ScrolledText(
            en_container, height=5, wrap=tk.WORD, relief="flat",
            background=theme_bg_color, foreground=theme_fg_color
        )
        self.en_text_display.bind("<KeyPress>", lambda e: "break")
        self.en_text_display.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        
        # 右侧：术语提示
        term_container = ttk.Frame(content_frame)
        term_container.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        term_container.rowconfigure(1, weight=1)
        term_container.columnconfigure(0, weight=1)
        
        ttk.Label(term_container, text="术语提示:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=0, pady=0)
        
        self.term_text = scrolledtext.ScrolledText(
            term_container, height=5, wrap=tk.WORD, relief="flat",
            background=theme_bg_color, foreground=theme_fg_color, state="disabled"
        )
        self.term_text.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        
        # 译文输入区域
        zh_header_frame = ttk.Frame(editor_frame); zh_header_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=(5,0))
        ttk.Label(zh_header_frame, text="译文:", anchor="nw").pack(side="left")
        shortcut_info_label = ttk.Label(zh_header_frame, text="快捷键: Enter 跳转到下一条, Ctrl+Enter 跳转到下一条待翻译")
        shortcut_info_label.pack(side="right")
        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=5, wrap=tk.WORD, state="disabled")
        # 确保译文栏水平填充整个可用空间
        self.zh_text_input.grid(row=2, column=1, sticky="nsew", padx=5, pady=5)
        
        # 延迟保存机制
        self._text_modified_timer = None
        self._text_modified_delay = 500  # 延迟500ms执行保存
        
        def _on_key_release(event):
            """合并的按键释放事件处理函数"""
            self._on_text_modified_delayed(event)
            self._update_term_suggestions(event)
        
        self.zh_text_input.bind("<KeyRelease>", _on_key_release)
        self.zh_text_input.bind("<FocusOut>", lambda e: self._save_current_edit())
        self.zh_text_input.bind("<Return>", self._save_and_jump_sequential)
        self.zh_text_input.bind("<Control-Return>", self._save_and_jump_pending)
        # 添加复制事件处理，确保只复制实际文本
        self.zh_text_input.bind("<Control-c>", self._on_copy)
        self.zh_text_input.bind("<Control-C>", self._on_copy)
        editor_btn_frame = ttk.Frame(editor_frame); editor_btn_frame.grid(row=3, column=1, sticky="ew", pady=(5,0))
        editor_btn_frame.columnconfigure(0, weight=1)
        
        # 右侧框架 - 放置其他按钮
        right_frame = ttk.Frame(editor_btn_frame)
        right_frame.grid(row=0, column=0, sticky="e")
        
        # 优化按钮布局，按操作频率和逻辑顺序排列
        btn_padding = 5  # 按钮间距
        
        # 其他按钮（居右）
        self.add_to_dict_btn = ttk.Button(right_frame, text="添加到词典", command=self._add_to_user_dictionary, state="disabled", bootstyle="info-outline")
        self.add_to_dict_btn.pack(side="right", padx=(btn_padding, 0))
        
        # 添加分隔符
        separator3 = ttk.Separator(right_frame, orient="vertical")
        separator3.pack(side="right", fill="y", padx=(btn_padding, btn_padding))
        
        self.history_btn = ttk.Button(right_frame, text="操作历史", command=self._show_operation_history, bootstyle="info-outline")
        self.history_btn.pack(side="right", padx=(btn_padding, btn_padding))
        ToolTip(self.history_btn, "查看和管理操作历史")
        
        # 添加分隔符
        separator2 = ttk.Separator(right_frame, orient="vertical")
        separator2.pack(side="right", fill="y", padx=(btn_padding, btn_padding))
        
        self.redo_btn = ttk.Button(right_frame, text="重做", command=self.redo, bootstyle="info-outline")
        self.redo_btn.pack(side="right", padx=(btn_padding, btn_padding))
        ToolTip(self.redo_btn, "重做已撤销的操作 (Ctrl+Y)")
        
        self.undo_btn = ttk.Button(right_frame, text="撤销", command=self.undo, bootstyle="info-outline")
        self.undo_btn.pack(side="right", padx=(0, btn_padding))
        ToolTip(self.undo_btn, "撤销上一步操作 (Ctrl+Z)")
        
        # 添加分隔符
        separator1 = ttk.Separator(right_frame, orient="vertical")
        separator1.pack(side="right", fill="y", padx=(btn_padding, btn_padding))

        right_pane.add(editor_frame, weight=1)
        
        # 创建翻译控制台UI容器，初始隐藏
        self.comprehensive_ui_container = ttk.Frame(self.right_frame_container)
        self.comprehensive_ui_container.pack(fill="both", expand=True)
        self.comprehensive_ui_container.pack_forget()
        
        # 创建上传到汉化仓库UI容器，初始隐藏
        self.github_upload_ui_container = ttk.Frame(self.right_frame_container)
        self.github_upload_ui_container.pack(fill="both", expand=True)
        self.github_upload_ui_container.pack_forget()

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        
        # 左侧状态显示区域
        status_container = ttk.Frame(btn_frame)
        status_container.pack(side="left", fill="x", expand=True)
        
        # 主状态标签
        self.status_label = ttk.Label(status_container, text="请选择一个项目以开始")
        self.status_label.pack(side="left", fill="x", expand=True)
        
        # 翻译状态显示标签


        # 功能切换按钮
        self.mode_switch_btn = ttk.Button(btn_frame, text="进入翻译控制台", command=self._toggle_mode, state="disabled", bootstyle="primary")
        self.mode_switch_btn.pack(side="right")
        ToolTip(self.mode_switch_btn, "在翻译工作台和翻译控制台功能之间切换")
        
        self.save_button = ttk.Button(btn_frame, text="保存项目", command=self._save_project, bootstyle="primary-outline")
        self.save_button.pack(side="right", padx=5)
        
        self.finish_button = ttk.Button(btn_frame, text=self.finish_button_text, command=self._on_finish, bootstyle="success")
        self.finish_button.pack(side="right", padx=5)
        
        # 上传到汉化仓库按钮 - 放在最左边
        self.github_upload_button = ttk.Button(btn_frame, text="上传到GitHub", command=self._on_github_upload, bootstyle="warning")
        self.github_upload_button.pack(side="right")
        ToolTip(self.github_upload_button, "进入GitHub汉化仓库上传界面")

    def _update_theme_colors(self):
        style = ttk.Style.get_instance()
        theme_bg_color = style.lookup('TFrame', 'background')
        theme_fg_color = style.lookup('TLabel', 'foreground')
        self.en_text_display.config(background=theme_bg_color, foreground=theme_fg_color)

    def _get_searchable_items(self, scope):
        if scope == 'current':
            selection = self.ns_tree.selection()
            if not selection:
                messagebox.showwarning("范围错误", "请先在左侧选择一个项目以确定搜索范围。", parent=self)
                return []
            return self.trans_tree.get_children()
        else:
            # 使用列表推导式代替显式循环，提高性能
            return [
                f"{ns_iid}___{idx}"
                for ns_iid in self.ns_tree.get_children()
                for idx, item in enumerate(self.translation_data.get(ns_iid, {}).get('items', []))
                if item.get('en', '').strip()
            ]

    def _safe_select_item(self, iid):
        if self.trans_tree.exists(iid):
            self.trans_tree.selection_set(iid)
    
    def _safe_select_item_and_update_ui(self, iid):
        """安全地选择项目并更新UI"""
        if self.trans_tree.exists(iid):
            # 先获取条目信息
            ns, idx = self._get_ns_idx_from_iid(iid)
            if ns is not None:
                item_data = self.translation_data[ns]['items'][idx]
                # 先更新当前选择信息
                self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': iid}
                
                # 解绑文本修改事件，避免设置编辑器内容时触发保存逻辑
                self.zh_text_input.unbind("<KeyRelease>")
                self.zh_text_input.unbind("<FocusOut>")
                
                # 先更新编辑器内容，避免触发保存逻辑
                self._set_editor_content(item_data['en'], item_data.get('zh', ''))
                # 清除编辑器的修改标记
                self.zh_text_input.edit_modified(False)
                
                # 重新绑定文本修改事件
                def _on_key_release(event):
                    """合并的按键释放事件处理函数"""
                    self._on_text_modified(event)
                    self._update_term_suggestions(event)
                
                self.zh_text_input.bind("<KeyRelease>", _on_key_release)
                self.zh_text_input.bind("<FocusOut>", lambda e: self._save_current_edit())
                
                # 选择项目
                self.trans_tree.selection_set(iid)
                self.trans_tree.focus(iid)
                self.trans_tree.see(iid)
                # 更新UI状态，确保按钮可用
                self._update_ui_state(interactive=True, item_selected=True)
                self.zh_text_input.focus_set()
                # 显示匹配的术语
                self._show_matching_terms(item_data['en'])
    
    def _restore_item_selection(self):
        """根据保存的信息重新选中条目"""
        if not hasattr(self, '_workbench_item_selection') or not self._workbench_item_selection:
            return
        
        selection_info = self._workbench_item_selection
        ns = selection_info['ns']
        idx = selection_info['idx']
        
        # 检查命名空间是否存在
        if not self.ns_tree.exists(ns):
            return
        
        # 确保当前选中的命名空间是保存的命名空间
        current_ns_selection = self.ns_tree.selection()
        if not current_ns_selection or current_ns_selection[0] != ns:
            # 切换到保存的命名空间
            self.ns_tree.selection_set(ns)
            self.ns_tree.focus(ns)
            self.ns_tree.see(ns)
            # 重新填充项目列表
            self._populate_item_list()
        
        # 重新构建正确的条目ID
        target_iid = f"{ns}___{idx}"
        
        # 检查条目是否存在
        if self.trans_tree.exists(target_iid):
            # 直接选择项目，不触发保存逻辑
            self.trans_tree.selection_set(target_iid)
            self.trans_tree.focus(target_iid)
            self.trans_tree.see(target_iid)
            
            # 直接更新当前选择信息和编辑器内容
            if ns is not None:
                item_data = self.translation_data[ns]['items'][idx]
                # 更新当前选择信息
                self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': target_iid}
                
                # 解绑文本修改事件，避免设置编辑器内容时触发保存逻辑
                self.zh_text_input.unbind("<KeyRelease>")
                self.zh_text_input.unbind("<FocusOut>")
                
                # 更新编辑器内容
                self._set_editor_content(item_data['en'], item_data.get('zh', ''))
                # 清除编辑器的修改标记
                self.zh_text_input.edit_modified(False)
                
                # 重新绑定文本修改事件
                def _on_key_release(event):
                    """合并的按键释放事件处理函数"""
                    self._on_text_modified(event)
                    self._update_term_suggestions(event)
                
                self.zh_text_input.bind("<KeyRelease>", _on_key_release)
                self.zh_text_input.bind("<FocusOut>", lambda e: self._save_current_edit())
                
                # 更新UI状态
                self._update_ui_state(interactive=True, item_selected=True)
                self.zh_text_input.focus_set()
                # 显示匹配的术语
                self._show_matching_terms(item_data['en'])

    def find_next(self, params):
        find_text = params["find_text"]
        if not find_text:
            return

        direction = 1 if params["direction"] == "down" else -1
        
        all_items = self._get_searchable_items(params["scope"])
        if not all_items:
            # 检查当前项目是否选中但无条目，或无项目
            if params["scope"] == 'current' and self.ns_tree.selection():
                messagebox.showinfo("搜索提示", "当前项目中没有可搜索的条目。", parent=self)
            elif params["scope"] == 'all':
                messagebox.showinfo("搜索提示", "没有可搜索的项目或条目。", parent=self)
            return

        # 获取当前选中的项目
        current_selection = self.trans_tree.selection()
        start_index = -1
        if current_selection:
            selected_item = current_selection[0]
            # 使用字典加速查找，时间复杂度O(1) instead of O(n)
            item_to_index = {item: idx for idx, item in enumerate(all_items)}
            start_index = item_to_index.get(selected_item, -1)
        
        # 计算搜索顺序
        if direction == 1:  # 向下搜索
            ordered_items = all_items[start_index+1:] + (all_items if params["wrap"] else [])
        else:  # 向上搜索
            ordered_items = all_items[:start_index][::-1] + (all_items[::-1] if params["wrap"] else [])

        # 获取要搜索的列
        column_map = {"en": "en", "zh": "zh", "all": "all"}
        search_column = column_map.get(params["search_column"], "all")
        match_case = params["match_case"]

        # 执行搜索
        for iid in ordered_items:
            ns, idx = self._get_ns_idx_from_iid(iid)
            if ns is None or idx is None:
                continue

            item = self.translation_data[ns]['items'][idx]
            key = item.get('key', '')
            en_text = item.get('en', '')
            zh_text = item.get('zh', '')

            # 根据搜索列进行匹配
            found = False
            if search_column == "en" or search_column == "all":
                if match_case:
                    if find_text in en_text:
                        found = True
                else:
                    if find_text.lower() in en_text.lower():
                        found = True
            if not found and (search_column == "zh" or search_column == "all"):
                if match_case:
                    if find_text in zh_text:
                        found = True
                else:
                    if find_text.lower() in zh_text.lower():
                        found = True
            if not found and search_column == "all":
                if match_case:
                    if find_text in key:
                        found = True
                else:
                    if find_text.lower() in key.lower():
                        found = True

            if found:
                # 保存当前编辑
                self._save_current_edit()
                
                # 切换到对应的命名空间
                current_ns_selection = self.ns_tree.selection()
                if not current_ns_selection or current_ns_selection[0] != ns:
                    # 切换命名空间并重新填充条目
                    self.ns_tree.selection_set(ns)
                    self.ns_tree.focus(ns)
                    self.ns_tree.see(ns)
                    self.update_idletasks()
                    self._populate_item_list()
                
                # 直接使用_iid重新构建当前模组下的正确ID
                current_mod_items = self.trans_tree.get_children()
                target_iid = f"{ns}___{idx}"
                
                # 选中并滚动到找到的项目
                if target_iid in current_mod_items:
                    self.trans_tree.selection_set(target_iid)
                    self.trans_tree.focus(target_iid)
                    self.trans_tree.see(target_iid)
                    
                    # 触发项目选中事件，更新编辑器内容
                    self._on_item_selected()
                return

        # 如果没有找到匹配项
        messagebox.showinfo("搜索完成", f"未找到更多包含 '{find_text}' 的条目。", parent=self)

    def replace_current_and_find_next(self, params):
        find_text = params["find_text"]
        replace_text = params["replace_text"]
        if not find_text:
            return

        # 获取当前选中的项目
        selection = self.trans_tree.selection()
        if not selection:
            # 如果没有选中项目，先查找第一个匹配项
            self.find_next(params)
            return

        iid = selection[0]
        ns, idx = self._get_ns_idx_from_iid(iid)
        if ns is None or idx is None:
            return

        item = self.translation_data[ns]['items'][idx]
        match_case = params["match_case"]
        search_column = params.get("search_column", "all")

        # 获取要替换的文本
        key = item.get('key', '')
        en_text = item.get('en', '')
        zh_text = item.get('zh', '')

        # 检查当前项目是否包含要查找的内容
        found = False
        target_text = None
        target_field = None

        # 先检查当前选中字段是否包含要查找的内容
        current_selection = self.trans_tree.selection()
        if current_selection:
            # 检查每个可能的字段
            if search_column == "en" or search_column == "all":
                if match_case:
                    if find_text in en_text:
                        found = True
                        target_text = en_text
                        target_field = "en"
                else:
                    if find_text.lower() in en_text.lower():
                        found = True
                        target_text = en_text
                        target_field = "en"
            
            if not found and (search_column == "zh" or search_column == "all"):
                if match_case:
                    if find_text in zh_text:
                        found = True
                        target_text = zh_text
                        target_field = "zh"
                else:
                    if find_text.lower() in zh_text.lower():
                        found = True
                        target_text = zh_text
                        target_field = "zh"
            
            if not found and search_column == "all":
                if match_case:
                    if find_text in key:
                        found = True
                        target_text = key
                        target_field = "key"
                else:
                    if find_text.lower() in key.lower():
                        found = True
                        target_text = key
                        target_field = "key"

        if not found:
            # 如果当前项目不包含要查找的内容，直接查找下一个
            self.find_next(params)
            return

        # 执行替换
        new_text = None
        if match_case:
            new_text = target_text.replace(find_text, replace_text)
        else:
            # 不区分大小写替换
            new_text = re.sub(re.escape(find_text), replace_text, target_text, flags=re.IGNORECASE)

        if new_text != target_text:
            # 更新项目数据
            
            if target_field == "en":
                item['en'] = new_text
            elif target_field == "zh":
                item['zh'] = new_text
            elif target_field == "key":
                item['key'] = new_text
            
            item['source'] = '手动校对'
            
            # 更新UI
            self._update_item_in_tree(iid, item)
            
            # 如果替换的是当前编辑的字段，更新编辑器内容
            if target_field == "zh":
                self.zh_text_input.delete("1.0", tk.END)
                self.zh_text_input.insert("1.0", new_text)
            elif target_field == "en":
                # 更新原文显示
                self.en_text_display.delete("1.0", tk.END)
                self.en_text_display.insert("1.0", new_text)
            
            self._set_dirty(True)
            
            # 保存状态用于撤销/重做，与编辑操作使用相同的details结构
            # 注意：这里在执行替换操作后调用record_operation，与编辑操作的行为保持一致
            details = {
                'key': item.get('key', ''),
                'original_text': target_text,
                'new_text': new_text,
                'namespace': ns,
                'index': idx
            }
            self.record_operation('REPLACE', details, target_iid=iid)

        # 如果当前项目包含要查找的内容并执行了替换，保持在当前项目
        # 只有当当前项目不包含要查找的内容时，才查找下一个
        if not found:
            self.find_next(params)
        
    def _update_item_in_tree(self, iid, item):
        """更新树视图中的项目"""
        if self.trans_tree.exists(iid):
            # 前台显示时将 _comment_* 格式的键显示为 _comment
            display_key = item['key']
            if display_key.startswith('_comment_'):
                display_key = '_comment'
            
            # 准备新的条目数据
            new_values = (display_key, item['en'], item.get('zh', ''), item['source'])
            
            # 检查当前条目数据是否与新数据相同
            current_values = self.trans_tree.item(iid, 'values')
            if current_values != new_values:
                # 只有当数据实际发生变化时才更新UI
                self.trans_tree.item(iid, values=new_values)

    def replace_all(self, params):
        find_text = params["find_text"]
        replace_text = params["replace_text"]
        if not find_text:
            return

        # 确认替换操作
        if not messagebox.askyesno("全部替换", f"您确定要将所有 '{find_text}' 替换为 '{replace_text}' 吗？\n此操作可以被撤销。", parent=self):
            return

        # 保存当前编辑
        self._save_current_edit(record_undo=False)
        
        # 保存当前选中信息
        saved_selection = self.current_selection_info.copy() if self.current_selection_info else None
        saved_ns_selection = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
        
        # 取消当前选中状态，确保当前条目也能被替换
        self.trans_tree.selection_remove(self.trans_tree.selection())
        self.current_selection_info = None
        
        # 获取替换参数
        match_case = params["match_case"]
        scope = params["scope"]
        search_column = params.get("search_column", "all")
        
        # 获取要搜索的命名空间
        namespaces_to_search = []
        if scope == "current":
            selection = self.ns_tree.selection()
            if selection:
                namespaces_to_search.append(selection[0])
        else:
            namespaces_to_search.extend(self.translation_data.keys())

        if not namespaces_to_search:
            messagebox.showwarning("范围错误", "请先在左侧选择一个项目以确定替换范围。", parent=self)
            return
        
        # 保存当前状态用于撤销/重做（在执行替换操作前保存）
        target_iid = saved_selection['row_id'] if saved_selection else None
        details = {
            'find_text': find_text,
            'replace_text': replace_text,
            'match_case': match_case,
            'scope': scope,
            'search_column': search_column,
            'namespaces': namespaces_to_search
        }
        self.record_operation('REPLACE_ALL', details, target_iid=target_iid)
        
        replacement_count = 0
        
        # 编译正则表达式（带转义），只编译一次
        escaped_find = re.escape(find_text)
        flags = 0 if match_case else re.IGNORECASE
        compiled_re = re.compile(escaped_find, flags)
        
        # 执行替换
        for ns in namespaces_to_search:
            for idx, item in enumerate(self.translation_data[ns]['items']):
                key = item.get('key', '')
                en_text = item.get('en', '')
                zh_text = item.get('zh', '')

                # 检查是否匹配
                found = False
                fields_to_replace = []

                # 根据搜索列检查匹配
                if search_column == "en" or search_column == "all":
                    if compiled_re.search(en_text):
                        found = True
                        fields_to_replace.append("en")
                
                if search_column == "zh" or search_column == "all":
                    if compiled_re.search(zh_text):
                        found = True
                        fields_to_replace.append("zh")
                
                if search_column == "all":
                    if compiled_re.search(key):
                        found = True
                        fields_to_replace.append("key")

                # 执行替换
                if found:
                    changed = False
                    for field in fields_to_replace:
                        original_text = item.get(field, '')
                        new_text = compiled_re.sub(replace_text, original_text)
                        if new_text != original_text:
                            item[field] = new_text
                            changed = True
                    
                    if changed:
                        item['source'] = '手动校对'
                        replacement_count += 1
        
        # 更新UI状态
        self._set_dirty(True)
        
        # 更新树视图
        self._populate_namespace_tree()
        self._populate_item_list()
        
        # 显示替换结果
        messagebox.showinfo("替换完成", f"已完成 {replacement_count} 处替换。", parent=self)
        
        # 恢复选中状态并更新编辑器内容
        if saved_selection:
            ns = saved_selection['ns']
            idx = saved_selection['idx']
            
            # 确保左侧模组树选中正确的模组
            if saved_ns_selection and self.ns_tree.exists(saved_ns_selection):
                self.ns_tree.selection_set(saved_ns_selection)
                self.ns_tree.focus(saved_ns_selection)
                self.ns_tree.see(saved_ns_selection)
            
            # 重新构建正确的ID
            new_iid = f"{ns}___{idx}"
            
            if self.trans_tree.exists(new_iid):
                # 重新选择项目
                self.trans_tree.selection_set(new_iid)
                self.trans_tree.focus(new_iid)
                self.trans_tree.see(new_iid)
                
                # 更新当前选择信息
                self.current_selection_info = {
                    'ns': ns,
                    'idx': idx,
                    'row_id': new_iid
                }
                
                # 更新编辑器内容
                item = self.translation_data[ns]['items'][idx]
                self._set_editor_content(item['en'], item.get('zh', ''))
                
                # 更新UI状态
                self._update_ui_state(interactive=True, item_selected=True)
    
    def _get_ns_idx_from_iid(self, iid):
        try:
            ns, idx_str = iid.rsplit('___', 1)
            return ns, int(idx_str)
        except (ValueError, IndexError):
            return None, None

    def record_operation(self, operation_type, details=None, target_iid=None):
        """记录操作到历史
        
        Args:
            operation_type: 操作类型
            details: 操作详细信息
            target_iid: 目标条目ID
        """
        import uuid
        import time
        
        current_time = time.time()
        
        # 检查是否可以合并操作
        can_merge = False
        if (operation_type == 'EDIT' or operation_type == 'REPLACE') and self.operation_history:
            last_op = self.operation_history[-1]
            time_diff = current_time - self.last_operation_time
            
            if ((last_op['type'] == 'EDIT' or last_op['type'] == 'REPLACE') and 
                last_op['target_iid'] == target_iid and 
                time_diff < self.operation_merge_window):
                # 合并连续的编辑或替换操作
                last_op['timestamp'] = datetime.now().isoformat()
                last_op['details'] = details or {}
                # 对于编辑或替换操作，只保存被修改的命名空间
                ns, idx = self._get_ns_idx_from_iid(target_iid)
                if ns is not None:
                    last_op['state'] = {
                        ns: copy.deepcopy(self.translation_data.get(ns, {}))
                    }
                else:
                    last_op['state'] = copy.deepcopy(self.translation_data)
                can_merge = True
        
        if not can_merge:
            # 创建操作记录
            # 对于编辑和替换操作，只保存被修改条目的状态，而不是整个translation_data
            state_to_save = None
            if (operation_type == 'EDIT' or operation_type == 'REPLACE') and target_iid:
                # 解析目标条目ID，获取命名空间和索引
                ns, idx = self._get_ns_idx_from_iid(target_iid)
                if ns is not None and idx is not None:
                    # 只保存被修改的命名空间的数据
                    state_to_save = {
                        ns: copy.deepcopy(self.translation_data.get(ns, {}))
                    }
            
            # 如果不是编辑操作或无法获取目标条目，保存整个translation_data
            if state_to_save is None:
                state_to_save = copy.deepcopy(self.translation_data)
            
            operation = {
                'id': str(uuid.uuid4()),
                'type': operation_type,
                'description': self.OPERATION_TYPES.get(operation_type, '其他操作'),
                'timestamp': datetime.now().isoformat(),
                'target_iid': target_iid,
                'details': details or {},
                'state': state_to_save
            }
            
            # 当添加新操作时，截断操作历史到当前状态索引
            # 这样之前的灰色重做条目就会被移除
            if self.current_state_index < len(self.operation_history) - 1:
                self.operation_history = self.operation_history[:self.current_state_index + 1]
            
            # 添加到历史记录
            self.operation_history.append(operation)
            
            # 更新当前状态索引，使其指向最后一个操作
            self.current_state_index = len(self.operation_history) - 1
            
            # 限制历史记录大小
            if len(self.operation_history) > self.max_history_size:
                self.operation_history.pop(0)
                # 当删除最早的记录后，更新当前状态索引
                self.current_state_index = len(self.operation_history) - 1
            

        
        # 更新上次操作时间
        self.last_operation_time = current_time
        
        # 更新按钮状态
        self._update_history_buttons()
        
        return operation['id'] if not can_merge else self.operation_history[-1]['id']
    
    def _record_action(self, target_iid: str | None):
        """兼容旧接口"""
        self.record_operation('OTHER', target_iid=target_iid)

    def undo(self, event=None):
        """执行撤回操作，基于操作历史"""
        # 检查是否有可撤回的操作
        if self.current_state_index > 0:
            # 获取当前被撤销的操作
            revoked_operation = self.operation_history[self.current_state_index]
            
            # 计算目标状态索引（当前状态索引减一）
            target_index = self.current_state_index - 1
            
            # 获取目标状态
            target_state = self.operation_history[target_index]['state']
            
            # 检查目标状态是否只包含单个命名空间（编辑或替换操作的优化格式）
            if len(target_state) == 1 and (revoked_operation['type'] == 'EDIT' or revoked_operation['type'] == 'REPLACE'):
                # 对于编辑或替换操作的优化格式，只更新单个命名空间
                ns = list(target_state.keys())[0]
                self.translation_data[ns] = copy.deepcopy(target_state[ns])
            else:
                # 对于其他操作，恢复整个状态
                self.translation_data = copy.deepcopy(target_state)
            
            # 更新当前状态索引
            self.current_state_index = target_index
            
            # 确定撤销后要选中的条目
            # 如果是批量操作，保持当前选中状态；否则选中撤销操作的对应条目
            target_to_select = None
            if not self._is_batch_operation(revoked_operation):
                target_to_select = revoked_operation.get('target_iid')
            else:
                # 对于批量操作，保持当前选中状态
                if self.trans_tree.selection():
                    target_to_select = self.trans_tree.selection()[0]
            
            # 更新UI
            self._set_dirty(True)
            self._full_ui_refresh(target_to_select=target_to_select)
            self._update_history_buttons()
        else:
            messagebox.showinfo("提示", "没有可以撤销的操作。")

    def redo(self, event=None):
        """执行重做操作，基于操作历史"""
        # 检查是否有可重做的操作
        if self.current_state_index < len(self.operation_history) - 1:
            # 计算目标状态索引（当前状态索引加一）
            target_index = self.current_state_index + 1
            
            # 获取被重做的操作
            redo_operation = self.operation_history[target_index]
            
            # 获取目标状态
            target_state = self.operation_history[target_index]['state']
            
            # 检查目标状态是否只包含单个命名空间（编辑或替换操作的优化格式）
            if len(target_state) == 1 and (redo_operation['type'] == 'EDIT' or redo_operation['type'] == 'REPLACE'):
                # 对于编辑或替换操作的优化格式，只更新单个命名空间
                ns = list(target_state.keys())[0]
                self.translation_data[ns] = copy.deepcopy(target_state[ns])
            else:
                # 对于其他操作，恢复整个状态
                self.translation_data = copy.deepcopy(target_state)
            
            # 更新当前状态索引
            self.current_state_index = target_index
            
            # 确定重做后要选中的条目
            # 如果是批量操作，保持当前选中状态；否则选中重做操作的对应条目
            target_to_select = None
            if not self._is_batch_operation(redo_operation):
                target_to_select = redo_operation.get('target_iid')
            else:
                # 对于批量操作，保持当前选中状态
                if self.trans_tree.selection():
                    target_to_select = self.trans_tree.selection()[0]
            
            # 更新UI
            self._set_dirty(True)
            self._full_ui_refresh(target_to_select=target_to_select)
            self._update_history_buttons()
        else:
            messagebox.showinfo("提示", "没有可以重做的操作。")

    def _update_history_buttons(self):
        """更新历史按钮的状态"""
        # 撤回按钮：当当前状态索引大于0时可用
        self.undo_btn.config(state="normal" if self.current_state_index > 0 else "disabled")
        # 重做按钮：当当前状态索引小于操作历史长度减1时可用
        self.redo_btn.config(state="normal" if self.current_state_index < len(self.operation_history) - 1 else "disabled")

    def _is_batch_operation(self, operation: dict) -> bool:
        """检查操作是否为批量操作（包含多个子操作的复合操作）
        
        Args:
            operation: 操作记录字典
            
        Returns:
            如果是批量操作返回True，否则返回False
        """
        batch_types = {
            'BATCH_PROCESS',  # 批量处理
            'AI_TRANSLATION', # AI翻译
            'IMPORT',         # 导入
            'REPLACE_ALL',    # 全部替换
        }
        return operation.get('type') in batch_types

    def _select_item_by_id(self, iid: str):
        if not iid or not self.winfo_exists():
            return
        
        try:
            ns, idx_str = iid.rsplit('___', 1)
            idx = int(idx_str)
            
            # 确保命名空间被选中（_full_ui_refresh 中已经处理了，但这里做双重检查）
            if self.ns_tree.exists(ns):
                # 临时解绑命名空间选择事件，避免触发 _on_namespace_selected
                self.ns_tree.unbind("<<TreeviewSelect>>")
                
                # 如果当前选中的命名空间不是目标命名空间，切换到目标命名空间
                current_ns = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
                if current_ns != ns:
                    self.ns_tree.selection_set(ns)
                    self.ns_tree.focus(ns)
                    self.ns_tree.see(ns)
                    # 刷新项目列表以显示目标命名空间的条目
                    self._populate_item_list()
                
                # 重新构建iid（因为项目列表可能已刷新）
                new_iid = f"{ns}___{idx}"
                
                # 选择目标条目
                if self.trans_tree.exists(new_iid):
                    # 先清除当前选择信息，避免触发保存逻辑
                    self.current_selection_info = None
                    # 临时解绑选择事件，避免递归调用
                    self.trans_tree.unbind("<<TreeviewSelect>>")
                    self.trans_tree.selection_set(new_iid)
                    self.trans_tree.focus(new_iid)
                    self.trans_tree.see(new_iid)
                    # 强制刷新界面
                    self.trans_tree.update()
                    # 恢复事件绑定
                    self.trans_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
                    # 手动更新选择信息和编辑器内容
                    self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': new_iid}
                    # 保存选择信息，防止被 _restore_item_selection 覆盖
                    self._workbench_item_selection = {'ns': ns, 'idx': idx}
                    item_data = self.translation_data[ns]['items'][idx]
                    self.zh_text_input.edit_modified(False)
                    self._set_editor_content(item_data['en'], item_data.get('zh', ''))
                    self.zh_text_input.edit_modified(False)
                    self.status_label.config(text=f"正在编辑: {ns} / {item_data['key']}")
                    self._show_matching_terms(item_data['en'])
                
                # 恢复事件绑定
                self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        except Exception as e:
            pass
    

    
    def _full_ui_refresh(self, target_to_select: str | None = None):
        # 获取当前选中的命名空间（在刷新前保存）
        saved_ns = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
        
        # 如果有目标条目要选择，解析出目标命名空间
        target_ns = None
        if target_to_select:
            try:
                target_ns = target_to_select.rsplit('___', 1)[0]
            except Exception:
                target_ns = None
        
        self._populate_namespace_tree()
        
        # 刷新后，优先选择目标条目所在的命名空间
        if target_ns and self.ns_tree.exists(target_ns):
            # 临时解绑命名空间选择事件，避免触发 _on_namespace_selected
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.ns_tree.selection_set(target_ns)
            self.ns_tree.focus(target_ns)
            self.ns_tree.see(target_ns)
            # 恢复事件绑定
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        elif saved_ns and self.ns_tree.exists(saved_ns):
            # 临时解绑命名空间选择事件，避免触发 _on_namespace_selected
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.ns_tree.selection_set(saved_ns)
            # 恢复事件绑定
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        
        self._populate_item_list()

        if target_to_select:
            self._select_item_by_id(target_to_select)
        else:
            self._clear_editor()
            self.current_selection_info = None
            self._update_ui_state(interactive=True, item_selected=False)

    def _sort_by_column(self, col_id):
        items = []
        for k in self.ns_tree.get_children(''):
            try:
                if col_id == '#0':
                    value = self.ns_tree.item(k, 'text').lower()
                else:
                    value = int(self.ns_tree.set(k, col_id))
                items.append((k, value))
            except (ValueError, TypeError):
                continue
        
        if self.sort_column == col_id:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col_id
            # 根据列类型设置默认排序方向
            if col_id == 'completed':
                self.sort_reverse = True  # 已翻译列默认降序，已翻译多的项目显示在前面
            elif col_id == 'pending':
                self.sort_reverse = False  # 待翻译列默认升序，待翻译少的项目显示在前面
            else:
                self.sort_reverse = False  # 其他列默认升序
        
        items.sort(key=lambda t: t[1], reverse=self.sort_reverse)
        
        for index, (k, v) in enumerate(items):
            self.ns_tree.move(k, '', index)
    
    def _setup_treeview_tags(self):
        source_colors = { "个人词典[Key]": "#4a037b", "个人词典[原文]": "#4a037b", "模组自带": "#006400", "第三方汉化包": "#008080", "社区词典[Key]": "#00008b", "社区词典[原文]": "#00008b", "待翻译": "#b22222", "AI翻译": "#008b8b", "手动校对": "#ff8c00", "标点修正": "#ff6347", "空": "#808080" }
        for source, color in source_colors.items(): self.trans_tree.tag_configure(source, foreground=color)
        self.trans_tree.tag_configure("手动校对", font=('Microsoft YaHei UI', 9, 'normal'))

    def _populate_namespace_tree(self):
        self.ns_tree.delete(*self.ns_tree.get_children())
        for ns, data in sorted(self.translation_data.items()):
            items = data.get('items', [])
            if not items: continue
            
            # 分类统计
            total_count = len(items)
            
            # 计算已翻译和待翻译数量
            display_completed = 0
            display_untranslated = 0
            
            for item in items:
                en_text = item.get('en', '').strip()
                zh_text = item.get('zh', '').strip()
                source = item.get('source', '')
                
                # 检查是否已翻译
                if zh_text:
                    # 任何有译文的条目都算已翻译
                    display_completed += 1
                elif en_text:
                    # 原文不为空但译文为空的算待翻译
                    display_untranslated += 1
                # 原文和译文都为空的不统计到待翻译
            
            display_text = data.get('display_name', f"{ns} ({data.get('jar_name', 'Unknown')})")
            self.ns_tree.insert("", "end", iid=ns, text=display_text, values=(display_untranslated, display_completed))

    def _update_namespace_summary(self, ns: str):
        if not self.ns_tree.exists(ns):
            return
        
        items = self.translation_data[ns].get('items', [])
        if not items:
            self.ns_tree.set(ns, "pending", 0)
            self.ns_tree.set(ns, "completed", 0)
            return

        # 计算已翻译和待翻译数量
        display_completed = 0
        display_untranslated = 0
        
        for item in items:
            en_text = item.get('en', '').strip()
            zh_text = item.get('zh', '').strip()
            
            # 检查是否已翻译
            if zh_text:
                # 任何有译文的条目都算已翻译
                display_completed += 1
            elif en_text:
                # 原文不为空但译文为空的算待翻译
                display_untranslated += 1
            # 原文和译文都为空的不统计到待翻译
        
        self.ns_tree.set(ns, "pending", display_untranslated)
        self.ns_tree.set(ns, "completed", display_completed)

    def _populate_item_list(self):
        # 检查是否需要更新（避免重复更新）
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]):
            return
        ns = selection[0]
        
        # 获取当前树视图中的条目
        current_items = set(self.trans_tree.get_children())
        
        # 计算需要显示的条目
        expected_items = []
        items_to_add = []
        items_to_update = []
        
        for idx, item_data in enumerate(self.translation_data.get(ns, {}).get('items', [])):
            iid = f"{ns}___{idx}"
            expected_items.append(iid)
            
            # 确定条目的source标签
            en_text = item_data.get('en', '').strip()
            zh_text = item_data.get('zh', '').strip()
            source = item_data.get('source', '')
            
            # 如果没有source标签或者source标签为默认值，根据内容自动确定
            if not source or source == '待翻译' and not en_text:
                if not en_text:
                    if zh_text:
                        source = '手动校对'  # 原文为空但有译文，标记为手动校对
                    else:
                        source = '空'  # 原文为空且没有译文，标记为空
                elif not zh_text:
                    source = '待翻译'  # 原文不为空但没有译文，标记为待翻译
                else:
                    source = '手动校对'  # 原文不为空且有译文，标记为手动校对
            
            # 前台显示时将 _comment_* 格式的键显示为 _comment
            display_key = item_data['key']
            if display_key.startswith('_comment_'):
                display_key = '_comment'
            
            # 准备条目数据
            item_values = (display_key, item_data['en'], item_data.get('zh', ''), source)
            
            if iid not in current_items:
                # 新条目，需要添加
                items_to_add.append((iid, item_values, (source,)))
            else:
                # 现有条目，检查是否需要更新
                current_values = self.trans_tree.item(iid, 'values')
                if current_values != item_values:
                    items_to_update.append((iid, item_values, (source,)))
        
        # 删除不存在的条目
        items_to_delete = [iid for iid in current_items if iid not in expected_items]
        if items_to_delete:
            self.trans_tree.delete(*items_to_delete)
        
        # 批量添加新条目
        for iid, values, tags in items_to_add:
            self.trans_tree.insert("", "end", iid=iid, values=values, tags=tags)
        
        # 批量更新现有条目
        for iid, values, tags in items_to_update:
            self.trans_tree.item(iid, values=values, tags=tags)

    def _sort_items_by_default_order(self):
        """按照默认顺序排序条目，再次点击则反序"""
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]):
            return
        
        ns = selection[0]
        items = self.translation_data[ns].get('items', [])
        
        # 切换排序顺序
        self.trans_items_sort_reverse = not self.trans_items_sort_reverse
        
        # 计算排序后的条目顺序
        start_idx = len(items) - 1 if self.trans_items_sort_reverse else 0
        end_idx = -1 if self.trans_items_sort_reverse else len(items)
        step = -1 if self.trans_items_sort_reverse else 1
        
        # 通过移动条目来实现排序，避免清空和重新插入
        for new_index, idx in enumerate(range(start_idx, end_idx, step)):
            iid = f"{ns}___{idx}"
            if self.trans_tree.exists(iid):
                self.trans_tree.move(iid, '', new_index)
    
    def _sort_items_by_source(self):
        """按照来源列排序条目，再次点击则反序"""
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]):
            return
        
        ns = selection[0]
        items = self.translation_data[ns].get('items', [])
        
        # 切换排序顺序
        self.source_sort_reverse = not self.source_sort_reverse
        
        # 准备排序数据
        sortable_items = []
        for idx, item_data in enumerate(items):
            en_text = item_data.get('en', '').strip()
            zh_text = item_data.get('zh', '').strip()
            source = item_data.get('source', '')
            
            # 如果没有source标签或者source标签为默认值，根据内容自动确定
            if not source or source == '待翻译' and not en_text:
                if not en_text:
                    if zh_text:
                        source = '手动校对'  # 原文为空但有译文，标记为手动校对
                    else:
                        source = '空'  # 原文为空且没有译文，标记为空
                elif not zh_text:
                    source = '待翻译'  # 原文不为空但没有译文，标记为待翻译
                else:
                    source = '手动校对'  # 原文不为空且有译文，标记为手动校对
            
            sortable_items.append((source, idx, item_data))
        
        # 按照来源排序
        sortable_items.sort(key=lambda x: x[0], reverse=self.source_sort_reverse)
        
        # 通过移动条目来实现排序，避免清空和重新插入
        for new_index, (source, idx, item_data) in enumerate(sortable_items):
            iid = f"{ns}___{idx}"
            if self.trans_tree.exists(iid):
                self.trans_tree.move(iid, '', new_index)
    
    def _on_namespace_selected(self, event=None):
        self._save_current_edit()
        
        # 处理正常模式下的模组选择
        if hasattr(self, '_current_mode') and self._current_mode == 'comprehensive':
            return
        
        # 处理正常模式下的模组选择
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]): return
        
        current_mod = selection[0]
        # 从翻译数据中获取模组信息
        mod_data = self.translation_data.get(current_mod, {})
        # 使用模组ID作为命名空间
        current_namespace = current_mod.split(':')[0] if ':' in current_mod else current_mod
        
        # 检查是否在GitHub上传模式
        if hasattr(self, '_github_upload_ui') and self.github_upload_ui_container.winfo_ismapped():
            # 更新GitHub上传UI中的命名空间和分支
            self._github_upload_ui.update_namespace_and_branch(current_namespace)
        
        self.current_selection_info = None
        # 重置排序状态
        self.trans_items_sort_reverse = False
        self.source_sort_reverse = False
        self._populate_item_list()
        self._clear_editor()
        # 当选择模组时，启用GitHub上传按钮
        self._update_ui_state(interactive=True, item_selected=False)
        # 单独启用GitHub上传按钮，因为上传操作是针对整个模组的
        self.github_upload_button.config(state="normal")
        self.status_label.config(text=f"已选择项目: {current_mod}")

    def _on_item_selected(self, event=None):
        selection = self.trans_tree.selection()
        if not selection: return

        row_id = selection[0]
        ns, idx = self._get_ns_idx_from_iid(row_id)
        if ns is None: return
        
        # 先获取当前编辑器的内容和当前选择信息
        current_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        current_selection = self.current_selection_info
        
        # 检查是否有当前选择，并且编辑器内容与当前选择的译文不同
        # 只有当当前选择与新选择不同时才保存，避免重新选中同一条目时触发保存逻辑
        if current_selection and current_selection['row_id'] != row_id and current_zh_text != self.translation_data[current_selection['ns']]['items'][current_selection['idx']].get('zh', '').strip():
            # 如果不同，则保存当前编辑的内容
            self._save_current_edit()
        
        # 更新当前选择信息
        self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': row_id}
        item_data = self.translation_data[ns]['items'][idx]
        
        # 更新编辑器内容
        self.zh_text_input.edit_modified(False)
        self._set_editor_content(item_data['en'], item_data.get('zh', ''))
        self.zh_text_input.edit_modified(False)
        self._update_ui_state(interactive=True, item_selected=True)
        self.status_label.config(text=f"正在编辑: {ns} / {item_data['key']}")
        self.zh_text_input.focus_set()
        
        # 显示匹配的术语
        self._show_matching_terms(item_data['en'])

    def _on_text_modified_delayed(self, event=None):
        """延迟处理文本修改事件，减少频繁保存操作"""
        # 取消之前的定时器
        if self._text_modified_timer:
            self.after_cancel(self._text_modified_timer)
        
        # 设置新的定时器
        self._text_modified_timer = self.after(self._text_modified_delay, self._save_current_edit)
    
    def _on_text_modified(self, event=None):
        if self.zh_text_input.edit_modified():
            self._save_current_edit()
            self.zh_text_input.edit_modified(False)
            
    def _save_current_edit(self, record_undo=True):
        if not self.current_selection_info:
            return

        info = self.current_selection_info
        new_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        item = self.translation_data[info['ns']]['items'][info['idx']]
        original_zh = item.get('zh', '').strip()

        if original_zh != new_zh_text:
            self._set_dirty(True)
            item['zh'] = new_zh_text
            
            # 只有译文变化时才更新来源字段
            # 分类逻辑
            if not item.get('en', '').strip():
                # 原文为空的条目
                if new_zh_text:
                    # 原文为空但手动添加了译文，标记为手动校对（已翻译）
                    new_source = '手动校对'
                else:
                    # 原文为空且没有译文，标记为"空"状态
                    new_source = '空'
            else:
                # 原文不为空的条目
                is_now_pending = not new_zh_text
                new_source = '手动校对' if not is_now_pending else '待翻译'
            item['source'] = new_source
            
            if record_undo:
                details = {
                    'key': item['key'],
                    'original_text': original_zh,
                    'new_text': new_zh_text,
                    'namespace': info['ns'],
                    'index': info['idx']
                }
                self.record_operation('EDIT', details, target_iid=info['row_id'])
        else:
            # 译文未变化，保持原有来源不变
            new_source = item.get('source', '')

        current_source = new_source
        
        # 检查项目是否存在于树视图中，避免Tkinter错误
        if self.trans_tree.exists(info['row_id']):
            self.trans_tree.item(info['row_id'], values=(item['key'], item['en'], item['zh'], current_source), tags=(current_source,))
        
        self._update_namespace_summary(info['ns'])

    def _set_dirty(self, is_dirty: bool):
        self.is_dirty = is_dirty
        self.save_button.config(bootstyle="primary" if is_dirty else "primary-outline")
        
        # 取消之前的延迟保存定时器
        if hasattr(self, '_session_save_timer') and self._session_save_timer:
            self.after_cancel(self._session_save_timer)
        
        if self.main_window and self.is_dirty:
            # 添加延迟保存机制，避免过于频繁的会话保存
            # 3秒后执行保存，期间有新的修改会取消之前的定时器
            self._session_save_timer = self.after(3000, self._save_session_with_delay)
        
        # 实现自动保存项目数据（延迟执行）
        if self.is_dirty and self.current_project_path:
            # 取消之前的自动保存定时器
            if hasattr(self, '_auto_save_timer') and self._auto_save_timer:
                self.after_cancel(self._auto_save_timer)
            # 3秒后执行自动保存，期间有新的修改会取消之前的定时器
            self._auto_save_timer = self.after(3000, lambda: self._perform_save(self.current_project_path))
    
    def _save_session_with_delay(self):
        """延迟保存会话"""
        if self.main_window and self.is_dirty:
            self.main_window._save_current_session()

    def _perform_save(self, save_path) -> bool:
        latest_data = self.translation_data
        
        save_data = {
            "version": "2.3", 
            "timestamp": datetime.now().isoformat(),
            "workbench_data": latest_data, 
            "namespace_formats": self.namespace_formats,
            "raw_english_files": self.raw_english_files,
            "module_names": self.module_names,
            "project_name": self.project_name,
            "current_settings": self.current_settings,
            "operation_history": self.operation_history
        }
        try:
            with open(save_path, 'w', encoding='utf-8') as f: 
                json.dump(save_data, f, indent=4, ensure_ascii=False)
            
            self.current_project_path = save_path
            self._set_dirty(False)
            self.status_label.config(text=f"项目已成功保存到: {Path(save_path).name}")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"保存项目文件时出错：\n{e}", parent=self)
            return False

    def _save_project(self) -> bool:
        path_to_save = self.current_project_path
        if not path_to_save:
            return self._save_project_as()
        
        return self._perform_save(path_to_save)

    def _save_project_as(self) -> bool:
        path_to_save = filedialog.asksaveasfilename(
            title="项目另存为",
            defaultextension=".sav",
            filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json")],
            initialfile=self.project_name
        )
        if not path_to_save:
            return False
        
        return self._perform_save(path_to_save)

    def _on_close_request(self, force_close=False, on_confirm=None):
        self.unbind_all("<Control-z>")
        self.unbind_all("<Control-y>")
        self.unbind_all("<Control-s>")

        self._save_current_edit()
        
        def do_confirm():
            if on_confirm:
                on_confirm()
            elif self.cancel_callback:
                self.cancel_callback()

        if not force_close and self.is_dirty:
            response = messagebox.askyesnocancel(
                "保存更改?", 
                f"项目有未保存的更改，是否要保存？",
                parent=self
            )
            if response is True:
                if self._save_project():
                    do_confirm()
            elif response is False:
                do_confirm()
            else: 
                self.bind_all("<Control-z>", self.undo)
                self.bind_all("<Control-y>", self.redo)
                self.bind_all("<Control-s>", lambda e: self._save_project())
                return
        else:
            do_confirm()
            
    def _save_and_jump_sequential(self, event=None):
        self._save_and_jump(lambda items, current_id: items[(items.index(current_id) + 1) % len(items)])
        return "break"

    def _save_and_jump_pending(self, event=None):
        def find_next_pending(items, current_id):
            start_index = items.index(current_id)
            for row_id in items[start_index+1:] + items[:start_index+1]:
                ns, idx = self._get_ns_idx_from_iid(row_id)
                if ns is None: continue
                item = self.translation_data[ns]['items'][idx]
                if not item.get('zh', '').strip() and item.get('en', '').strip():
                    return row_id
            ui_utils.show_info("恭喜", f"项目 '{self.current_selection_info['ns']}' 中已没有待翻译的条目！", parent=self)
            return None
        self._save_and_jump(find_next_pending)
        return "break"

    def _save_and_jump(self, next_finder_func):
        self._save_current_edit()
        if not (self.current_selection_info and self.current_selection_info.get('idx') is not None): return
        
        all_item_ids = self.trans_tree.get_children()
        if not all_item_ids: return
            
        try:
            next_row_id = next_finder_func(all_item_ids, self.current_selection_info['row_id'])
            if next_row_id:
                self.trans_tree.selection_set(next_row_id)
                self.trans_tree.focus(next_row_id)
                self.trans_tree.see(next_row_id)
        except (ValueError, IndexError): pass

    def _update_ui_state(self, interactive: bool, item_selected: bool, ns_select_mode=None):
        if interactive:
            base_state = "normal"
            # 根据当前模式决定选中模式
            if ns_select_mode is None:
                ns_select_mode = "extended" if self._current_mode == "comprehensive" else "browse"
            self.ns_tree.config(selectmode=ns_select_mode)
            self.trans_tree.config(selectmode="browse")
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
            self.trans_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        else:
            base_state = "disabled"
            self.ns_tree.config(selectmode="none")
            self.trans_tree.config(selectmode="none")
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.trans_tree.unbind("<<TreeviewSelect>>")
            self.ns_tree.selection_set()
            self.trans_tree.selection_set()

        self.finish_button.config(state=base_state)
        self.save_button.config(state=base_state)
        
        # 直接检查当前是否在特殊模式下
        # 1. 检查是否在GitHub上传模式
        is_in_github_upload_mode = False
        if hasattr(self, 'github_upload_ui_container'):
            try:
                is_in_github_upload_mode = self.github_upload_ui_container.winfo_ismapped()
            except:
                pass
        
        # 2. 检查是否在翻译控制台模式
        is_in_translation_console_mode = False
        if hasattr(self, '_current_mode'):
            is_in_translation_console_mode = self._current_mode == 'comprehensive'
        
        # 3. 综合判断
        is_in_special_mode = is_in_github_upload_mode or is_in_translation_console_mode
        
        # 只有在普通工作台模式下才更新按钮状态
        if not is_in_special_mode:
            # 更新功能切换按钮状态
            self.mode_switch_btn.config(state=base_state)
            
            # GitHub上传按钮始终启用，不需要选中项目
            self.github_upload_button.config(state="normal")
        
        if item_selected and interactive and self.current_selection_info:
            # 检查当前条目是否已存在于个人词典中
            from utils import config_manager
            user_dict = config_manager.load_user_dict()
            info = self.current_selection_info
            item_data = self.translation_data[info['ns']]['items'][info['idx']]
            key, origin_name = item_data['key'], item_data['en']
            translation = self.zh_text_input.get("1.0", "end-1c").strip()
            
            # 检查key和origin_name是否都在词典中，且译文相同
            key_in_dict = key in user_dict["by_key"]
            origin_in_dict = origin_name in user_dict["by_origin_name"]
            
            # 如果key和origin_name都在词典中，且译文相同
            if key_in_dict and origin_in_dict:
                key_trans = user_dict["by_key"][key]
                origin_trans = user_dict["by_origin_name"][origin_name]
                if key_trans == translation and origin_trans == translation:
                    # 已添加到词典，禁用按钮并更改文本
                    self.add_to_dict_btn.config(state="disabled", text="已添加到词典")
                    self.zh_text_input.config(state="normal", cursor="xterm")
                    return
            
            # 否则，启用按钮并显示正常文本
            self.add_to_dict_btn.config(state="normal", text="添加到词典")
            self.zh_text_input.config(state="normal", cursor="xterm")
        else:
            self.add_to_dict_btn.config(state="disabled", text="添加到词典")
            self.zh_text_input.config(state="disabled", cursor="")
            
    def _toggle_github_upload_mode(self, enter_mode=True):
        """在翻译工作台和GitHub上传模式之间切换"""
        # 保存当前编辑
        self._save_current_edit()
        
        if enter_mode:
            # 进入GitHub上传模式
            # 保存翻译工作台模式的选中状态
            if not hasattr(self, '_workbench_selection'):
                self._workbench_selection = []
            self._workbench_selection = list(self.ns_tree.selection())
            
            # 保存当前选中的条目信息
            if not hasattr(self, '_workbench_item_selection'):
                self._workbench_item_selection = None
            if self.current_selection_info:
                self._workbench_item_selection = {
                    'ns': self.current_selection_info['ns'],
                    'idx': self.current_selection_info['idx'],
                    'row_id': self.current_selection_info['row_id']
                }
            else:
                self._workbench_item_selection = None
            
            # 取消当前所有已选中的条目状态
            self.trans_tree.selection_clear()
            # 清除当前选择信息
            self.current_selection_info = None
            
            # 隐藏工作区UI
            self.workbench_ui_container.pack_forget()
            
            # 显示GitHub上传UI
            self.github_upload_ui_container.pack(fill="both", expand=True)
            
            # 更新按钮文本和命令
            self.github_upload_button.config(text="返回翻译工作台", command=lambda: self._toggle_github_upload_mode(False), bootstyle="warning")
            # 禁用翻译控制台按钮
            self.mode_switch_btn.config(state="disabled")
            
            # 更新状态栏
            self.status_label.config(text="GitHub上传模式 - 配置上传选项并执行上传")
        else:
            # 返回翻译工作台模式
            # 隐藏GitHub上传UI
            self.github_upload_ui_container.pack_forget()
            
            # 显示工作区UI
            self.workbench_ui_container.pack(fill="both", expand=True)
            
            # 1. 首先将选择模式改为单选
            self.ns_tree.config(selectmode="browse")
            
            # 2. 清除所有选中状态
            self.ns_tree.selection_clear()
            
            # 3. 恢复翻译工作台模式的选中状态
            if hasattr(self, '_workbench_selection') and self._workbench_selection:
                # 翻译工作台模式只允许选中一个模组，所以只取第一个
                self.ns_tree.selection_set(self._workbench_selection[0])
            
            # 4. 确保只有一个选中项（防止任何可能的多选残留）
            current_selection = self.ns_tree.selection()
            if len(current_selection) > 1:
                # 如果仍然有多个选中，只保留第一个
                self.ns_tree.selection_clear()
                self.ns_tree.selection_set(current_selection[0])
            
            # 切换回翻译工作台模式时，重新绑定事件处理函数
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
            
            # 更新按钮文本和命令
            self.github_upload_button.config(text="上传到GitHub", command=self._on_github_upload, bootstyle="warning")
            # 启用翻译控制台按钮
            self.mode_switch_btn.config(state="normal")
            
            # 更新状态栏
            selection = self.ns_tree.selection()
            if selection:
                self.status_label.config(text=f"已选择项目: {selection[0]}")
            else:
                self.status_label.config(text="未选择任何项目")
            
            # 重新填充项目列表
            self._populate_item_list()
            
            # 更新UI状态
            self._update_ui_state(interactive=True, item_selected=bool(selection))
            
            # 等待条目列表加载完成后，根据保存的信息重新选中条目
            if hasattr(self, '_workbench_item_selection') and self._workbench_item_selection:
                # 使用after方法确保在UI更新后执行重新选中操作
                self.after(100, self._restore_item_selection)
    
    def _toggle_mode(self):
        """在翻译工作台和翻译控制台功能之间切换"""
        # 保存当前编辑
        self._save_current_edit()
        
        if self._current_mode == "workbench":
            # 保存翻译工作台模式的选中状态
            if not hasattr(self, '_workbench_selection'):
                self._workbench_selection = []
            self._workbench_selection = list(self.ns_tree.selection())
            
            # 保存当前选中的条目信息
            if not hasattr(self, '_workbench_item_selection'):
                self._workbench_item_selection = None
            # 保存当前选中的条目信息（只保存标识符，不保存数据）
            if self.current_selection_info:
                self._workbench_item_selection = {
                    'ns': self.current_selection_info['ns'],
                    'idx': self.current_selection_info['idx'],
                    'row_id': self.current_selection_info['row_id']
                }
            else:
                self._workbench_item_selection = None
            
            # 取消当前所有已选中的条目状态
            self.trans_tree.selection_clear()
            # 清除当前选择信息，避免与翻译控制台的操作冲突
            self.current_selection_info = None
            
            # 进入翻译控制台模式
            self._current_mode = "comprehensive"
            
            # 隐藏工作区UI
            self.workbench_ui_container.pack_forget()
            
            # 先更新模组列表为多选模式
            self.ns_tree.config(selectmode="extended")
            
            # 然后恢复翻译控制台模式的选中状态
            if hasattr(self, '_comprehensive_selection'):
                self.ns_tree.selection_set(self._comprehensive_selection)
            else:
                self.ns_tree.selection_clear()
            
            # 显示翻译控制台UI
            self.comprehensive_ui_container.pack(fill="both", expand=True)
            if self._comprehensive_ui is None:
                # 创建翻译控制台UI组件
                from gui.enhanced_comprehensive_processing import EnhancedComprehensiveProcessing
                self._comprehensive_ui = EnhancedComprehensiveProcessing(self.comprehensive_ui_container, self)
                self._comprehensive_ui.pack(fill="both", expand=True)
                # 初始化时更新批次预览
                self.after(0, lambda: self._comprehensive_ui._update_batch_preview())
            
            # 更新按钮文本
            self.mode_switch_btn.config(text="返回翻译工作台")
            # 禁用GitHub上传按钮
            self.github_upload_button.config(state="disabled")
            
            # 更新状态栏
            self.status_label.config(text="翻译控制台模式 - 可多选模组进行批量操作")
            # 确保在翻译控制台模式下，只有翻译控制台的事件处理函数被绑定
            self.ns_tree.unbind("<<TreeviewSelect>>")
            # 绑定翻译控制台模式的事件处理函数
            self.ns_tree.bind("<<TreeviewSelect>>", self._comprehensive_ui._on_module_selection_change)
            self.ns_tree.bind("<Button-1>", self._comprehensive_ui._on_module_click)
            self.ns_tree.bind("<ButtonPress-1>", self._comprehensive_ui._on_module_press)
            self.ns_tree.bind("<B1-Motion>", self._comprehensive_ui._on_module_drag)
            self.ns_tree.bind("<ButtonRelease-1>", self._comprehensive_ui._on_module_release)
            # 更新批次预览（确保在选择状态恢复后调用）
            self.after(0, lambda: self._comprehensive_ui._update_batch_preview() if hasattr(self, '_comprehensive_ui') else None)
        else:
            # 保存翻译控制台模式的选中状态
            if not hasattr(self, '_comprehensive_selection'):
                self._comprehensive_selection = []
            self._comprehensive_selection = list(self.ns_tree.selection())
            
            # 切换回翻译工作台模式
            self._current_mode = "workbench"
            
            # 隐藏翻译控制台UI
            self.comprehensive_ui_container.pack_forget()
            
            # 显示工作区UI
            self.workbench_ui_container.pack(fill="both", expand=True)
            
            # 1. 首先将选择模式改为单选
            self.ns_tree.config(selectmode="browse")
            
            # 2. 清除所有选中状态
            self.ns_tree.selection_clear()
            
            # 3. 恢复翻译工作台模式的选中状态
            if hasattr(self, '_workbench_selection') and self._workbench_selection:
                # 翻译工作台模式只允许选中一个模组，所以只取第一个
                self.ns_tree.selection_set(self._workbench_selection[0])
            
            # 4. 确保只有一个选中项（防止任何可能的多选残留）
            current_selection = self.ns_tree.selection()
            if len(current_selection) > 1:
                # 如果仍然有多个选中，只保留第一个
                self.ns_tree.selection_clear()
                self.ns_tree.selection_set(current_selection[0])
            
            # 切换回翻译工作台模式时，重新绑定事件处理函数
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
            
            # 更新按钮文本
            self.mode_switch_btn.config(text="进入翻译控制台")
            # 启用GitHub上传按钮
            self.github_upload_button.config(state="normal")
            
            # 更新状态栏
            selection = self.ns_tree.selection()
            if selection:
                self.status_label.config(text=f"已选择项目: {selection[0]}")
            else:
                self.status_label.config(text="未选择任何项目")
            
            # 重新填充项目列表
            self._populate_item_list()
            
            # 更新UI状态
            self._update_ui_state(interactive=True, item_selected=bool(selection))
            
            # 等待条目列表加载完成后，根据保存的信息重新选中条目
            if hasattr(self, '_workbench_item_selection') and self._workbench_item_selection:
                # 使用after方法确保在UI更新后执行重新选中操作
                self.after(100, self._restore_item_selection)
    
    def _show_export_menu(self):
        """显示导出菜单"""
        export_menu = tk.Menu(self, tearoff=0)
        
        # 导出范围选项
        scope_menu = tk.Menu(export_menu, tearoff=0)
        scope_menu.add_command(label="当前模组的待译项", command=lambda: self._export_to_file(scope="current"))
        scope_menu.add_command(label="所有模组的待译项", command=lambda: self._export_to_file(scope="all"))
        scope_menu.add_command(label="当前模组的所有项", command=lambda: self._export_to_file(scope="current_all"))
        scope_menu.add_command(label="所有模组的所有项", command=lambda: self._export_to_file(scope="all_all"))
        export_menu.add_cascade(label="导出到文件", menu=scope_menu)
        
        # 复制到剪贴板选项
        copy_menu = tk.Menu(export_menu, tearoff=0)
        copy_menu.add_command(label="当前模组的待译项", command=lambda: self._copy_to_clipboard(scope="current"))
        copy_menu.add_command(label="所有模组的待译项", command=lambda: self._copy_to_clipboard(scope="all"))
        copy_menu.add_command(label="当前模组的所有项", command=lambda: self._copy_to_clipboard(scope="current_all"))
        copy_menu.add_command(label="所有模组的所有项", command=lambda: self._copy_to_clipboard(scope="all_all"))
        export_menu.add_cascade(label="复制到剪贴板", menu=copy_menu)
        
        # 显示菜单
        x, y = self.export_btn.winfo_rootx(), self.export_btn.winfo_rooty() + self.export_btn.winfo_height()
        export_menu.post(x, y)
        
    def _show_import_menu(self):
        """显示导入菜单"""
        import_menu = tk.Menu(self, tearoff=0)
        import_menu.add_command(label="从文件导入", command=self._import_from_file)
        import_menu.add_command(label="从剪贴板导入", command=self._import_from_clipboard)
        
        # 显示菜单
        x, y = self.import_btn.winfo_rootx(), self.import_btn.winfo_rooty() + self.import_btn.winfo_height()
        import_menu.post(x, y)
        
    def _get_export_data(self, scope):
        """获取要导出的数据"""
        export_data = []
        namespaces_to_export = []
        
        if scope in ["current", "current_all"]:
            selection = self.ns_tree.selection()
            if not selection:
                messagebox.showwarning("范围错误", "请先在左侧选择一个项目以确定导出范围。", parent=self)
                return None
            namespaces_to_export = [selection[0]]
        else:
            namespaces_to_export = list(self.translation_data.keys())
        
        for ns in namespaces_to_export:
            ns_data = self.translation_data[ns]
            items = ns_data.get('items', [])
            for item in items:
                if scope in ["current", "all"] and item.get('zh', '').strip():
                    continue  # 只导出待译项
                export_item = {
                    'key': item['key'],
                    'en': item['en'],
                    'zh': item.get('zh', '')
                }
                export_data.append(export_item)
        
        return export_data
        
    def _export_to_file(self, scope):
        """导出数据到文件"""
        export_data = self._get_export_data(scope)
        if not export_data:
            return
        
        file_path = filedialog.asksaveasfilename(
            title="导出翻译数据",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialfile=f"translation_export_{scope}.json"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("导出成功", f"已成功导出 {len(export_data)} 条记录到 {file_path}", parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", f"导出数据时出错：{e}", parent=self)
            logging.error(f"导出数据失败: {e}")
            
    def _copy_to_clipboard(self, scope):
        """复制数据到剪贴板"""
        export_data = self._get_export_data(scope)
        if not export_data:
            return
        
        try:
            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            self.clipboard_clear()
            self.clipboard_append(json_str)
            messagebox.showinfo("复制成功", f"已成功复制 {len(export_data)} 条记录到剪贴板", parent=self)
        except Exception as e:
            messagebox.showerror("复制失败", f"复制数据到剪贴板时出错：{e}", parent=self)
            logging.error(f"复制数据到剪贴板失败: {e}")
            
    def _import_from_file(self):
        """从文件导入翻译结果"""
        file_path = filedialog.askopenfilename(
            title="导入翻译结果",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            self._process_import_data(import_data)
        except Exception as e:
            messagebox.showerror("导入失败", f"从文件导入数据时出错：{e}", parent=self)
            logging.error(f"从文件导入数据失败: {e}")
            
    def _import_from_clipboard(self):
        """从剪贴板导入翻译结果"""
        try:
            clipboard_text = self.clipboard_get()
            import_data = json.loads(clipboard_text)
            self._process_import_data(import_data)
        except json.JSONDecodeError:
            messagebox.showerror("导入失败", "剪贴板中的数据格式不正确，请确保是有效的JSON格式。", parent=self)
        except Exception as e:
            messagebox.showerror("导入失败", f"从剪贴板导入数据时出错：{e}", parent=self)
            logging.error(f"从剪贴板导入数据失败: {e}")
            
    def _process_import_data(self, import_data):
        """处理导入的翻译数据"""
        if not isinstance(import_data, list):
            messagebox.showerror("导入失败", "导入数据格式不正确，请确保是包含翻译条目的列表。", parent=self)
            return
        
        # 保存当前状态用于撤销
        details = {
            'source': 'file' if hasattr(self, '_import_from_file') else 'clipboard',
            'total_items': len(import_data),
            'expected_format': 'list of translation items'
        }
        self.record_operation('IMPORT', details, target_iid=None)
        
        updated_count = 0
        skipped_count = 0
        not_found_count = 0
        
        for import_item in import_data:
            key = import_item.get('key')
            zh = import_item.get('zh', '').strip()
            
            if not key:
                skipped_count += 1
                continue
            
            # 查找匹配的条目
            found = False
            # 遍历所有命名空间查找匹配的 key
            for namespace in self.translation_data:
                items = self.translation_data[namespace]['items']
                for item in items:
                    if item['key'] == key:
                        # 更新翻译
                        if zh:
                            item['zh'] = zh
                            item['source'] = '外部导入'
                            updated_count += 1
                        found = True
                        break
                if found:
                    break
            
            if not found:
                not_found_count += 1
        
        # 更新UI
        self._full_ui_refresh()
        self._set_dirty(True)
        
        # 显示导入结果
        message = f"导入完成！\n"
        message += f"成功更新: {updated_count} 条\n"
        message += f"跳过无效条目: {skipped_count} 条\n"
        message += f"未找到匹配项: {not_found_count} 条"
        messagebox.showinfo("导入结果", message, parent=self)

    def _clear_editor(self):
        self._set_editor_content("", "")
        
    def _show_matching_terms(self, en_text: str):
        """
        显示匹配的术语，支持精确单词匹配和不区分大小写合并
        使用防抖和缓存机制优化性能
        Args:
            en_text: 原文文本
        """
        # 1. 增加搜索ID，标记当前请求
        current_search_id = self._current_search_id + 1
        self._current_search_id = current_search_id
        
        # 2. 检查缓存，避免重复计算
        cache_key = en_text
        if cache_key in self._term_match_cache:
            # 从缓存中获取术语并更新访问顺序
            self._term_match_cache.move_to_end(cache_key)
            # 检查是否为最新请求，只有最新请求才更新UI
            if current_search_id == self._current_search_id:
                display_terms = self._term_match_cache[cache_key]
                self._update_term_display(display_terms)
            return
        
        # 2. 防抖机制：取消之前的更新任务
        if self._term_update_id:
            self.after_cancel(self._term_update_id)
        
        # 3. 取消当前正在运行的术语搜索
        self._term_search_cancelled = True
        
        # 4. 立即显示"正在搜索"提示
        self.term_text.config(state="normal")
        self.term_text.delete("1.0", tk.END)
        self.term_text.insert(tk.END, "正在搜索...")
        self.term_text.config(state="disabled")
        self.term_text.yview_moveto(0.0)
        
        # 5. 延迟执行术语匹配，减少UI阻塞
        def delayed_term_match():
            import threading
            from utils.dictionary_searcher import DictionarySearcher
            
            # 重置取消标志
            self._term_search_cancelled = False
            
            # 定义后台线程执行的函数
            def background_term_match():
                # 检查是否已被取消
                if self._term_search_cancelled:
                    return
                    
                matching_terms = []
                matched_terms_set = set()  # 避免重复匹配
                
                # 快速检查：如果文本为空，直接返回空列表
                if not en_text:
                    display_terms = []
                    # 清理缓存
                    self._term_match_cache[cache_key] = display_terms
                    self._term_match_cache.move_to_end(cache_key)  # 确保新添加的条目在末尾
                    self._cleanup_term_cache()  # 清理缓存以保持大小
                    # 检查是否为最新请求，只有最新请求才更新UI
                    if current_search_id == self._current_search_id:
                        try:
                            # 检查主窗口是否仍然存在
                            if self.winfo_exists():
                                self.after(0, lambda: self._update_term_display(display_terms))
                        except RuntimeError:
                            # 捕获主线程不在主循环中的错误
                            pass
                    return
                
                # 提取文本中的所有单词，用于快速过滤
                text_words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', en_text.lower()))
                
                # 快速检查：如果单词集合为空，直接返回空列表
                if not text_words:
                    display_terms = []
                    # 清理缓存
                    self._cleanup_term_cache()
                    self._term_match_cache[cache_key] = display_terms
                    # 检查是否为最新请求，只有最新请求才更新UI
                    if current_search_id == self._current_search_id:
                        try:
                            # 检查主窗口是否仍然存在
                            if self.winfo_exists():
                                self.after(0, lambda: self._update_term_display(display_terms))
                        except RuntimeError:
                            # 捕获主线程不在主循环中的错误
                            pass
                    return
                
                # 1. 处理个人词典中的术语
                user_dict = config_manager.load_user_dict()
                user_dict_origin_terms = user_dict.get("by_origin_name", {})
                
                for original, translation in user_dict_origin_terms.items():
                    # 检查是否已被取消
                    if self._term_search_cancelled:
                        return
                        
                    original_lower = original.lower()
                    if original_lower in text_words:
                        # 检查是否在文本中完整匹配
                        if re.search(rf'\b{re.escape(original)}\b', en_text, re.IGNORECASE):
                            temp_term = {
                                "id": f"user_dict_{original_lower}",
                                "original": original,
                                "translation": [translation],
                                "comment": "",
                                "domain": "",
                                "created_at": "",
                                "updated_at": ""
                            }
                            matching_terms.append(temp_term)
                            matched_terms_set.add(original)
                
                # 2. 处理社区词典中的术语
                config = config_manager.load_config()
                community_dict_path = config.get("community_dict_path", "")
                
                if community_dict_path:
                    searcher = DictionarySearcher(community_dict_path)
                    if searcher.is_available():
                        # 优化1：只排除已匹配的术语
                        filtered_words = [word for word in text_words if word not in matched_terms_set]
                        
                        # 优化2：如果过滤后的单词数量太多，限制查询数量
                        if len(filtered_words) > 15:
                            filtered_words = sorted(filtered_words, key=lambda x: len(x), reverse=True)[:15]
                        
                        # 只查询过滤后的单词
                        for word in filtered_words:
                            # 检查是否已被取消
                            if self._term_search_cancelled:
                                searcher.close()
                                return
                                
                            if word not in matched_terms_set:
                                # 在社区词典中查询该单词，限制结果数量
                                results = searcher.search_by_english(word, limit=3)
                                for result in results:
                                    # 检查是否已被取消
                                    if self._term_search_cancelled:
                                        searcher.close()
                                        return
                                        
                                    original = result.get("ORIGIN_NAME", "").strip()
                                    trans_name = result.get("TRANS_NAME", "").strip()
                                    
                                    if original and trans_name:
                                        # 过滤条件1：单词数不大于2
                                        word_count = len(original.split())
                                        if word_count > 2:
                                            continue
                                    
                                    # 过滤条件2：译文必须包含中文
                                    if not re.search('[一-鿿]', trans_name):
                                        continue
                                    
                                    original_lower = original.lower()
                                    # 检查是否在文本中完整匹配
                                    if original_lower in text_words and re.search(rf'\b{re.escape(original)}\b', en_text, re.IGNORECASE):
                                        # 检查是否已经存在该术语
                                        existing_term = next((t for t in matching_terms if t['original'].lower() == original_lower), None)
                                        if existing_term:
                                            # 如果存在，添加译文到现有术语
                                            if trans_name not in existing_term['translation']:
                                                existing_term['translation'].append(trans_name)
                                        else:
                                            # 如果不存在，创建新术语
                                            temp_term = {
                                                "id": f"community_dict_{original_lower}",
                                                "original": original,
                                                "translation": [trans_name],
                                                "comment": "",
                                                "domain": "",
                                                "created_at": "",
                                                "updated_at": ""
                                            }
                                            matching_terms.append(temp_term)
                                            matched_terms_set.add(original)
                        searcher.close()
                
                # 检查是否已被取消
                if self._term_search_cancelled:
                    return
                    
                # 3. 不区分大小写合并相同术语
                merged_terms = {}
                for term in matching_terms:
                    # 检查是否已被取消
                    if self._term_search_cancelled:
                        return
                        
                    term_lower = term['original'].lower()
                    if term_lower not in merged_terms:
                        merged_terms[term_lower] = []
                    merged_terms[term_lower].append(term)
                
                # 4. 从原文中提取实际的术语版本，并准备显示数据
                term_with_positions = []
                for term_lower, term_list in merged_terms.items():
                    # 检查是否已被取消
                    if self._term_search_cancelled:
                        return
                        
                    # 在原文中查找实际的术语版本（保持大小写）和位置
                    pattern = re.compile(rf'\b{re.escape(term_lower)}\b', re.IGNORECASE)
                    match = pattern.search(en_text)
                    if match:
                        actual_term = match.group(0)  # 原文中实际的术语版本
                        position = match.start()  # 记录首次出现的位置
                    else:
                        actual_term = term_list[0]['original']  # 否则使用术语库中的版本
                        position = float('inf')  # 未找到的术语放在最后
                    
                    # 按术语长度排序，选择最长的术语（可能有不同长度的变体）
                    term_list.sort(key=lambda x: len(x['original']), reverse=True)
                    primary_term = term_list[0]
                    
                    # 合并所有译文（去重）
                    all_translations = set()
                    for t in term_list:
                        if isinstance(t['translation'], list):
                            all_translations.update(t['translation'])
                        else:
                            all_translations.add(t['translation'])
                    
                    # 创建显示用的术语对象，移除来源信息
                    display_term = {
                        'actual_original': actual_term,
                        'original': primary_term['original'],
                        'translation': list(all_translations),
                        'domain': '',
                        'comment': '',  # 移除来源信息
                        'position': position
                    }
                    term_with_positions.append(display_term)
                
                # 检查是否已被取消
                if self._term_search_cancelled:
                    return
                    
                # 按照术语在原文中首次出现的位置排序
                display_terms = sorted(term_with_positions, key=lambda x: x['position'])
                
                # 缓存结果
                self._term_match_cache[cache_key] = display_terms
                self._term_match_cache.move_to_end(cache_key)  # 确保新添加的条目在末尾
                self._cleanup_term_cache()  # 清理缓存以保持大小
                
                # 检查是否为最新请求，只有最新请求才更新UI
                if current_search_id == self._current_search_id:
                    try:
                        # 检查主窗口是否仍然存在
                        if self.winfo_exists():
                            self.after(0, lambda: self._update_term_display(display_terms))
                    except RuntimeError:
                        # 捕获主线程不在主循环中的错误
                        pass
            
            # 使用线程池执行术语匹配
            self._thread_pool.submit(background_term_match)
        
        # 延迟执行术语匹配
        self._term_update_id = self.after(self._term_update_delay, delayed_term_match)
        
    def _update_term_display(self, display_terms):
        """
        更新术语提示区域的显示
        Args:
            display_terms: 要显示的术语列表
        """
        # 更新术语提示区域
        self.term_text.config(state="normal")
        self.term_text.delete("1.0", tk.END)
        # 确保术语提示区域正确换行
        self.term_text.config(height=5, wrap=tk.WORD)
        
        if display_terms:
            for i, term in enumerate(display_terms):
                # 使用原文中的实际版本显示，多个译文用分号分隔
                term_info = f"{term['actual_original']} → {'; '.join(term['translation'])}"
                # 只在不是最后一个术语时添加换行符
                if i < len(display_terms) - 1:
                    self.term_text.insert(tk.END, term_info + "\n")
                else:
                    self.term_text.insert(tk.END, term_info)
                # 绑定点击事件，支持点击插入术语
                self.term_text.tag_add(f"term_{i}", f"{i+1}.0", f"{i+1}.end")
                self.term_text.tag_bind(f"term_{i}", "<Button-1>", 
                                     lambda e, t=term: self._insert_term(t['translation']))
                # 添加悬停效果
                self.term_text.tag_configure(f"term_{i}", foreground="#0066cc")
        else:
            self.term_text.insert(tk.END, "未找到匹配的术语")
        
        self.term_text.config(state="disabled")
        self.term_text.yview_moveto(0.0)
    
    def _insert_term(self, translation):
        """
        将选中的术语插入到译文框中
        Args:
            translation: 术语译文（可能是字符串或列表）
        """
        if self.current_selection_info:
            # 处理翻译数据类型，确保是字符串
            if isinstance(translation, list):
                # 如果是列表，使用第一个译文
                trans_text = translation[0] if translation else ""
            else:
                trans_text = translation
            
            # 获取当前选中的文本范围
            try:
                # 如果有选中内容，替换选中的部分
                start = self.zh_text_input.index("sel.first")
                end = self.zh_text_input.index("sel.last")
                self.zh_text_input.delete(start, end)
                self.zh_text_input.insert(start, trans_text)
            except tk.TclError:
                # 如果没有选中内容，在当前光标位置插入
                cursor_pos = self.zh_text_input.index("insert")
                self.zh_text_input.insert(cursor_pos, trans_text)
            
            self._save_current_edit()
    
    def _update_term_suggestions(self, event=None):
        """
        实时更新术语提示
        """
        if self.current_selection_info:
            ns = self.current_selection_info['ns']
            idx = self.current_selection_info['idx']
            item_data = self.translation_data[ns]['items'][idx]
            self._show_matching_terms(item_data['en'])
    
    def _clear_term_cache(self):
        """
        清除术语缓存，当术语库更新时调用
        """
        self._term_match_cache.clear()
        logging.debug("术语缓存已清除")
    

    
    def _cleanup_term_cache(self):
        """
        清理术语缓存，保持缓存大小在合理范围内
        """
        while len(self._term_match_cache) > self._term_cache_max_size:
            # 删除最旧的条目（OrderedDict的第一个条目）
            self._term_match_cache.popitem(last=False)
        logging.debug(f"术语缓存已清理，当前大小: {len(self._term_match_cache)}")
    
    def reload_term_database(self):
        """
        重新加载术语库并清除缓存
        """
        self.term_db.reload()
        self._clear_term_cache()
    
    def destroy(self):
        """
        销毁TranslationWorkbench实例，释放资源
        """
        # 取消所有定时器
        if hasattr(self, '_term_update_id') and self._term_update_id:
            try:
                self.after_cancel(self._term_update_id)
            except:
                pass
        
        if hasattr(self, '_text_modified_timer') and self._text_modified_timer:
            try:
                self.after_cancel(self._text_modified_timer)
            except:
                pass
        
        if hasattr(self, '_session_save_timer') and self._session_save_timer:
            try:
                self.after_cancel(self._session_save_timer)
            except:
                pass
        
        if hasattr(self, '_auto_save_timer') and self._auto_save_timer:
            try:
                self.after_cancel(self._auto_save_timer)
            except:
                pass
        
        # 关闭线程池
        if hasattr(self, '_thread_pool') and self._thread_pool:
            try:
                self._thread_pool.shutdown(wait=False, cancel_futures=True)
            except:
                pass
        
        # 清除术语匹配缓存
        if hasattr(self, '_term_match_cache'):
            self._term_match_cache.clear()
        
        # 清除操作历史
        if hasattr(self, 'operation_history'):
            self.operation_history.clear()
        
        # 调用父类的destroy方法
        super().destroy()
    
    def _set_editor_content(self, en_text: str, zh_text: str):
        # 设置原文显示
        self.en_text_display.delete("1.0", "end")
        self.en_text_display.insert("1.0", en_text)
        # 确保原文栏正确换行并只显示实际文本
        self.en_text_display.config(height=5, wrap=tk.WORD)
        # 重置原文栏滚动条位置
        self.en_text_display.yview_moveto(0.0)
        self.en_text_display.xview_moveto(0.0)
        
        # 设置译文输入，确保文本末尾没有额外的换行符
        self.zh_text_input.config(state="normal")
        self.zh_text_input.delete("1.0", "end")
        self.zh_text_input.insert("1.0", zh_text)
        # 确保译文栏正确换行并只显示实际文本
        self.zh_text_input.config(height=5, wrap=tk.WORD)
        # 重置译文栏滚动条位置
        self.zh_text_input.yview_moveto(0.0)
        self.zh_text_input.xview_moveto(0.0)
        
        # 更新术语提示区域
        self._show_matching_terms(en_text)
    
    def _on_copy(self, event):
        """处理复制事件，确保只复制实际文本，不包含额外的换行和空格"""
        # 获取选中文本，如果没有选择则获取全部文本
        try:
            selected_text = self.zh_text_input.get("sel.first", "sel.last")
        except tk.TclError:
            # 如果没有选中任何文本，获取全部文本
            selected_text = self.zh_text_input.get("1.0", "end-1c")
        
        # 清理文本，移除多余的空白和换行符
        cleaned_text = selected_text.strip()
        
        # 将清理后的文本放入剪贴板
        self.zh_text_input.clipboard_clear()
        self.zh_text_input.clipboard_append(cleaned_text)
        
        # 阻止默认的复制行为
        return "break"
    

    



    def _add_to_user_dictionary(self):
        if not self.current_selection_info: return
        info = self.current_selection_info; item_data = self.translation_data[info['ns']]['items'][info['idx']]
        key, origin_name = item_data['key'], item_data['en']
        translation = self.zh_text_input.get("1.0", "end-1c").strip()
        if not translation:
            messagebox.showwarning("操作无效", "译文不能为空！", parent=self); return
        
        user_dict = config_manager.load_user_dict()
        # 同时保存Key和原文到个人词典
        user_dict["by_key"][key] = translation
        user_dict["by_origin_name"][origin_name] = translation
        config_manager.save_user_dict(user_dict)
        
        # 记录添加词典操作
        details = {
            'key': key,
            'origin_name': origin_name,
            'translation': translation
        }
        self.record_operation('DICTIONARY_ADD', details, target_iid=info['row_id'])
        
        self.status_label.config(text=f"成功！已将“{translation}”存入个人词典")
        self._set_dirty(True)
        # 更新按钮状态
        self._update_ui_state(interactive=True, item_selected=True)

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        initial_query = ""
        if self.current_selection_info:
            item_data = self.translation_data[self.current_selection_info['ns']]['items'][self.current_selection_info['idx']]
            initial_query = item_data['en']
        DictionarySearchWindow(self.main_window.root, initial_query=initial_query)
        
    def _run_ai_translation_async(self):
        # 重置取消标志
        self._ai_translation_cancelled = False
        self._save_current_edit()
        self._update_ui_state(interactive=False, item_selected=False)
        self.status_label.config(text="正在准备AI翻译...")
        self.log_callback("正在准备AI翻译...", "INFO")
        # 使用线程池执行AI翻译
        self._thread_pool.submit(self._ai_translation_worker)
    
    def cancel_ai_translation(self):
        """
        取消AI翻译操作
        """
        self._ai_translation_cancelled = True
        self.log_callback("AI翻译已取消", "INFO")
        self.status_label.config(text="AI翻译已取消")
        # 取消翻译器实例的任务
        if hasattr(self, '_current_translator') and self._current_translator:
            try:
                self._current_translator.cancel()
                self.log_callback("已通知翻译器取消所有任务", "INFO")
            except Exception as e:
                self.log_callback(f"取消翻译器任务时发生错误: {e}", "ERROR")
        # 关闭当前的AI翻译线程池
        try:
            if hasattr(self, '_current_ai_executor') and self._current_ai_executor:
                self.log_callback("正在终止AI翻译线程池...", "INFO")
                self._current_ai_executor.shutdown(wait=False, cancel_futures=True)
                self._current_ai_executor = None
                self.log_callback("AI翻译线程池已终止", "INFO")
        except Exception as e:
            self.log_callback(f"取消AI翻译线程池时发生错误: {e}", "ERROR")
        # 关闭并重建线程池，以取消所有正在执行的任务
        try:
            if hasattr(self, '_thread_pool') and self._thread_pool:
                self.log_callback("正在终止所有AI翻译线程...", "INFO")
                self._thread_pool.shutdown(wait=False, cancel_futures=True)
                # 重建线程池
                from concurrent.futures import ThreadPoolExecutor
                self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ModpackLocalizer")
                self.log_callback("线程池已重置，所有AI翻译任务已终止", "INFO")
        except Exception as e:
            self.log_callback(f"取消AI翻译时发生错误: {e}", "ERROR")

    def _ai_translation_worker(self):
        try:
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            items_to_translate_info = [{'ns': ns, 'idx': idx, 'en': item['en']} for ns, data in self.translation_data.items() for idx, item in enumerate(data.get('items', [])) if not item.get('zh', '').strip() and item.get('en', '').strip()]
            if not items_to_translate_info:
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: self.status_label.config(text="没有需要AI翻译的空缺条目。"))
                except RuntimeError:
                    pass
                self.log_callback("没有需要AI翻译的空缺条目。", "INFO"); return
            
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            texts_to_translate = [info['en'] for info in items_to_translate_info]
            s = self.current_settings
            translator = AITranslator(s.get('api_services', []))
            # 保存当前翻译器实例
            self._current_translator = translator
            
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            # 分批次处理文本
            batches = [texts_to_translate[i:i + s['ai_batch_size']] for i in range(0, len(texts_to_translate), s['ai_batch_size'])]
            total_batches, translations_nested = len(batches), [None] * len(batches)
            
            # 创建并保存AI翻译线程池
            from concurrent.futures import ThreadPoolExecutor
            self._current_ai_executor = ThreadPoolExecutor(max_workers=s['ai_max_threads'])
            try:
                future_map = {self._current_ai_executor.submit(translator.translate_batch, (i, batch, s['model'], s['prompt'])): i for i, batch in enumerate(batches)}
                for i, future in enumerate(as_completed(future_map), 1):
                    # 检查取消标志
                    if self._ai_translation_cancelled:
                        self.log_callback("AI翻译已取消，停止执行", "INFO")
                        # 取消所有未完成的任务
                        for f in future_map:
                            if not f.done():
                                f.cancel()
                        break
                    
                    batch_idx = future_map[future]
                    translations_nested[batch_idx] = future.result()
                    msg = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    try:
                        if self.winfo_exists():
                            self.after(0, lambda m=msg: self.status_label.config(text=m))
                    except RuntimeError:
                        pass
                    self.log_callback(msg, "INFO")
            finally:
                # 关闭线程池
                if self._current_ai_executor:
                    self._current_ai_executor.shutdown(wait=False)
                    self._current_ai_executor = None
            
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            # 合并翻译结果
            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            
            if len(translations) != len(texts_to_translate): raise ValueError(f"AI返回数量不匹配! 预期:{len(texts_to_translate)}, 实际:{len(translations)}")
            
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            try:
                if self.winfo_exists():
                    self.after(0, self._update_ui_after_ai, items_to_translate_info, translations)
            except RuntimeError:
                pass
            
        except Exception as e:
            # 检查是否是取消导致的异常
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消", "INFO")
            else:
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: messagebox.showerror("AI翻译失败", f"执行AI翻译时发生错误:\n{e}", parent=self))
                except RuntimeError:
                    pass
                self.log_callback(f"AI翻译失败: {e}", "ERROR")
        finally:
            try:
                if self.winfo_exists():
                    self.after(0, self._update_ui_state, True, bool(self.current_selection_info))
            except (tk.TclError, RuntimeError):
                # 捕获tk.TclError和主线程不在主循环中的错误
                pass

    def _is_valid_translation(self, text: str | None) -> bool:
        if not text or not text.strip():
            return False
        return True

    def _update_ui_after_ai(self, translated_info, translations):
        """更新UI以反映AI翻译结果
        
        Args:
            translated_info: 翻译信息列表，包含每个翻译条目的命名空间和索引
            translations: AI返回的翻译结果列表
        """
        # 保存当前选中状态
        saved_selection = self.current_selection_info.copy() if self.current_selection_info else None
        
        # 应用AI翻译结果
        valid_translation_count = 0
        for info, translation in zip(translated_info, translations):
            if self._is_valid_translation(translation):
                # 获取对应条目并更新
                item = self.translation_data[info['ns']]['items'][info['idx']]
                item['zh'] = translation
                item['source'] = 'AI翻译'
                valid_translation_count += 1
            else:
                logging.warning(f"AI为 '{info['en']}' 返回的译文 '{translation}' 无效，已忽略。")
        
        # 记录AI翻译操作
        target_iid = saved_selection['row_id'] if saved_selection else None
        details = {
            'batch_size': s.get('ai_batch_size', 10),
            'max_threads': s.get('ai_max_threads', 5),
            'model': s.get('model', 'default'),
            'total_items': len(items_to_translate_info),
            'valid_translations': valid_translation_count
        }
        self.record_operation('AI_TRANSLATION', details, target_iid=target_iid)
        
        # 更新UI状态
        self._set_dirty(True)
        
        # 显示翻译结果统计
        total_returned = len(translations)
        msg = f"AI翻译完成！共收到 {total_returned} 条结果，其中 {valid_translation_count} 条为有效译文。"
        self.status_label.config(text=msg)
        self.log_callback(msg, "SUCCESS")
        
        # 刷新树视图
        self._populate_namespace_tree()
        self._populate_item_list()
        
        # 恢复选中状态
        if saved_selection:
            ns = saved_selection['ns']
            idx = saved_selection['idx']
            iid = f"{ns}___{idx}"
            
            # 检查条目是否存在
            if self.trans_tree.exists(iid):
                # 重新选择条目
                self.trans_tree.selection_set(iid)
                self.trans_tree.focus(iid)
                self.trans_tree.see(iid)
                
                # 更新当前选择信息
                item = self.translation_data[ns]['items'][idx]
                self.current_selection_info = {
                    'ns': ns,
                    'idx': idx,
                    'row_id': iid
                }
                
                # 更新编辑器内容
                self._set_editor_content(item['en'], item.get('zh', ''))
                
                # 更新UI状态
                self._update_ui_state(interactive=True, item_selected=True)
            else:
                # 条目不存在，清除编辑器
                self._clear_editor()
                self.current_selection_info = None
                self._update_ui_state(interactive=True, item_selected=False)
        else:
            # 没有选中状态，清除编辑器
            self._clear_editor()
            self.current_selection_info = None
            self._update_ui_state(interactive=True, item_selected=False)

    def _on_finish(self):
        self._save_current_edit()
        final_lookup = defaultdict(dict)
        latest_data = self.translation_data
        for ns, data in latest_data.items():
            for item in data.get('items', []):
                if item.get('zh', '').strip():
                    final_lookup[ns][item['key']] = item['zh']
        
        final_translations = dict(final_lookup)
        if self.finish_callback:
            self.finish_callback(final_translations, latest_data)
    
    def _on_github_upload(self):
        """GitHub汉化仓库上传按钮点击事件"""
        # 保存当前编辑
        self._save_current_edit()
        
        # 加载GitHub配置
        from utils import config_manager
        config = config_manager.load_config()
        github_config = {
            'repo': config.get('github_repo', ''),
            'token': config.get('github_token', ''),
            'commit_message': config.get('github_commit_message', '更新汉化资源包'),
            'pull_before_push': config.get('github_pull_before_push', True)
        }
        
        # 验证配置
        required_configs = ['repo', 'token', 'commit_message']
        if not all(github_config.get(key, '') for key in required_configs):
            from gui import ui_utils
            ui_utils.show_error("配置不完整", "请先在设置中配置GitHub上传选项", parent=self)
            return
        
        # 获取当前选中的模组信息
        current_mod = None
        current_namespace = ""
        current_file_format = "json"  # 默认格式
        
        # 检查是否有选中的项目
        selection = self.ns_tree.selection()
        if selection:
            current_mod = selection[0]
            # 从翻译数据中获取模组信息
            mod_data = self.translation_data.get(current_mod, {})
            # 使用模组ID作为命名空间
            current_namespace = current_mod.split(':')[0] if ':' in current_mod else current_mod
            # 根据namespace_formats确定文件格式
            if hasattr(self, 'namespace_formats') and current_namespace in self.namespace_formats:
                current_file_format = self.namespace_formats[current_namespace]
            else:
                # 如果没有找到对应格式，默认使用json
                current_file_format = "json"
        
        # 进入GitHub上传模式
        self._toggle_github_upload_mode(True)
        
        # 创建GitHub上传UI组件
        if not hasattr(self, '_github_upload_ui'):
            from gui.github_upload_ui import GitHubUploadUI
            self._github_upload_ui = GitHubUploadUI(
                self.github_upload_ui_container, 
                self, 
                current_namespace, 
                current_file_format, 
                github_config
            )
            self._github_upload_ui.pack(fill="both", expand=True)
        else:
            # 更新GitHub上传UI中的命名空间和分支
            self._github_upload_ui.update_namespace_and_branch(current_namespace)
    
    def _show_operation_history(self):
        """显示操作历史窗口"""
        from tkinter import Toplevel
        
        history_window = Toplevel(self)
        history_window.title("操作历史")
        history_window.geometry("1000x600")
        history_window.transient(self)
        history_window.grab_set()
        
        # 创建主框架
        main_frame = ttk.Frame(history_window, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # 标题
        ttk.Label(main_frame, text="操作历史记录", bootstyle="primary").pack(anchor="w", pady=(0, 10))
        
        # 搜索框
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索:").pack(side="left", padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=40)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # 创建历史记录列表
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # 创建Treeview组件
        history_tree = ttk.Treeview(tree_frame, columns=("type", "module", "key", "original", "current"), show="headings")
        
        # 设置列标题和宽度
        history_tree.heading("type", text="操作类型")
        history_tree.heading("module", text="模组")
        history_tree.heading("key", text="原文键")
        history_tree.heading("original", text="原内容")
        history_tree.heading("current", text="现内容")
        
        history_tree.column("type", width=120, anchor="center")
        history_tree.column("module", width=150, anchor="w")
        history_tree.column("key", width=150, anchor="w")
        history_tree.column("original", width=250, anchor="w")
        history_tree.column("current", width=250, anchor="w")
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        history_tree.pack(fill="both", expand=True, side="left")
        
        # 定义标签样式，用于区分已撤回和未撤回的操作
        style = ttk.Style()
        # 为Treeview项定义样式
        style.configure("Normal.Treeview.Item", foreground="#000000")  # 正常操作：黑色文本
        style.configure("Revoked.Treeview.Item", foreground="#808080")  # 已撤回操作：灰色文本
        
        # 确保 current_state_index 不超过操作历史的长度
        if self.current_state_index >= len(self.operation_history):
            self.current_state_index = len(self.operation_history) - 1
        
        def search_history():
            query = search_var.get().lower()
            
            # 清空现有内容
            for item in history_tree.get_children():
                history_tree.delete(item)
            
            # 按时间正序显示（条目列表形式），跳过初始化操作
            for i, op in enumerate(self.operation_history):
                # 跳过初始化操作
                if op['type'] == 'INIT':
                    continue
                
                description = op['description']
                details = op['details']
                target_iid = op.get('target_iid')
                
                # 提取模组信息
                module = ""
                if target_iid:
                    try:
                        module = target_iid.split('___')[0]
                    except:
                        module = ""
                
                # 提取键、原内容、现内容
                key = ""
                original = ""
                current = ""
                
                if details:
                    if op['type'] == 'EDIT':
                        key = details.get('key', '')
                        original = details.get('original_text', '')[:50]  # 限制长度
                        current = details.get('new_text', '')[:50]
                    elif op['type'] == 'REPLACE':
                        key = details.get('key', '')
                        original = details.get('original_text', '')[:50]
                        current = details.get('new_text', '')[:50]
                    elif op['type'] == 'REPLACE_ALL':
                        key = "全部替换"
                        original = details.get('find_text', '')[:50]
                        current = details.get('replace_text', '')[:50]
                    elif op['type'] == 'AI_TRANSLATION':
                        key = "AI翻译"
                        original = f"共 {details.get('total_items', 0)} 条"
                        current = f"成功 {details.get('valid_translations', 0)} 条"
                    elif op['type'] == 'IMPORT':
                        key = "导入"
                        original = details.get('source', 'file')
                        current = f"{details.get('total_items', 0)} 条"
                    elif op['type'] == 'DICTIONARY_ADD':
                        key = "添加词典"
                        original = ""
                        current = details.get('translation', '')[:50]
                    elif op['type'] == 'BATCH_PROCESS':
                        process_type = details.get('process_type', 'unknown')
                        changes = details.get('changes', [])
                        change_count = len(changes)
                        
                        key = "批量处理"
                        original = process_type
                        if change_count > 0:
                            current = f"修改了 {change_count} 条条目"
                        else:
                            current = ""
                    elif op['type'] == 'REDO':
                        key = "重做"
                        original = details.get('redo_from', 'stack')
                        current = ""
                
                # 构建搜索文本
                search_text = f"{description} {module} {key} {original} {current}"
                
                # 搜索匹配
                if not query or query in search_text.lower():
                    # 确定是否为已撤回的操作
                    # 已撤回的操作是指索引大于当前状态索引的操作
                    item_id = str(i)
                    
                    # 添加到Treeview
                    history_tree.insert("", "end", iid=item_id, values=(
                        description,
                        module,
                        key,
                        original,
                        current
                    ))
                    
                    # 设置项的标签，用于区分已撤回和未撤回的操作
                    if i > self.current_state_index:
                        # 已撤回的操作，设置为灰色
                        history_tree.item(item_id, tags=("revoked",))
                    else:
                        # 未撤回的操作，保持默认颜色
                        history_tree.item(item_id, tags=("normal",))
        
        # 为Treeview定义标签
        history_tree.tag_configure("normal", foreground="black")
        history_tree.tag_configure("revoked", foreground="#808080")
        
        def jump_to_history(event):
            """跳转到历史记录中的指定状态"""
            selected_item = history_tree.selection()
            if selected_item:
                index = int(selected_item[0])
                if 0 <= index < len(self.operation_history):
                    # 判断是执行撤回还是重做操作
                    # 如果选中的索引大于当前状态索引，则执行重做操作
                    is_redo_operation = index > self.current_state_index
                    
                    # 保存当前选中状态
                    saved_selection = self.trans_tree.selection()[0] if self.trans_tree.selection() else None
                    saved_ns = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
                    
                    # 确定要选中的条目
                    target_to_select = None
                    
                    if is_redo_operation:
                        # 执行重做操作，恢复到选中条目的状态
                        # 恢复到选中条目的状态
                        target_state = self.operation_history[index]['state']
                        # 检查目标状态是否只包含单个命名空间（编辑或替换操作的优化格式）
                        if len(target_state) == 1 and (self.operation_history[index]['type'] == 'EDIT' or self.operation_history[index]['type'] == 'REPLACE'):
                            # 对于编辑或替换操作的优化格式，只更新单个命名空间
                            ns = list(target_state.keys())[0]
                            self.translation_data[ns] = copy.deepcopy(target_state[ns])
                        else:
                            # 对于其他操作，恢复整个状态
                            self.translation_data = copy.deepcopy(target_state)
                        
                        # 更新当前状态索引，以便正确标记已撤回的操作
                        self.current_state_index = index
                        
                        # 不截断历史记录，保持其完整
                        # 这样用户可以通过再次在历史窗口中选择后续操作来实现重做
                        
                        # 确定重做后要选中的条目
                        # 如果是批量操作，保持当前选中状态；否则选中重做操作的对应条目
                        if not self._is_batch_operation(self.operation_history[index]):
                            target_to_select = self.operation_history[index].get('target_iid')
                        else:
                            target_to_select = saved_selection
                        
                        # 更新UI
                        self._set_dirty(True)
                        self._full_ui_refresh(target_to_select=target_to_select)
                        self._update_history_buttons()
                        
                        # 更新历史记录显示的颜色标记
                        for item in history_tree.get_children():
                            item_index = int(item)
                            if item_index > self.current_state_index:
                                history_tree.item(item, tags=('revoked',))
                            else:
                                history_tree.item(item, tags=('normal',))
                    else:
                        # 执行撤回操作，恢复到选中条目之前的状态
                        # 计算要恢复到的状态索引
                        target_index = max(0, index - 1)
                        
                        # 恢复到目标状态（选中条目之前的状态）
                        target_state = self.operation_history[target_index]['state']
                        # 检查目标状态是否只包含单个命名空间（编辑或替换操作的优化格式）
                        if len(target_state) == 1 and (self.operation_history[target_index]['type'] == 'EDIT' or self.operation_history[target_index]['type'] == 'REPLACE'):
                            # 对于编辑或替换操作的优化格式，只更新单个命名空间
                            ns = list(target_state.keys())[0]
                            self.translation_data[ns] = copy.deepcopy(target_state[ns])
                        else:
                            # 对于其他操作，恢复整个状态
                            self.translation_data = copy.deepcopy(target_state)
                        
                        # 更新当前状态索引，以便正确标记已撤回的操作
                        self.current_state_index = target_index
                        
                        # 不截断历史记录，保持其完整
                        # 这样用户可以通过再次在历史窗口中选择后续操作来实现重做
                        
                        # 确定撤回后要选中的条目
                        # 如果是批量操作，保持当前选中状态；否则选中被撤回操作的对应条目
                        if not self._is_batch_operation(self.operation_history[index]):
                            target_to_select = self.operation_history[index].get('target_iid')
                        else:
                            target_to_select = saved_selection
                        
                        # 更新UI
                        self._set_dirty(True)
                        self._full_ui_refresh(target_to_select=target_to_select)
                        self._update_history_buttons()
                        
                        # 更新历史记录显示的颜色标记
                        for item in history_tree.get_children():
                            item_index = int(item)
                            if item_index > self.current_state_index:
                                history_tree.item(item, tags=('revoked',))
                            else:
                                history_tree.item(item, tags=('normal',))
        
        # 绑定点击事件
        history_tree.bind("<<TreeviewSelect>>", jump_to_history)
        
        ttk.Button(search_frame, text="搜索", command=search_history).pack(side="left")
        
        # 初始填充历史记录
        search_history()
        
        # 移除关闭按钮，窗口可通过右上角关闭
        
