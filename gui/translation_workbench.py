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

from utils import config_manager
from services.ai_translator import AITranslator
from gui import ui_utils
from gui.custom_widgets import ToolTip
from gui.find_replace_dialog import FindReplaceDialog
from core.term_database import TermDatabase

class TranslationWorkbench(ttk.Frame):
    def __init__(self, parent_frame, initial_data: dict, namespace_formats: dict, raw_english_files: dict, current_settings: dict, log_callback=None, project_path: str | None = None, finish_button_text: str = "完成", finish_callback=None, cancel_callback=None, project_name: str = "Unnamed_Project", main_window_instance=None, undo_history: dict = None):
        super().__init__(parent_frame)
        self.translation_data = initial_data
        self.namespace_formats = namespace_formats
        self.raw_english_files = raw_english_files
        self.current_settings = current_settings
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
        
        # 术语匹配结果缓存
        self._term_match_cache = {}
        
        # 术语搜索线程控制
        self._current_term_thread = None
        self._term_search_cancelled = False
        self._current_search_id = 0

        self.final_translations = None
        self.current_selection_info = None
        self.sort_column = '#0'
        self.sort_reverse = False
        self.original_headings = {}
        
        self.current_project_path = project_path
        self.is_dirty = False
        
        self.undo_stack = []
        self.redo_stack = []
        self.undo_targets = []
        self.redo_targets = []
        
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
        
        self._record_action(target_iid=None) 
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
            "workbench_data": self.undo_stack[-1] if self.undo_stack else self.translation_data,
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
        self.trans_tree.heading("key", text="原文键"); self.trans_tree.column("key", width=200, stretch=False)
        self.trans_tree.heading("english", text="原文"); self.trans_tree.column("english", width=250, stretch=True)
        self.trans_tree.heading("chinese", text="译文"); self.trans_tree.column("chinese", width=250, stretch=True)
        self.trans_tree.heading("source", text="来源"); self.trans_tree.column("source", width=120, stretch=False)
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
        
        ttk.Label(en_container, text="原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=0, pady=0)
        
        style = ttk.Style.get_instance()
        theme_bg_color = style.lookup('TFrame', 'background')
        theme_fg_color = style.lookup('TLabel', 'foreground')
        self.en_text_display = scrolledtext.ScrolledText(
            en_container, height=5, wrap="word", relief="flat",
            background=theme_bg_color, foreground=theme_fg_color
        )
        self.en_text_display.bind("<KeyPress>", lambda e: "break")
        self.en_text_display.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        
        # 右侧：术语提示
        term_container = ttk.Frame(content_frame)
        term_container.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        term_container.rowconfigure(1, weight=1)
        
        ttk.Label(term_container, text="术语提示:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=0, pady=0)
        
        self.term_text = scrolledtext.ScrolledText(
            term_container, height=5, wrap="word", relief="flat",
            background=theme_bg_color, foreground=theme_fg_color, state="disabled"
        )
        self.term_text.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        
        # 译文输入区域
        zh_header_frame = ttk.Frame(editor_frame); zh_header_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=(5,0))
        ttk.Label(zh_header_frame, text="译文:", anchor="nw").pack(side="left")
        shortcut_info_label = ttk.Label(zh_header_frame, text="快捷键: Enter 跳转到下一条, Ctrl+Enter 跳转到下一条待翻译")
        shortcut_info_label.pack(side="right")
        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=5, wrap="word", state="disabled")
        # 确保译文栏水平填充整个可用空间
        self.zh_text_input.grid(row=2, column=1, sticky="nsew", padx=5, pady=5)
        self.zh_text_input.bind("<KeyRelease>", self._on_text_modified)
        self.zh_text_input.bind("<FocusOut>", lambda e: self._save_current_edit())
        self.zh_text_input.bind("<Return>", self._save_and_jump_sequential)
        self.zh_text_input.bind("<Control-Return>", self._save_and_jump_pending)
        # 添加复制事件处理，确保只复制实际文本
        self.zh_text_input.bind("<Control-c>", self._on_copy)
        self.zh_text_input.bind("<Control-C>", self._on_copy)
        # 添加术语提示实时更新
        self.zh_text_input.bind("<KeyRelease>", self._update_term_suggestions, add="+")
        editor_btn_frame = ttk.Frame(editor_frame); editor_btn_frame.grid(row=3, column=1, sticky="e", pady=(5,0))
        
        self.add_to_dict_btn = ttk.Button(editor_btn_frame, text="添加到词典", command=self._add_to_user_dictionary, state="disabled", bootstyle="info-outline")
        self.add_to_dict_btn.pack(side="left", padx=(0, 10))
        
        self.undo_btn = ttk.Button(editor_btn_frame, text="撤销", command=self.undo, bootstyle="info-outline")
        self.undo_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.undo_btn, "撤销上一步操作 (Ctrl+Z)")
        self.redo_btn = ttk.Button(editor_btn_frame, text="重做", command=self.redo, bootstyle="info-outline")
        self.redo_btn.pack(side="left", padx=(0, 10))
        ToolTip(self.redo_btn, "重做已撤销的操作 (Ctrl+Y)")

        right_pane.add(editor_frame, weight=1)
        
        # 创建翻译控制台UI容器，初始隐藏
        self.comprehensive_ui_container = ttk.Frame(self.right_frame_container)
        self.comprehensive_ui_container.pack(fill="both", expand=True)
        self.comprehensive_ui_container.pack_forget()

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        self.status_label = ttk.Label(btn_frame, text="请选择一个项目以开始")
        self.status_label.pack(side="left", fill="x", expand=True)

        # 功能切换按钮 - 放到最右边
        self.mode_switch_btn = ttk.Button(btn_frame, text="切换到翻译控制台", command=self._toggle_mode, state="disabled", bootstyle="primary")
        self.mode_switch_btn.pack(side="right")
        ToolTip(self.mode_switch_btn, "在翻译工作台和翻译控制台功能之间切换")
        
        self.save_button = ttk.Button(btn_frame, text="保存项目", command=self._save_project, bootstyle="primary-outline")
        self.save_button.pack(side="right", padx=5)
        self.finish_button = ttk.Button(btn_frame, text=self.finish_button_text, command=self._on_finish, bootstyle="success")
        self.finish_button.pack(side="right")

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
            all_iids = []
            for ns_iid in self.ns_tree.get_children():
                for idx, item in enumerate(self.translation_data.get(ns_iid, {}).get('items', [])):
                    if item.get('en', '').strip():
                        all_iids.append(f"{ns_iid}___{idx}")
            return all_iids

    def _safe_select_item(self, iid):
        if self.trans_tree.exists(iid):
            self.trans_tree.selection_set(iid)
    
    def _safe_select_item_and_update_ui(self, iid):
        """安全地选择项目并更新UI"""
        if self.trans_tree.exists(iid):
            self.trans_tree.selection_set(iid)
            self.trans_tree.focus(iid)
            self.trans_tree.see(iid)
            # 触发项目选中事件以更新编辑器
            self._on_item_selected(None)
            # 更新UI状态，确保按钮可用
            ns, idx = self._get_ns_idx_from_iid(iid)
            if ns is not None:
                item_data = self.translation_data[ns]['items'][idx]
                self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': iid}
                self._set_editor_content(item_data['en'], item_data.get('zh', ''))
                self._update_ui_state(interactive=True, item_selected=True)
                self.zh_text_input.focus_set()

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
        if current_selection and current_selection[0] in all_items:
            start_index = all_items.index(current_selection[0])
        
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
            # 保存原始状态用于撤销
            self._record_action(target_iid=iid)
            
            # 更新项目数据
            original_item = copy.deepcopy(item)
            
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

        # 替换后查找下一个
        self.after(10, lambda p=params: self.find_next(p))
        
    def _update_item_in_tree(self, iid, item):
        """更新树视图中的项目"""
        if self.trans_tree.exists(iid):
            self.trans_tree.item(iid, values=(item['key'], item['en'], item.get('zh', ''), item['source']))

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
        
        # 保存当前状态用于撤销（使用copy.deepcopy确保状态被正确保存）
        target_iid = saved_selection['row_id'] if saved_selection else None
        self.undo_stack.append(copy.deepcopy(self.translation_data))
        self.undo_targets.append(target_iid)
        self.redo_stack.clear()
        self.redo_targets.clear()
        self._update_history_buttons()
        
        replacement_count = 0
        
        # 执行替换
        for ns in namespaces_to_search:
            for idx, item in enumerate(self.translation_data[ns]['items']):
                key = item.get('key', '')
                en_text = item.get('en', '')
                zh_text = item.get('zh', '')

                # 检查是否匹配
                found = False
                fields_to_replace = []

                # 编译正则表达式（带转义）
                escaped_find = re.escape(find_text)
                flags = 0 if match_case else re.IGNORECASE
                compiled_re = re.compile(escaped_find, flags)

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

    def _record_action(self, target_iid: str | None):
        if self.undo_stack and self.translation_data == self.undo_stack[-1]:
            return
        
        self.undo_stack.append(copy.deepcopy(self.translation_data))
        self.undo_targets.append(target_iid)
        self.redo_stack.clear()
        self.redo_targets.clear()
        self._update_history_buttons()

    def undo(self, event=None):
        if len(self.undo_stack) > 1:
            # 深拷贝当前状态，添加到重做栈
            self.redo_stack.append(copy.deepcopy(self.translation_data))
            target_to_reselect = self.undo_targets.pop()
            self.redo_targets.append(target_to_reselect)
            
            # 从撤销栈弹出最后一个状态
            self.undo_stack.pop()
            
            # 深拷贝恢复的状态，避免引用问题
            self.translation_data = copy.deepcopy(self.undo_stack[-1])
            
            self._set_dirty(True)
            self._full_ui_refresh(target_to_reselect)
            self._update_history_buttons()

    def redo(self, event=None):
        if self.redo_stack:
            # 深拷贝当前状态，添加到撤销栈
            self.undo_stack.append(copy.deepcopy(self.redo_stack[-1]))
            target_to_reselect = self.redo_targets.pop()
            self.undo_targets.append(target_to_reselect)
            
            # 从重做栈弹出最后一个状态
            self.redo_stack.pop()
            
            # 深拷贝恢复的状态，避免引用问题
            self.translation_data = copy.deepcopy(self.undo_stack[-1])
            
            self._set_dirty(True)
            self._full_ui_refresh(target_to_reselect)
            self._update_history_buttons()

    def _update_history_buttons(self):
        self.undo_btn.config(state="normal" if len(self.undo_stack) > 1 else "disabled")
        self.redo_btn.config(state="normal" if self.redo_stack else "disabled")

    def _select_item_by_id(self, iid: str):
        if not iid or not self.winfo_exists():
            return
        
        try:
            ns, idx_str = iid.rsplit('___', 1)
            idx = int(idx_str)
            
            # 先获取命名空间，然后刷新项目列表
            if self.ns_tree.exists(ns):
                self.ns_tree.selection_set(ns)
                self.ns_tree.focus(ns)
                self.ns_tree.see(ns)
                
                # 刷新项目列表
                self._populate_item_list()
                
                # 重新构建iid，因为项目列表已经刷新了
                new_iid = f"{ns}___{idx}"
                
                # 选择新构建的iid
                if self.trans_tree.exists(new_iid):
                    self.trans_tree.selection_set(new_iid)
                    self.trans_tree.focus(new_iid)
                    self.trans_tree.see(new_iid)
        except Exception as e:
            logging.warning(f"在撤销/重做后尝试自动选择条目 '{iid}' 时出错: {e}")
    

    
    def _full_ui_refresh(self, target_to_select: str | None = None):
        saved_ns = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
        
        self._populate_namespace_tree()
        
        if saved_ns and self.ns_tree.exists(saved_ns):
            self.ns_tree.selection_set(saved_ns)
        
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
        source_colors = { "个人词典[Key]": "#4a037b", "个人词典[原文]": "#4a037b", "模组自带": "#006400", "第三方汉化包": "#008080", "社区词典[Key]": "#00008b", "社区词典[原文]": "#00008b", "待翻译": "#b22222", "AI翻译": "#008b8b", "手动校对": "#0000cd", "空": "#808080" }
        for source, color in source_colors.items(): self.trans_tree.tag_configure(source, foreground=color)
        self.trans_tree.tag_configure("手动校对", font=('Microsoft YaHei UI', 9, 'bold'))

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
        self.trans_tree.delete(*self.trans_tree.get_children())
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]): return
        ns = selection[0]
        for idx, item_data in enumerate(self.translation_data.get(ns, {}).get('items', [])):
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
            
            self.trans_tree.insert("", "end", iid=f"{ns}___{idx}",
                                   values=(item_data['key'], item_data['en'], item_data.get('zh', ''), source),
                                   tags=(source,))

    def _on_namespace_selected(self, event=None):
        self._save_current_edit()
        
        # 处理正常模式下的模组选择
        if hasattr(self, '_current_mode') and self._current_mode == 'comprehensive':
            return
        
        # 处理正常模式下的模组选择
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]): return
        
        self.current_selection_info = None
        self._populate_item_list()
        self._clear_editor()
        self._update_ui_state(interactive=True, item_selected=False)
        self.status_label.config(text=f"已选择项目: {selection[0]}")

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
        if current_selection and current_zh_text != self.translation_data[current_selection['ns']]['items'][current_selection['idx']].get('zh', '').strip():
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
                self._record_action(target_iid=info['row_id'])
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
            # 1秒后执行保存，期间有新的修改会取消之前的定时器
            self._session_save_timer = self.after(1000, self._save_session_with_delay)
        
        # 实现自动保存项目数据
        if self.is_dirty and self.current_project_path:
            self._perform_save(self.current_project_path)
    
    def _save_session_with_delay(self):
        """延迟保存会话"""
        if self.main_window and self.is_dirty:
            self.main_window._save_current_session()

    def _perform_save(self, save_path) -> bool:
        self._save_current_edit()
        latest_data = self.undo_stack[-1] if self.undo_stack else self.translation_data
        
        save_data = {
            "version": "2.3", 
            "timestamp": datetime.now().isoformat(),
            "workbench_data": latest_data, 
            "namespace_formats": self.namespace_formats,
            "raw_english_files": self.raw_english_files
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
        
        # 更新功能切换按钮状态
        self.mode_switch_btn.config(state=base_state)
        
        if item_selected and interactive:
            self.add_to_dict_btn.config(state="normal")
            self.zh_text_input.config(state="normal", cursor="xterm")
        else:
            self.add_to_dict_btn.config(state="disabled")
            self.zh_text_input.config(state="disabled", cursor="")
            
    def _toggle_mode(self):
        """在翻译工作台和翻译控制台功能之间切换"""
        # 保存当前编辑
        self._save_current_edit()
        
        if self._current_mode == "workbench":
            # 保存翻译工作台模式的选中状态
            if not hasattr(self, '_workbench_selection'):
                self._workbench_selection = []
            self._workbench_selection = list(self.ns_tree.selection())
            
            # 切换到翻译控制台模式
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
            self.mode_switch_btn.config(text="切换到翻译控制台")
            
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
                    'zh': item.get('zh', ''),
                    'source': item.get('source', ''),
                    'namespace': ns
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
        self._record_action(target_iid=None)
        
        updated_count = 0
        skipped_count = 0
        not_found_count = 0
        
        for import_item in import_data:
            key = import_item.get('key')
            namespace = import_item.get('namespace')
            zh = import_item.get('zh', '').strip()
            
            if not key or not namespace:
                skipped_count += 1
                continue
            
            # 查找匹配的条目
            found = False
            if namespace in self.translation_data:
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
                
                # 提取文本中的所有单词，用于快速过滤
                text_words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', en_text.lower()))
                
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
                
                # 检查是否为最新请求，只有最新请求才更新UI
                if current_search_id == self._current_search_id:
                    try:
                        # 检查主窗口是否仍然存在
                        if self.winfo_exists():
                            self.after(0, lambda: self._update_term_display(display_terms))
                    except RuntimeError:
                        # 捕获主线程不在主循环中的错误
                        pass
            
            # 启动后台线程执行术语匹配
            threading.Thread(target=background_term_match, daemon=True).start()
        
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
    
    def reload_term_database(self):
        """
        重新加载术语库并清除缓存
        """
        self.term_db.reload()
        self._clear_term_cache()
    
    def _set_editor_content(self, en_text: str, zh_text: str):
        # 设置原文显示
        self.en_text_display.delete("1.0", "end")
        self.en_text_display.insert("1.0", en_text)
        
        # 设置译文输入，确保文本末尾没有额外的换行符
        self.zh_text_input.config(state="normal")
        self.zh_text_input.delete("1.0", "end")
        self.zh_text_input.insert("1.0", zh_text)
        
        # 确保译文栏只显示实际文本，不允许在文字右边选中
        self.zh_text_input.config(height=3, wrap="word")
        
        # 重置滚动条位置，确保文本从顶部开始显示
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
        self.status_label.config(text=f"成功！已将“{translation}”存入个人词典")
        self._set_dirty(True)

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        initial_query = ""
        if self.current_selection_info:
            item_data = self.translation_data[self.current_selection_info['ns']]['items'][self.current_selection_info['idx']]
            initial_query = item_data['en']
        DictionarySearchWindow(self.main_window.root, initial_query=initial_query)
        
    def _run_ai_translation_async(self):
        self._save_current_edit()
        self._update_ui_state(interactive=False, item_selected=False)
        self.status_label.config(text="正在准备AI翻译...")
        self.log_callback("正在准备AI翻译...", "INFO")
        threading.Thread(target=self._ai_translation_worker, daemon=True).start()

    def _ai_translation_worker(self):
        try:
            items_to_translate_info = [{'ns': ns, 'idx': idx, 'en': item['en']} for ns, data in self.translation_data.items() for idx, item in enumerate(data.get('items', [])) if not item.get('zh', '').strip() and item.get('en', '').strip()]
            if not items_to_translate_info:
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: self.status_label.config(text="没有需要AI翻译的空缺条目。"))
                except RuntimeError:
                    pass
                self.log_callback("没有需要AI翻译的空缺条目。", "INFO"); return
            
            texts_to_translate = [info['en'] for info in items_to_translate_info]
            s = self.current_settings
            translator = AITranslator(s['api_keys'], s.get('api_endpoint'))
            batches = [texts_to_translate[i:i + s['ai_batch_size']] for i in range(0, len(texts_to_translate), s['ai_batch_size'])]
            total_batches, translations_nested = len(batches), [None] * len(batches)
            
            with ThreadPoolExecutor(max_workers=s['ai_max_threads']) as executor:
                future_map = {executor.submit(translator.translate_batch, (i, batch, s['model'], s['prompt'], s.get('ai_stream_timeout', 30))): i for i, batch in enumerate(batches)}
                for i, future in enumerate(as_completed(future_map), 1):
                    batch_idx = future_map[future]
                    translations_nested[batch_idx] = future.result()
                    msg = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    try:
                        if self.winfo_exists():
                            self.after(0, lambda m=msg: self.status_label.config(text=m))
                    except RuntimeError:
                        pass
                    self.log_callback(msg, "INFO")
            
            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            if len(translations) != len(texts_to_translate): raise ValueError(f"AI返回数量不匹配! 预期:{len(texts_to_translate)}, 实际:{len(translations)}")
            try:
                if self.winfo_exists():
                    self.after(0, self._update_ui_after_ai, items_to_translate_info, translations)
            except RuntimeError:
                pass
            
        except Exception as e:
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
        
        # 直接将当前状态（AI翻译后的状态）添加到撤销栈
        # 这样撤销时可以恢复到上一个状态，当前状态是AI翻译后的状态
        self.undo_stack.append(copy.deepcopy(self.translation_data))
        target_iid = saved_selection['row_id'] if saved_selection else None
        self.undo_targets.append(target_iid)
        
        # 清空重做栈，因为执行了新的操作
        self.redo_stack.clear()
        self.redo_targets.clear()
        
        # 更新按钮状态
        self._update_history_buttons()
        
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