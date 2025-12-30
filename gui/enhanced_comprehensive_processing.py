import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog, filedialog
import threading
import logging
import copy
import itertools
from collections import defaultdict
import math

from utils import config_manager
from services.ai_translator import AITranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
from gui.custom_widgets import ToolTip



class EnhancedComprehensiveProcessing(tk.Frame):
    def __init__(self, parent, workbench_instance):
        super().__init__(parent)
        self.workbench = workbench_instance
        
        # 初始化变量
        self.processing = False
        self.settings = config_manager.load_config()
        
        # 配置变量
        self.mixed_translation_var = tk.BooleanVar(value=self.settings.get('mixed_translation', False))
        
        # 添加变量追踪，实现自动保存
        self.mixed_translation_var.trace_add("write", lambda *args: self._save_config())
        
        # 创建主容器
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        
        # 右侧：配置和操作面板（不再需要主面板和模组管理面板）
        self.operation_panel = ttk.LabelFrame(main_frame, text="操作配置", padding="10")
        self.operation_panel.pack(fill="both", expand=True)
        

        
        # 初始化操作配置面板
        self._init_operation_panel()
        
        # 绑定事件
        self.operation_var.trace_add("write", self._on_operation_change)
        
        # 绑定事件 - 这些绑定会在切换到翻译控制台模式时生效
        # 选择事件用于更新开始按钮状态和批次预览
        # 点击事件用于处理翻译控制台模式下的模组选择
        # 长按拖拽事件用于处理模组的拖拽选择
        
        # 初始化长按拖拽相关变量
        self._long_press_started = False
        self._long_press_item = None
        self._last_dragged_item = None
        self._processed_items = set()  # 跟踪本次拖拽中已处理的模组
        
        # 初始化时显示默认选项面板
        self._on_operation_change()
        
        # 初始化时检查选中的模组，更新开始按钮状态和批次预览
        self._check_module_selection()
        self._update_batch_preview()
        
    def _init_operation_panel(self):
        """初始化操作配置面板"""
        import ttkbootstrap as ttk
        # 使用更现代的卡片式设计
        
        # 操作类型选择卡片
        operation_card = ttk.LabelFrame(self.operation_panel, text="操作类型", padding="15", bootstyle="primary")
        operation_card.pack(fill="x", pady=(0, 20))
        
        # 操作类型映射
        self.operations_values = {
            "AI翻译": "ai_translate",
            "导出文本": "export",
            "导入翻译": "import"
        }
        self.operations_reverse_values = {
            "ai_translate": "AI翻译",
            "export": "导出文本",
            "import": "导入翻译"
        }
        
        self.operation_var = tk.StringVar(value=self.operations_reverse_values.get("ai_translate"))
        
        operations = [
            "AI翻译",
            "导出文本",
            "导入翻译"
        ]
        
        # 使用更现代的Combobox样式
        operation_combo_frame = ttk.Frame(operation_card)
        operation_combo_frame.pack(fill="x")
        
        ttk.Label(operation_combo_frame, text="选择操作类型: ", font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(0, 5))
        self.operation_combo = ttk.Combobox(operation_combo_frame, textvariable=self.operation_var, values=operations, state="readonly", bootstyle="primary")
        
        # 设置当前选中项的索引，确保组件正确显示选中状态
        if self.operation_var.get() in operations:
            self.operation_combo.current(operations.index(self.operation_var.get()))
        self.operation_combo.pack(fill="x", pady=(0, 10))
        
        # 添加事件绑定
        self.operation_combo.bind('<<ComboboxSelected>>', lambda e: [self._on_operation_change(e), self._on_combobox_selected(e, self.operation_combo), self._update_operation_comment()])
        self.operation_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, self.operation_combo))
        self.operation_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, self.operation_combo))
        
        # 操作类型注释文本，使用更醒目的样式
        self.operation_comment_var = tk.StringVar()
        self._update_operation_comment()
        self.operation_comment = ttk.Label(operation_card, textvariable=self.operation_comment_var, 
                                          font=("Microsoft YaHei UI", 9), foreground="#555555", 
                                          wraplength=600, justify="left")
        self.operation_comment.pack(anchor="w", pady=(5, 0))
        
        # AI翻译选项卡片
        self.ai_options_frame = ttk.LabelFrame(self.operation_panel, text="AI翻译选项", padding="8", bootstyle="success")
        self.ai_options_frame.pack(fill="x", pady=(0, 10))
        
        # AI翻译工作模式选择
        mode_card = ttk.LabelFrame(self.ai_options_frame, text="翻译模式", padding="8")
        mode_card.pack(fill="x", pady=(0, 10))
        
        # 翻译模式映射
        self.modes_values = {
            "基础翻译模式": "basic",
            "翻译润色模式": "polish",
            "混合翻译模式": "hybrid"
        }
        self.modes_reverse_values = {
            "basic": "基础翻译模式",
            "polish": "翻译润色模式",
            "hybrid": "混合翻译模式"
        }
        
        # 获取当前设置的内部值，转换为显示值
        current_mode = self.settings.get('translation_mode', 'hybrid')
        self.translation_mode_var = tk.StringVar(value=self.modes_reverse_values.get(current_mode))
        
        modes = [
            "基础翻译模式",
            "翻译润色模式",
            "混合翻译模式"
        ]
        
        # 翻译模式选择区域（删除了"选择翻译模式："文本）
        self.mode_combo = ttk.Combobox(mode_card, textvariable=self.translation_mode_var, values=modes, state="readonly", bootstyle="success")
        
        # 设置当前选中项的索引，确保组件正确显示选中状态
        if self.translation_mode_var.get() in modes:
            self.mode_combo.current(modes.index(self.translation_mode_var.get()))
        self.mode_combo.pack(fill="x", pady=(5, 5))
        
        # 添加事件绑定
        self.mode_combo.bind('<<ComboboxSelected>>', lambda e: self._on_combobox_selected(e, self.mode_combo))
        self.mode_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, self.mode_combo))
        self.mode_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, self.mode_combo))
        
        # 添加模式切换注释，使用更现代的样式
        self.mode_comment_var = tk.StringVar()
        self._update_mode_comment()
        self.mode_comment = ttk.Label(mode_card, textvariable=self.mode_comment_var, 
                                     font=("Microsoft YaHei UI", 9), foreground="#555555",
                                     wraplength=800, justify="left")
        self.mode_comment.pack(anchor="w", pady=(3, 0))
        
        # 绑定模式切换事件
        self.translation_mode_var.trace_add("write", lambda *args: [self._save_config(), self._update_mode_comment(), self._update_batch_preview()])
        
        # 智能翻译算法卡片
        algorithm_card = ttk.LabelFrame(self.ai_options_frame, text="翻译控制台设置", padding="6")
        algorithm_card.pack(fill="x", pady=(0, 8))
        
        # 优化布局：使用网格布局，充分利用宽度
        algorithm_card.columnconfigure(0, weight=1)
        algorithm_card.columnconfigure(1, weight=1)
        algorithm_card.columnconfigure(2, weight=1)
        algorithm_card.columnconfigure(3, weight=1)
        
        # 批次处理模式选择
        batch_mode_frame = ttk.Frame(algorithm_card)
        batch_mode_frame.grid(row=0, column=0, columnspan=1, sticky="w", padx=5, pady=5)
        
        ttk.Label(batch_mode_frame, text="批次处理模式: ", font=("Microsoft YaHei UI", 10), width=12).pack(side="left", padx=5)
        
        # 从设置中加载batch_processing_mode值，如果不存在或格式不正确则使用默认值
        batch_processing_mode = self.settings.get('batch_processing_mode', 'words')
        # 验证格式是否正确
        if batch_processing_mode not in ['words', 'batch', 'items']:
            batch_processing_mode = 'words'
        self.batch_mode_var = tk.StringVar(value=batch_processing_mode)
        
        # 批次处理模式选项：单词、批次和条目
        mode_options = [
            "单词",
            "批次",
            "条目"
        ]
        # 映射显示值到内部值
        self.mode_values = {
            "单词": "words",
            "批次": "batch",
            "条目": "items"
        }
        self.mode_reverse_values = {v: k for k, v in self.mode_values.items()}
        
        # 创建显示值变量，用于绑定到Combobox
        self.batch_mode_display_var = tk.StringVar()
        # 设置初始显示值
        self.batch_mode_display_var.set(self.mode_reverse_values[batch_processing_mode])
        
        mode_combo = ttk.Combobox(batch_mode_frame, textvariable=self.batch_mode_display_var, 
                                 values=mode_options, state="readonly", bootstyle="success", width=8)
        # 设置默认选择
        mode_combo.current(mode_options.index(self.mode_reverse_values[batch_processing_mode]))
        mode_combo.pack(side="left", padx=(0, 10))
        
        # 每批次数量设置
        batch_value_frame = ttk.Frame(algorithm_card)
        batch_value_frame.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # 创建三个独立的变量，用于存储每种模式的数值
        self.words_batch_var = tk.IntVar(value=self.settings.get('ai_batch_words', 2000))
        self.items_batch_var = tk.IntVar(value=self.settings.get('ai_batch_items', 10))
        self.batch_count_var = tk.IntVar(value=self.settings.get('ai_batch_count', 10))
        
        # 动态标签：根据批次处理模式显示不同的标签文本
        if batch_processing_mode == "words":
            label_text = "每批次单词数: "
            current_var = self.words_batch_var
        elif batch_processing_mode == "items":
            label_text = "每批次条目数: "
            current_var = self.items_batch_var
        else:
            label_text = "批次数: "
            current_var = self.batch_count_var
        
        self.batch_value_label = ttk.Label(batch_value_frame, text=label_text, font=("Microsoft YaHei UI", 10), width=12)
        self.batch_value_label.pack(side="left", padx=5)
        
        # 根据模式设置不同的数值范围
        if batch_processing_mode == "batch":
            spinbox_from = 1
            spinbox_to = 100
        else:
            spinbox_from = 100
            spinbox_to = 50000
        
        # 创建spinbox
        value_spinbox = ttk.Spinbox(batch_value_frame, from_=spinbox_from, to=spinbox_to, 
                                  textvariable=current_var, width=8, bootstyle="success")
        value_spinbox.pack(side="left")
        
        # 保存当前的spinbox引用和当前模式
        self.current_spinbox = value_spinbox
        self.current_batch_var = current_var
        
        # 保存初始模式，用于模式切换时的比较
        self._current_batch_mode = batch_processing_mode
        
        # 添加事件处理，切换批次处理模式时更新标签文本、数值范围和绑定的变量
        def on_batch_mode_change(*args):
            # 获取当前选择的新模式
            new_batch_mode = self.batch_mode_var.get()
            
            # 保存当前spinbox的值到旧模式对应的变量
            try:
                current_value = value_spinbox.get()
                current_value = int(current_value)
                if self._current_batch_mode == "words":
                    self.words_batch_var.set(current_value)
                elif self._current_batch_mode == "items":
                    self.items_batch_var.set(current_value)
                else:
                    self.batch_count_var.set(current_value)
            except (ValueError, tk.TclError):
                # 如果当前值无效，不保存
                pass
            
            # 更新当前模式记录
            self._current_batch_mode = new_batch_mode
            
            # 根据新模式更新UI
            if new_batch_mode == "words":
                self.batch_value_label.config(text="每批次单词数: ")
                value_spinbox.config(from_=100, to=50000)
                new_var = self.words_batch_var
            elif new_batch_mode == "items":
                self.batch_value_label.config(text="每批次条目数: ")
                value_spinbox.config(from_=100, to=50000)
                new_var = self.items_batch_var
            else:
                self.batch_value_label.config(text="批次数: ")
                value_spinbox.config(from_=1, to=100)
                new_var = self.batch_count_var
            
            # 切换spinbox绑定的变量
            value_spinbox.configure(textvariable=new_var)
            self.current_batch_var = new_var
            
            # 保存配置并更新批次预览和UI
            self._save_config()
            self._update_batch_preview()
            self._update_batch_ui()
        
        # 添加下拉选择事件处理，解决文字选中问题
        def on_combo_selected(e):
            # 当选择变化时，直接从Combobox获取用户选择的显示值
            display_value = e.widget.get()
            # 转换为内部值
            internal_value = self.mode_values.get(display_value, 'words')
            # 只有当内部值真正变化时才触发更新
            if internal_value != self.batch_mode_var.get():
                self.batch_mode_var.set(internal_value)
                on_batch_mode_change()
            self._on_combobox_selected(e, mode_combo)
        
        mode_combo.bind('<<ComboboxSelected>>', on_combo_selected)
        mode_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, mode_combo))
        mode_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, mode_combo))
        
        # 绑定批次计算模式变化事件
        self.batch_mode_var.trace_add("write", on_batch_mode_change)
        
        # 绑定数值变化事件
        self.words_batch_var.trace_add("write", lambda *args: [self._save_config(), self._update_batch_preview()])
        self.items_batch_var.trace_add("write", lambda *args: [self._save_config(), self._update_batch_preview()])
        self.batch_count_var.trace_add("write", lambda *args: [self._save_config(), self._update_batch_preview()])
        
        # 批次预览：移到右侧
        self.preview_frame = ttk.Frame(algorithm_card)
        self.preview_frame.grid(row=0, column=3, sticky="e", padx=5, pady=5)
        
        ttk.Label(self.preview_frame, text="预计批次:", font=("Microsoft YaHei UI", 10), foreground="#666666").pack(side="left", padx=(0, 5))
        
        self.batch_preview_var = tk.StringVar(value="0")
        batch_preview_label = ttk.Label(self.preview_frame, textvariable=self.batch_preview_var, 
                                       font=("Microsoft YaHei UI", 12, "bold"), foreground="#28a745")
        batch_preview_label.pack(side="left")
        
        # 初始化UI状态
        self._update_batch_ui()
        
        # 按钮框架 - 设计更现代的按钮布局
        self.button_frame = ttk.Frame(self.operation_panel, padding="15")
        self.button_frame.pack(fill="x", pady=(10, 0))
        
        # 使用更现代的按钮样式和布局
        button_container = ttk.Frame(self.button_frame)
        button_container.pack(fill="x", anchor="e")
        
        self.cancel_button = ttk.Button(button_container, text="取消", command=self._on_cancel, bootstyle="outline-secondary", width=12)
        self.cancel_button.pack(side="right", padx=(10, 0))
        
        self.start_button = ttk.Button(button_container, text="开始处理", command=self._on_start, bootstyle="success-outline", width=15)
        self.start_button.pack(side="right")
        
        # 导入选项卡片（仅在导入操作时显示）
        self.import_options_frame = ttk.LabelFrame(self.operation_panel, text="导入选项", padding="15", bootstyle="info")
        self.import_options_frame.pack(fill="x", pady=(0, 20))
        self.import_options_frame.pack_forget()
        
        # 导入来源映射
        self.import_sources_values = {
            "从文件导入": "file",
            "从剪贴板导入": "clipboard"
        }
        self.import_sources_reverse_values = {
            "file": "从文件导入",
            "clipboard": "从剪贴板导入"
        }
        
        self.import_source_var = tk.StringVar(value=self.import_sources_reverse_values.get("file"))
        
        import_sources = [
            "从文件导入",
            "从剪贴板导入"
        ]
        
        # 导入来源选择区域
        import_source_frame = ttk.Frame(self.import_options_frame)
        import_source_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(import_source_frame, text="选择导入来源: ", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.import_source_combo = ttk.Combobox(import_source_frame, textvariable=self.import_source_var, values=import_sources, state="readonly", bootstyle="info")
        
        # 设置当前选中项的索引，确保组件正确显示选中状态
        if self.import_source_var.get() in import_sources:
            self.import_source_combo.current(import_sources.index(self.import_source_var.get()))
        self.import_source_combo.pack(fill="x")
        
        # 添加事件绑定
        self.import_source_combo.bind('<<ComboboxSelected>>', lambda e: self._on_combobox_selected(e, self.import_source_combo))
        self.import_source_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, self.import_source_combo))
        self.import_source_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, self.import_source_combo))
        
        # 导出选项卡片（仅在导出操作时显示）
        self.export_options_frame = ttk.LabelFrame(self.operation_panel, text="导出选项", padding="15", bootstyle="warning")
        self.export_options_frame.pack(fill="x", pady=(0, 20))
        self.export_options_frame.pack_forget()
        
        # 导出范围选项
        export_scope_card = ttk.LabelFrame(self.export_options_frame, text="导出范围", padding="12")
        export_scope_card.pack(fill="x", pady=(0, 15))
        
        # 导出范围映射
        self.export_scopes_values = {
            "全部文本": "all",
            "仅待翻译": "pending",
            "仅已翻译": "completed"
        }
        self.export_scopes_reverse_values = {
            "all": "全部文本",
            "pending": "仅待翻译",
            "completed": "仅已翻译"
        }
        
        self.export_scope_var = tk.StringVar(value=self.export_scopes_reverse_values.get("all"))
        
        export_scopes = [
            "全部文本",
            "仅待翻译",
            "仅已翻译"
        ]
        
        ttk.Label(export_scope_card, text="选择导出范围: ", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.export_scope_combo = ttk.Combobox(export_scope_card, textvariable=self.export_scope_var, values=export_scopes, state="readonly", bootstyle="warning")
        
        # 设置当前选中项的索引，确保组件正确显示选中状态
        if self.export_scope_var.get() in export_scopes:
            self.export_scope_combo.current(export_scopes.index(self.export_scope_var.get()))
        self.export_scope_combo.pack(fill="x")
        
        # 添加事件绑定
        self.export_scope_combo.bind('<<ComboboxSelected>>', lambda e: self._on_combobox_selected(e, self.export_scope_combo))
        self.export_scope_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, self.export_scope_combo))
        self.export_scope_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, self.export_scope_combo))
        
        # 导出方式选项
        export_method_card = ttk.LabelFrame(self.export_options_frame, text="导出方式", padding="12")
        export_method_card.pack(fill="x")
        
        self.export_method_var = tk.StringVar(value="导出到文件")
        export_methods = [
            "导出到文件",
            "导出到剪贴板"
        ]
        self.export_method_values = {
            "导出到文件": "file",
            "导出到剪贴板": "clipboard"
        }
        self.export_method_reverse_values = {
            "file": "导出到文件",
            "clipboard": "导出到剪贴板"
        }
        
        ttk.Label(export_method_card, text="选择导出方式: ", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.export_method_combo = ttk.Combobox(export_method_card, textvariable=self.export_method_var, values=export_methods, state="readonly", bootstyle="warning")
        
        # 设置当前选中项的索引，确保组件正确显示选中状态
        if self.export_method_var.get() in export_methods:
            self.export_method_combo.current(export_methods.index(self.export_method_var.get()))
        self.export_method_combo.pack(fill="x")
        
        # 添加事件绑定
        self.export_method_combo.bind('<<ComboboxSelected>>', lambda e: self._on_combobox_selected(e, self.export_method_combo))
        self.export_method_combo.bind('<FocusOut>', lambda e: self._on_combobox_focus_out(e, self.export_method_combo))
        self.export_method_combo.bind('<FocusIn>', lambda e: self._on_combobox_focus_in(e, self.export_method_combo))
        
        # 配置会自动保存，无需手动保存按钮
    
    def _count_words(self, text: str) -> int:
        """计算文本的单词数量
        
        Args:
            text: 要计算单词数量的文本
            
        Returns:
            int: 文本的单词数量
        """
        if not text:
            return 0
        # 使用split()简单计算单词数量，消耗更低
        return len(text.split())
    
    def _update_mode_comment(self):
        """更新模式切换注释"""
        mode = self.translation_mode_var.get()
        if mode == "基础翻译模式":
            self.mode_comment_var.set("仅对用户提供的待翻译文本进行直接翻译，不涉及任何已翻译内容的参考或润色处理")
        elif mode == "翻译润色模式":
            self.mode_comment_var.set("专门针对已完成翻译的文本进行质量优化，包括语言流畅度提升、专业术语统一等")
        elif mode == "混合翻译模式":
            self.mode_comment_var.set("在处理待翻译文本时，结合已翻译内容进行综合翻译，确保翻译风格一致性")
        else:
            self.mode_comment_var.set("")
    
    def _update_operation_comment(self):
        """更新操作类型注释"""
        operation = self.operation_var.get()
        if operation == "AI翻译":
            self.operation_comment_var.set("使用AI对选中模组中的待翻译文本进行批量翻译，支持多种翻译模式")
        elif operation == "导出文本":
            self.operation_comment_var.set("将选中模组中的文本导出到文件或剪贴板，可选择导出范围和方式")
        elif operation == "导入翻译":
            self.operation_comment_var.set("从文件或剪贴板导入翻译结果，更新选中模组中的翻译内容")
        else:
            self.operation_comment_var.set("")
    

    
    def _on_operation_change(self, *args):
        """操作类型变化事件处理"""
        # 将显示值转换为内部值
        operation_display = self.operation_var.get()
        operation = self.operations_values.get(operation_display, "ai_translate")
        
        # 隐藏所有选项
        self.ai_options_frame.pack_forget()
        self.import_options_frame.pack_forget()
        self.export_options_frame.pack_forget()
        self.button_frame.pack_forget()
        
        # 根据操作类型显示相应选项
        if operation == "ai_translate":
            self.ai_options_frame.pack(fill="x", pady=(0, 15))
            self.button_frame.pack(fill="x", anchor="e", pady=(0, 15))
        elif operation == "import":
            self.import_options_frame.pack(fill="x", pady=(0, 15))
            self.button_frame.pack(fill="x", anchor="e", pady=(0, 15))
        elif operation == "export":
            self.export_options_frame.pack(fill="x", pady=(0, 15))
            self.button_frame.pack(fill="x", anchor="e", pady=(0, 15))
        
        self.update_idletasks()
    
    def _on_threshold_change(self, *args):
        """阈值变化事件处理"""
        # 字符串值已经在下拉框中显示，无需更新标签
        # 但需要确保配置保存的是浮点数
        pass
    
    def _on_combobox_focus_out(self, event, combobox):
        """处理Combobox焦点移出事件，取消文字选中状态"""
        # 取消文字选中状态
        combobox.selection_clear()
        # 确保光标位置在文本末尾
        combobox.icursor(tk.END)
    
    def _on_combobox_selected(self, event, combobox):
        """处理Combobox选项选中事件，立即取消文字选中状态"""
        # 立即取消文字选中状态，不使用延迟
        combobox.selection_clear()
        combobox.icursor(tk.END)
    
    def _on_combobox_focus_in(self, event, combobox):
        """处理Combobox焦点进入事件，取消文字选中状态"""
        # 立即取消文字选中状态，不使用延迟
        combobox.selection_clear()
        combobox.icursor(tk.END)
    
    def _check_module_selection(self):
        """检查选中的模组，并更新开始按钮的状态"""
        selected_modules = self.workbench.ns_tree.selection()
        if selected_modules:
            self.start_button.config(state="normal")
        else:
            self.start_button.config(state="disabled")
        
        # 更新批次预览
        self._update_batch_preview()
        
    def _calculate_total_batches(self):
        """计算预计的批次数量"""
        # 获取选中的模组
        selected_modules = self.workbench.ns_tree.selection()
        if not selected_modules:
            return 0
        
        # 获取翻译模式
        translation_mode_display = self.translation_mode_var.get()
        translation_mode = self.modes_values.get(translation_mode_display, "hybrid")
        
        batch_mode = self.batch_mode_var.get()
        
        # 如果是批次数模式，直接返回用户指定的批次数
        if batch_mode == "batch":
            try:
                return self.batch_count_var.get()
            except (tk.TclError, ValueError):
                return self.settings.get('ai_batch_count', 10)
        
        # 计算待处理的条目数量、总长度和单词数量
        total_items = 0
        total_chars = 0
        total_words = 0
        
        for ns in selected_modules:
            items = self.workbench.translation_data.get(ns, {}).get("items", [])
            for idx, item in enumerate(items):
                en_text = item.get("en", "").strip()
                zh_text = item.get("zh", "").strip()
                
                if en_text:
                    if translation_mode == "basic" or translation_mode == "hybrid":
                        # 基础翻译模式和混合翻译模式：仅处理待翻译文本
                        if not zh_text:
                            total_items += 1
                            total_chars += len(en_text)
                            total_words += self._count_words(en_text)
                    elif translation_mode == "polish":
                        # 翻译润色模式：仅处理已翻译文本
                        if zh_text:
                            combined_text = f"{en_text} -> {zh_text}"
                            total_items += 1
                            total_chars += len(combined_text)
                            total_words += self._count_words(combined_text)
        
        # 计算批次数量
        if total_items == 0:
            return 0
        
        # 获取批处理值
        try:
            if batch_mode == "words":
                batch_value = self.words_batch_var.get()
            elif batch_mode == "items":
                batch_value = self.items_batch_var.get()
            else:
                batch_value = self.batch_count_var.get()
        except (tk.TclError, ValueError):
            # 使用保存的默认值
            if batch_mode == "words":
                batch_value = self.settings.get('ai_batch_words', 2000)
            elif batch_mode == "items":
                batch_value = self.settings.get('ai_batch_items', 200)
            else:
                batch_value = self.settings.get('ai_batch_count', 10)
        
        if batch_mode == "words":
            # 基于单词数量：每批次单词数
            return max(1, (total_words + batch_value - 1) // batch_value)
        elif batch_mode == "items":
            # 基于条目数量：每批次条目数
            return max(1, (total_items + batch_value - 1) // batch_value)
        else:
            # 基于批次数量：直接使用指定的批次数
            return max(1, batch_value)
        
    def _update_batch_preview(self):
        """更新批次预览显示"""
        total_batches = self._calculate_total_batches()
        self.batch_preview_var.set(f"{total_batches}")
    
    def _on_module_click(self, event):
        """处理模组点击事件，实现点击已选中模组取消选中的功能"""
        # 只有在翻译控制台模式下才执行自定义点击逻辑
        if self.workbench._current_mode != "comprehensive":
            return
            
        # 获取点击的模组
        region = self.workbench.ns_tree.identify_region(event.x, event.y)
        if region == "cell" or region == "text":
            # 获取当前点击的模组ID
            clicked_item = self.workbench.ns_tree.identify_row(event.y)
            if clicked_item:
                # 获取所有选中的模组
                all_selected = self.workbench.ns_tree.selection()
                
                # 临时解绑选择事件，避免递归调用
                self.workbench.ns_tree.unbind("<<TreeviewSelect>>")
                
                try:
                    if clicked_item in all_selected:
                        # 如果点击的是已选中的模组，取消其选中状态
                        self.workbench.ns_tree.selection_remove(clicked_item)
                    else:
                        # 如果点击的是未选中的模组，添加到选中列表
                        self.workbench.ns_tree.selection_add(clicked_item)
                finally:
                    # 重新绑定选择事件
                    self.workbench.ns_tree.bind("<<TreeviewSelect>>", self._on_module_selection_change)
                
                # 更新状态栏
                selection = self.workbench.ns_tree.selection()
                if selection:
                    self.workbench.status_label.config(text=f"已选择 {len(selection)} 个项目")
                else:
                    self.workbench.status_label.config(text="未选择任何项目")
                
                # 更新开始按钮状态和批次预览
                self._check_module_selection()
                self._update_batch_preview()
    
    def _on_module_press(self, event):
        """处理鼠标按下事件，立即开始长按操作"""
        # 只有在翻译控制台模式下才执行长按操作
        if self.workbench._current_mode != "comprehensive":
            return
            
        region = self.workbench.ns_tree.identify_region(event.x, event.y)
        if region == "cell" or region == "text":
            # 获取当前点击的模组ID
            clicked_item = self.workbench.ns_tree.identify_row(event.y)
            if clicked_item:
                # 清空已处理项目集合
                self._processed_items.clear()
                # 保存起始位置
                self._long_press_item = clicked_item
                # 将起始模组添加到已处理集合中
                self._processed_items.add(clicked_item)
                # 立即开始长按操作
                self._long_press_started = True
                self._last_dragged_item = self._long_press_item
    
    def _on_module_drag(self, event):
        """处理鼠标拖拽事件，切换经过的模组选中状态"""
        # 只有在翻译控制台模式下才执行拖拽操作
        if self.workbench._current_mode != "comprehensive":
            return
            
        if self._long_press_started:
            region = self.workbench.ns_tree.identify_region(event.x, event.y)
            if region == "cell" or region == "text":
                # 获取当前拖拽到的模组ID
                dragged_item = self.workbench.ns_tree.identify_row(event.y)
                if dragged_item and dragged_item != self._last_dragged_item:
                    # 获取所有模组的列表
                    all_items = self.workbench.ns_tree.get_children()
                    
                    # 找到起始和结束模组的索引
                    if self._last_dragged_item in all_items and dragged_item in all_items:
                        start_idx = all_items.index(self._last_dragged_item)
                        end_idx = all_items.index(dragged_item)
                        
                        # 确定处理范围（包括起始和结束模组）
                        if start_idx < end_idx:
                            # 向下拖拽
                            range_start = start_idx + 1
                            range_end = end_idx + 1
                        else:
                            # 向上拖拽
                            range_start = end_idx
                            range_end = start_idx
                        
                        # 处理范围内的所有模组
                        for idx in range(range_start, range_end):
                            item = all_items[idx]
                            
                            # 如果该模组已经在本次拖拽中处理过，跳过
                            if item in self._processed_items:
                                continue
                            
                            # 将模组添加到已处理集合
                            self._processed_items.add(item)
                            
                            # 获取所有选中的模组
                            all_selected = self.workbench.ns_tree.selection()
                            
                            # 临时解绑选择事件，避免递归调用
                            self.workbench.ns_tree.unbind("<<TreeviewSelect>>")
                            
                            try:
                                if item in all_selected:
                                    # 如果是已选中的模组，取消其选中状态
                                    self.workbench.ns_tree.selection_remove(item)
                                else:
                                    # 如果是未选中的模组，添加到选中列表
                                    self.workbench.ns_tree.selection_add(item)
                            finally:
                                # 重新绑定选择事件
                                self.workbench.ns_tree.bind("<<TreeviewSelect>>", self._on_module_selection_change)
                    
                    # 更新状态栏
                    selection = self.workbench.ns_tree.selection()
                    if selection:
                        self.workbench.status_label.config(text=f"已选择 {len(selection)} 个项目")
                    else:
                        self.workbench.status_label.config(text="未选择任何项目")
                    
                    # 更新开始按钮状态
                    self._check_module_selection()
                    
                    # 更新批次预览
                    self._update_batch_preview()
                    
                    # 保存当前拖拽位置
                    self._last_dragged_item = dragged_item
    
    def _on_module_release(self, event):
        """处理鼠标释放事件，结束长按操作"""
        # 重置长按状态
        self._long_press_started = False
        self._long_press_item = None
        self._last_dragged_item = None
    
    def _on_module_selection_change(self, event=None):
        """处理模组选择变化事件，更新开始按钮状态和批次预览"""
        self._check_module_selection()
        self._update_batch_preview()
    
    def _update_batch_ui(self):
        """根据批次设置状态更新UI"""
        # 从批次处理模式中提取信息
        batch_mode = self.batch_mode_var.get()
        
        # 移除智能批处理设置相关UI，简化界面
        if hasattr(self, 'smart_batching_frame'):
            self.smart_batching_frame.pack_forget()
        if hasattr(self, 'smart_batching_settings_frame'):
            self.smart_batching_settings_frame.pack_forget()
        if hasattr(self, 'traditional_batch_frame'):
            self.traditional_batch_frame.pack_forget()
        if hasattr(self, 'count_mode_frame'):
            self.count_mode_frame.pack_forget()
        if hasattr(self, 'value_mode_frame'):
            self.value_mode_frame.pack_forget()
        
        # 控制预计批次预览的显示/隐藏
        if hasattr(self, 'preview_frame'):
            if batch_mode == "batch":
                # 当选择批次模式时，隐藏预计批次预览
                self.preview_frame.grid_remove()
            else:
                # 其他模式下显示预计批次预览
                self.preview_frame.grid()
        
        # 更新批次预览
        self._update_batch_preview()
    
    def _save_config(self):
        """保存配置（自动调用，无需手动触发）"""
        # 更新配置，将显示值转换为内部值
        self.settings['translation_mode'] = self.modes_values.get(self.translation_mode_var.get(), 'hybrid')
        
        # 保存合并后的批次处理模式
        self.settings['batch_processing_mode'] = self.batch_mode_var.get()
        
        # 保存三种模式的独立数值设置
        try:
            # 保存每批次单词数
            self.settings['ai_batch_words'] = self.words_batch_var.get()
            # 保存每批次条目数
            self.settings['ai_batch_items'] = self.items_batch_var.get()
            # 保存批次数
            self.settings['ai_batch_count'] = self.batch_count_var.get()
        except (tk.TclError, ValueError):
            # 使用默认值
            self.settings['ai_batch_words'] = self.settings.get('ai_batch_words', 2000)
            self.settings['ai_batch_items'] = self.settings.get('ai_batch_items', 10)
            self.settings['ai_batch_count'] = self.settings.get('ai_batch_count', 10)
        
        # 保存到文件
        config_manager.save_config(self.settings)
        
        # 更新workbench的当前设置
        self.workbench.current_settings = self.settings
        
        logging.info("配置已自动保存")
    
    def _on_start(self):
        """开始处理"""
        if self.processing:
            return
        
        # 将显示值转换为内部值
        operation_display = self.operation_var.get()
        operation = self.operations_values.get(operation_display, "ai_translate")
        
        # 保存当前编辑
        self.workbench._save_current_edit()
        
        # 禁用界面
        self.processing = True
        self.start_button.config(state="disabled")
        self.cancel_button.config(text="取消")
        
        # 获取选中的模组
        selected_modules = self.workbench.ns_tree.selection()
        
        # 根据操作类型执行不同的处理
        if operation == "ai_translate":
            self._start_ai_translation(selected_modules)
        elif operation == "export":
            self._start_export(selected_modules)
        elif operation == "import":
            self._start_import(selected_modules)
    
    def _on_exit(self):
        """退出翻译控制台模式，返回翻译工作台"""
        # 检查是否有任务正在处理
        if self.processing:
            # 显示提示，要求先取消当前任务
            from tkinter import messagebox
            messagebox.showwarning("操作提示", "当前有任务正在处理，请先点击'取消'按钮终止任务后再退出翻译控制台。")
            return
        
        # 调用workbench的toggle_mode方法切换回翻译工作台模式
        self.workbench._toggle_mode()
    
    def _on_cancel(self):
        """取消处理"""
        if self.processing:
            # 这里可以添加取消逻辑
            self.processing = False
            self.workbench.status_label.config(text="处理已取消")
            self.workbench.log_callback("处理已取消", "INFO")
            self.start_button.config(state="normal")
            self.cancel_button.config(text="取消")
        else:
            # 因为现在是Frame组件，不需要destroy，只需要重置状态
            self.workbench.status_label.config(text="准备就绪")
            self.workbench.log_callback("准备就绪", "INFO")
    
    def _start_ai_translation(self, selected_modules):
        """开始AI翻译"""
        # 检查是否有选中的模组
        if not selected_modules:
            # 显示提示，要求先选中模组
            messagebox.showwarning("操作提示", "请先在左侧选择一个或多个模组进行处理。")
            # 恢复界面状态
            self.processing = False
            self.start_button.config(state="normal")
            self.cancel_button.config(text="取消")
            return
        
        self.workbench.status_label.config(text="正在准备AI翻译...")
        self.workbench.log_callback("正在准备AI翻译...", "INFO")
        
        # 在工作线程中执行AI翻译
        threading.Thread(target=self._ai_translation_worker, args=(selected_modules,), daemon=True).start()
    
    def _ai_translation_worker(self, selected_modules):
        """AI翻译工作线程"""
        try:
            # 获取翻译模式，将显示值转换为内部值
            translation_mode_display = self.translation_mode_var.get()
            translation_mode = self.modes_values.get(translation_mode_display, "hybrid")
            
            # 1. 根据翻译模式获取待处理的条目
            all_items = []
            all_texts = set()
            translated_texts = defaultdict(list)  # 已翻译文本映射：英文原文 -> 中文译文
            
            # 先收集所有已翻译文本，用于混合翻译模式
            for ns in selected_modules:
                items = self.workbench.translation_data.get(ns, {}).get("items", [])
                for idx, item in enumerate(items):
                    en_text = item.get("en", "").strip()
                    zh_text = item.get("zh", "").strip()
                    if en_text:
                        all_texts.add(en_text)
                        if zh_text:
                            translated_texts[en_text].append(zh_text)
            
            # 根据模式筛选待处理条目
            for ns in selected_modules:
                items = self.workbench.translation_data.get(ns, {}).get("items", [])
                for idx, item in enumerate(items):
                    en_text = item.get("en", "").strip()
                    zh_text = item.get("zh", "").strip()
                    
                    if en_text:
                        if translation_mode == "basic" or translation_mode == "hybrid":
                            # 基础翻译模式和混合翻译模式：仅处理待翻译文本
                            if not zh_text:
                                all_items.append((ns, idx, item))
                        elif translation_mode == "polish":
                            # 翻译润色模式：仅处理已翻译文本
                            if zh_text:
                                all_items.append((ns, idx, item))
            
            if not all_items:
                self.after(0, lambda: messagebox.showinfo("提示", "没有符合条件的条目需要处理。"))
                self.after(0, lambda: self.workbench.status_label.config(text="准备就绪"))
                self.after(0, lambda: setattr(self, "processing", False))
                self.after(0, lambda: self.start_button.config(state="normal"))
                return
            
            if not self.processing:
                return
            
            # 3. 准备翻译数据
            all_texts_to_translate = []
            all_item_mapping = []
            all_group_contexts = []
            
            # 为所有待处理条目生成上下文
            group_context = self._generate_translation_context(all_items, translated_texts) if translation_mode == "hybrid" else ""
            
            for ns, idx, item in all_items:
                en_text = item.get("en", "").strip()
                zh_text = item.get("zh", "").strip()
                
                if translation_mode == "polish" and zh_text:
                    # 润色模式：传递英文原文和中文译文，格式为 "原文 -> 译文"
                    combined_text = f"{en_text} -> {zh_text}"
                    all_texts_to_translate.append(combined_text)
                else:
                    # 其他模式：仅传递英文原文
                    all_texts_to_translate.append(en_text)
                
                all_item_mapping.append((ns, idx, item))
                all_group_contexts.append(group_context)
            
            # 4. 执行AI翻译
            self.after(0, lambda: self.workbench.status_label.config(text="正在进行AI翻译..."))
            
            # 获取设置
            s = self.settings
            
            # 初始化翻译器
            translator = AITranslator(s['api_keys'], s.get('api_endpoint'))
            
            # 计算批次大小或批次数量
            total_items = len(all_texts_to_translate)
            total_words = sum(self._count_words(text) for text in all_texts_to_translate)
            batches = []
            
            # 获取批次处理模式和值
            batch_mode = self.batch_mode_var.get()
            try:
                if batch_mode == "words":
                    batch_value = self.words_batch_var.get()
                elif batch_mode == "items":
                    batch_value = self.items_batch_var.get()
                else:
                    batch_value = self.batch_count_var.get()
            except (tk.TclError, ValueError):
                # 使用保存的默认值
                if batch_mode == "words":
                    batch_value = s.get('ai_batch_words', 2000)
                elif batch_mode == "items":
                    batch_value = s.get('ai_batch_items', 10)
                else:
                    batch_value = s.get('ai_batch_count', 10)
            
            # 批次划分逻辑
            if batch_mode == "words":
                # 基于单词数量的批次划分：平均分配每批次单词数
                total_words = sum(self._count_words(text) for text in all_texts_to_translate)
                # 计算需要的批次数：向上取整(total_words / batch_value)
                total_batches = max(1, (total_words + batch_value - 1) // batch_value)
                # 计算每批次的平均单词数
                words_per_batch = max(1, (total_words + total_batches - 1) // total_batches)
                
                batches = []
                current_batch = []
                current_contexts = []
                current_words = 0
                
                for text, context in zip(all_texts_to_translate, all_group_contexts):
                    text_words = self._count_words(text)
                    current_batch.append(text)
                    current_contexts.append(context)
                    current_words += text_words
                    
                    # 当当前批次的单词数接近平均单词数，且还有下一个条目时，考虑是否拆分
                    if len(current_batch) < len(all_texts_to_translate) and abs(current_words - words_per_batch) <= abs((current_words + self._count_words(all_texts_to_translate[len(current_batch)]) - words_per_batch)):
                        # 当前批次更接近平均单词数，创建新批次
                        batches.append((current_batch.copy(), current_contexts.copy()))
                        current_batch.clear()
                        current_contexts.clear()
                        current_words = 0
                
                # 添加最后一个批次
                if current_batch:
                    batches.append((current_batch, current_contexts))
                
                # 记录批处理大小（平均每批次单词数）
                batch_size = words_per_batch
            elif batch_mode == "items":
                # 基于条目数量的批次划分：平均分配每批次条目数
                total_items = len(all_texts_to_translate)
                # 计算需要的批次数：向上取整(total_items / batch_value)
                total_batches = max(1, (total_items + batch_value - 1) // batch_value)
                # 计算每批次的平均条目数
                items_per_batch = max(1, (total_items + total_batches - 1) // total_batches)
                
                batches = []
                start_idx = 0
                
                for i in range(total_batches):
                    # 计算当前批次的结束索引，确保最后一个批次包含剩余的所有条目
                    end_idx = min(start_idx + items_per_batch, total_items)
                    batch_texts = all_texts_to_translate[start_idx:end_idx]
                    batch_contexts = all_group_contexts[start_idx:end_idx]
                    batches.append((batch_texts, batch_contexts))
                    start_idx = end_idx
                    
                    # 如果已经处理完所有条目，退出循环
                    if start_idx >= total_items:
                        break
                
                # 记录批处理大小（平均每批次条目数）
                batch_size = items_per_batch
            else:
                # 基于批次数量的批次划分：直接使用指定的批次数
                num_batches = batch_value
                # 计算每批次的条目数量
                items_per_batch = max(1, (total_items + num_batches - 1) // num_batches)
                
                batches = []
                start_idx = 0
                
                for i in range(num_batches):
                    # 计算当前批次的结束索引，确保最后一个批次包含剩余的所有条目
                    end_idx = min(start_idx + items_per_batch, total_items)
                    batch_texts = all_texts_to_translate[start_idx:end_idx]
                    batch_contexts = all_group_contexts[start_idx:end_idx]
                    batches.append((batch_texts, batch_contexts))
                    start_idx = end_idx
                    
                    # 如果已经处理完所有条目，退出循环
                    if start_idx >= total_items:
                        break
                
                # 记录批处理大小（每批次条目数）
                batch_size = items_per_batch
            
            total_batches = len(batches)
            translations_nested = [None] * total_batches
            
            # 记录翻译设置
            logging.info(f"AI翻译设置 - 模式: {translation_mode}, 批处理大小: {batch_size}")
            
            # 使用线程池执行翻译
            with ThreadPoolExecutor(max_workers=s['ai_max_threads']) as executor:
                future_map = {}
                
                for i, (batch, contexts) in enumerate(batches):
                    # 根据模式调整提示词
                    batch_prompt = self._adjust_prompt_for_mode(s['prompt'], translation_mode, contexts)
                    future_map[executor.submit(translator.translate_batch, (i, batch, s['model'], batch_prompt, s.get('ai_stream_timeout', 30)))] = i
                
                for i, future in enumerate(as_completed(future_map), 1):
                    if not self.processing:
                        break
                    
                    batch_idx = future_map[future]
                    translations_nested[batch_idx] = future.result()
                    
                    # 更新状态
                    status_text = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    
                    self.after(0, lambda s=status_text: self.workbench.status_label.config(text=s))
                    self.workbench.log_callback(status_text, "INFO")
            
            if not self.processing:
                return
            
            # 5. 合并翻译结果
            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            
            if len(translations) != len(all_texts_to_translate):
                raise ValueError(f"AI返回数量不匹配! 预期:{len(all_texts_to_translate)}, 实际:{len(translations)}")
            
            # 6. 更新翻译结果
            self.after(0, lambda: self._update_translations(all_item_mapping, translations, translation_mode))
            
        except Exception as e:
            logging.error(f"AI翻译失败: {e}", exc_info=True)
            self.after(0, lambda: messagebox.showerror("AI翻译失败", f"执行AI翻译时发生错误:\n{e}"))
            self.after(0, lambda err=e: self.workbench.status_label.config(text=f"处理失败: {str(err)}"))
        finally:
            self.after(0, lambda: setattr(self, "processing", False))
            self.after(0, lambda: self.start_button.config(state="normal"))
    
    def _generate_translation_context(self, group, translated_texts):
        """为翻译组生成上下文，确保翻译风格一致性"""
        context_parts = []
        stats = {
            'total_contexts_generated': 0,
            'group_contexts': 0,
            'similar_contexts': 0,
            'common_words_filtered': 0,
            'unique_words_processed': 0
        }
        
        # 收集该组中已翻译的文本作为参考
        for ns, idx, item in group:
            en_text = item.get("en", "").strip()
            zh_text = item.get("zh", "").strip()
            
            if zh_text:
                context_parts.append(f"{en_text} -> {zh_text}")
                stats['group_contexts'] += 1
        
        # 生成当前批次待翻译文本的关键词集合
        def generate_keywords_for_batch():
            # 常用单词过滤列表（包含冠词、介词、系动词、助动词等高频基础词汇）
            common_words = {
                # 冠词
                'the', 'a', 'an',
                
                # 系动词
                'is', 'are', 'was', 'were', 'be', 'been', 'being',
                
                # 介词
                'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'up', 'about',
                'into', 'over', 'after', 'beneath', 'under', 'above', 'across', 'through',
                'before', 'behind', 'between', 'around', 'near', 'off', 'out', 'down',
                'along', 'among', 'against', 'amongst', 'during', 'except', 'following',
                'like', 'minus', 'next', 'opposite', 'outside', 'plus', 'round', 'since',
                'than', 'toward', 'towards', 'underneath', 'until', 'unto', 'upon', 'via',
                
                # 连接词
                'as', 'but', 'and', 'or', 'nor', 'so', 'yet', 'if', 'because', 'since',
                'when', 'while', 'where', 'who', 'which', 'that', 'what', 'how', 'why',
                'whom', 'whose', 'whether', 'though', 'although', 'unless', 'until',
                'whereas', 'while', 'whenever', 'wherever', 'whoever', 'whichever',
                'whatever', 'however', 'moreover', 'furthermore', 'therefore', 'hence',
                'thus', 'consequently', 'nevertheless', 'nonetheless', 'otherwise',
                'instead', 'besides', 'though', 'although',
                
                # 代词
                'these', 'those', 'this', 'that', 'my', 'your', 'his', 'her', 'its', 'our',
                'their', 'we', 'you', 'they', 'he', 'she', 'it', 'i', 'me', 'us', 'them',
                'mine', 'yours', 'his', 'hers', 'ours', 'theirs', 'myself', 'yourself',
                'himself', 'herself', 'itself', 'ourselves', 'yourselves', 'themselves',
                'one', 'ones', 'each', 'every', 'either', 'neither', 'both', 'all', 'some',
                'any', 'none', 'much', 'many', 'few', 'little', 'several', 'enough',
                'other', 'another',
                
                # 助动词和情态动词
                'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'can', 'could',
                'may', 'might', 'must', 'have', 'has', 'had', 'not',
                
                # 限定词
                'no', 'yes', 'all', 'both', 'each', 'every', 'few', 'many', 'more',
                'most', 'some', 'such', 'any', 'little', 'much', 'enough', 'too',
                'very', 'so', 'just', 'only', 'even', 'also',
                
                # 副词
                'ever', 'never', 'now', 'then', 'here', 'there', 'up', 'down', 'in',
                'out', 'away', 'still', 'again', 'further', 'once', 'always', 'usually',
                'often', 'sometimes', 'rarely', 'seldom', 'never', 'already', 'yet',
                'just', 'only', 'even', 'also', 'too', 'very', 'so', 'such', 'much',
                'many', 'little', 'few', 'more', 'most', 'less', 'least', 'rather',
                'quite', 'almost', 'nearly', 'hardly', 'scarcely', 'barely', 'just',
                'exactly', 'precisely', 'definitely', 'certainly', 'absolutely',
                'completely', 'totally', 'fully', 'partly', 'partially', 'mostly',
                'mainly', 'chiefly', 'primarily', 'particularly', 'especially',
                'specifically', 'exactly', 'directly', 'immediately', 'soon',
                'quickly', 'slowly', 'carefully', 'easily', 'hard', 'well', 'badly',
                'better', 'best', 'worse', 'worst',
                
                # 疑问词
                'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
                'whatever', 'whichever', 'whoever', 'whomever', 'wherever', 'whenever',
                'however',
                
                # 其他常用词
                'been', 'being', 'having', 'done', 'doing', 'going', 'get', 'got', 'getting',
                'go', 'goes', 'went', 'gone', 'come', 'comes', 'came', 'coming', 'take',
                'takes', 'took', 'taken', 'make', 'makes', 'made', 'making', 'give',
                'gives', 'gave', 'given', 'use', 'uses', 'used', 'using', 'find',
                'finds', 'found', 'look', 'looks', 'looked', 'looking', 'see', 'sees',
                'saw', 'seen', 'watch', 'watches', 'watched', 'watching', 'read', 'reads',
                'read', 'reading', 'write', 'writes', 'wrote', 'written', 'writing',
                'speak', 'speaks', 'spoke', 'spoken', 'speaking', 'say', 'says', 'said',
                'saying', 'tell', 'tells', 'told', 'telling', 'think', 'thinks', 'thought',
                'thinking', 'know', 'knows', 'knew', 'known', 'knowing', 'understand',
                'understands', 'understood', 'understanding', 'learn', 'learns', 'learned',
                'learnt', 'learning', 'hear', 'hears', 'heard', 'hearing', 'listen',
                'listens', 'listened', 'listening', 'feel', 'feels', 'felt', 'feeling',
                'touch', 'touches', 'touched', 'touching', 'smell', 'smells', 'smelled',
                'smelt', 'smelling', 'taste', 'tastes', 'tasted', 'tasting', 'start',
                'starts', 'started', 'starting', 'stop', 'stops', 'stopped', 'stopping',
                'begin', 'begins', 'began', 'begun', 'beginning', 'end', 'ends', 'ended',
                'ending', 'continue', 'continues', 'continued', 'continuing', 'keep',
                'keeps', 'kept', 'keeping', 'hold', 'holds', 'held', 'holding', 'carry',
                'carries', 'carried', 'carrying', 'bring', 'brings', 'brought', 'bringing',
                'take', 'takes', 'took', 'taken', 'taking', 'send', 'sends', 'sent',
                'sending', 'receive', 'receives', 'received', 'receiving', 'give',
                'gives', 'gave', 'given', 'giving', 'get', 'gets', 'got', 'gotten', 'getting',
                'put', 'puts', 'put', 'putting', 'set', 'sets', 'set', 'setting', 'leave',
                'leaves', 'left', 'leaving', 'stay', 'stays', 'stayed', 'staying', 'come',
                'comes', 'came', 'coming', 'go', 'goes', 'went', 'gone', 'going', 'move',
                'moves', 'moved', 'moving', 'walk', 'walks', 'walked', 'walking', 'run',
                'runs', 'ran', 'running', 'jump', 'jumps', 'jumped', 'jumping', 'climb',
                'climbs', 'climbed', 'climbing', 'swim', 'swims', 'swam', 'swum', 'swimming',
                'fly', 'flies', 'flew', 'flown', 'flying', 'drive', 'drives', 'drove',
                'driven', 'driving', 'ride', 'rides', 'rode', 'ridden', 'riding', 'travel',
                'travels', 'traveled', 'travelled', 'traveling', 'travelling', 'arrive',
                'arrives', 'arrived', 'arriving', 'reach', 'reaches', 'reached', 'reaching',
                'leave', 'leaves', 'left', 'leaving', 'enter', 'enters', 'entered', 'entering',
                'exit', 'exits', 'exited', 'exiting', 'open', 'opens', 'opened', 'opening',
                'close', 'closes', 'closed', 'closing', 'turn', 'turns', 'turned', 'turning',
                'on', 'off', 'up', 'down', 'in', 'out', 'over', 'under', 'around', 'through',
                'across', 'between', 'among', 'along', 'behind', 'before', 'after', 'above',
                'below', 'beneath', 'beside', 'next', 'near', 'far', 'away', 'here', 'there',
                'now', 'then', 'soon', 'later', 'earlier', 'today', 'tomorrow', 'yesterday',
                'morning', 'afternoon', 'evening', 'night', 'day', 'week', 'month', 'year',
                'hour', 'minute', 'second', 'time', 'times', 'once', 'twice', 'again',
                'more', 'most', 'less', 'least', 'better', 'best', 'worse', 'worst',
                'good', 'bad', 'well', 'ill', 'nice', 'fine', 'great', 'small', 'big',
                'large', 'little', 'much', 'many', 'few', 'several', 'some', 'any',
                'all', 'both', 'each', 'every', 'either', 'neither', 'no', 'none',
                'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
                'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen',
                'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty', 'sixty',
                'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'billion',
                'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth',
                'ninth', 'tenth', 'eleventh', 'twelfth', 'thirteenth', 'fourteenth',
                'fifteenth', 'sixteenth', 'seventeenth', 'eighteenth', 'nineteenth',
                'twentieth', 'thirtieth', 'fortieth', 'fiftieth', 'sixtieth', 'seventieth',
                'eightieth', 'ninetieth', 'hundredth'
            }
            
            # 提取当前批次待翻译文本
            batch_texts = []
            for ns, idx, item in group:
                en_text = item.get("en", "").strip()
                batch_texts.append(en_text)
            
            # 提取所有单词并去重
            import re
            all_words = set()
            for text in batch_texts:
                # 提取单词，转换为小写
                words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
                all_words.update(words)
            
            # 过滤常用单词
            filtered_words = all_words - common_words
            stats['common_words_filtered'] = len(all_words) - len(filtered_words)
            stats['unique_words_processed'] = len(filtered_words)
            
            return filtered_words
        
        # 获取当前批次的关键词
        batch_keywords = generate_keywords_for_batch()
        
        # 只有当存在关键词时才进行关联文本筛选
        if batch_keywords:
            # 查找关联的已翻译文本
            seen_texts = set()
            for ns, idx, item in group:
                # 跳过已经处理过的文本
                current_en = item.get("en", "").strip()
                seen_texts.add(current_en)
            
            # 遍历所有已翻译文本，查找关联文本
            import re
            for en_text, zh_list in translated_texts.items():
                if en_text in seen_texts:
                    continue
                
                # 检查已翻译文本是否包含当前批次的任何关键词
                en_text_lower = en_text.lower()
                has_keyword = False
                for keyword in batch_keywords:
                    # 使用单词边界匹配，确保是完整单词
                    if re.search(r'\b' + re.escape(keyword) + r'\b', en_text_lower):
                        has_keyword = True
                        break
                
                if has_keyword:
                    # 添加关联文本作为参考
                    for zh_text in zh_list:
                        context_parts.append(f"关联文本参考: {en_text} -> {zh_text}")
                        stats['similar_contexts'] += 1
        
        stats['total_contexts_generated'] = stats['group_contexts'] + stats['similar_contexts']
        
        # 记录统计信息
        logging.info(f"上下文生成统计: {stats}")
        
        if context_parts:
            return "\n".join(context_parts)
        return ""
    

    
    def _adjust_prompt_for_mode(self, base_prompt, mode, contexts):
        """根据翻译模式调整提示词"""
        if mode == "basic":
            # 基础翻译模式：简洁直接的翻译要求
            format_note = "(如 %s, §a, \n)"  # 单独定义包含转义字符的字符串
            example = '{"0": "译文1", "1": "译文2"}'
            adjusted_prompt = f"""你是一个只输出JSON的翻译AI。
任务：将输入JSON对象中，每个数字键对应的英文字符串值翻译为简体中文。
核心指令:
1. 仅对提供的英文文本进行直接翻译，不参考任何其他内容
2. 保持原文的语气、风格和意图
3. 严格保留所有格式代码 {format_note} 和特殊字符
4. 翻译要准确、专业、自然，符合中文表达习惯
5. 注意游戏相关术语的正确翻译
最终要求:
你的回复必须是、且只能是一个JSON对象, 例如 `{example}`。
禁止在 `[` 和 `]` 或 `{{` 和 `}}` 的前后添加任何多余的文字或代码标记。"""
        elif mode == "polish":
            # 翻译润色模式：基于已有译文进行优化
            format_note = "(如 %s, §a, \n)"  # 单独定义包含转义字符的字符串
            example = '{"0": "润色后的译文1", "1": "润色后的译文2"}'
            adjusted_prompt = f"""你是一个只输出JSON的翻译润色AI。
任务：对输入JSON对象中每个数字键对应的文本进行处理，输入格式为"英文原文 -> 中文译文"，你需要基于英文原文和现有中文译文生成更优质的中文翻译。
核心指令:
1. 首先解析输入格式：英文原文 -> 中文译文
2. 基于英文原文的准确含义，对现有中文译文进行优化
3. 提高语言流畅度，使表达更符合中文习惯和游戏语境
4. 统一专业术语，确保术语一致性
5. 修正语法错误和用词不当
6. 增强表达的自然度和可读性
7. 保持原文意思和语气不变
8. 优化句子结构，提升整体质量
9. 严格保留所有格式代码 {format_note} 和特殊字符
10. 只返回优化后的中文译文，不要包含英文原文或其他格式
最终要求:
你的回复必须是、且只能是一个JSON对象, 例如 `{example}`。
禁止在 `[` 和 `]` 或 `{{` 和 `}}` 的前后添加任何多余的文字或代码标记。"""
        elif mode == "hybrid" and contexts:
            # 混合翻译模式：结合上下文的翻译要求
            from collections import Counter
            context_counts = Counter(contexts)
            most_common_context = context_counts.most_common(1)[0][0]
            
            format_note = "(如 %s, §a, \n)"  # 单独定义包含转义字符的字符串
            example = '{"0": "译文1", "1": "译文2"}'
            adjusted_prompt = f"""你是一个只输出JSON的智能翻译AI。
任务：将输入JSON对象中每个数字键对应的英文字符串值翻译为简体中文，严格参考提供的上下文。

翻译参考上下文：
{most_common_context}

核心指令:
1. 严格参考上述上下文进行翻译，确保新翻译与现有翻译风格一致
2. 使用相同的专业术语和表达方式
3. 相似文本的翻译保持高度一致性
4. 新翻译与现有翻译自然融合
5. 保持原文的语气、风格和意图
6. 严格保留所有格式代码 {format_note} 和特殊字符
7. 翻译要准确、专业、自然，符合中文表达习惯
8. 注意上下文语境，避免孤立翻译
最终要求:
你的回复必须是、且只能是一个JSON对象, 例如 `{example}`。
禁止在 `[` 和 `]` 或 `{{` 和 `}}` 的前后添加任何多余的文字或代码标记。"""
        else:
            # 默认使用原始提示词
            adjusted_prompt = base_prompt
        
        return adjusted_prompt
    

    
    def _update_translations(self, item_mapping, translations, translation_mode):
        """更新翻译结果"""
        # 强制记录当前状态用于撤销，不检查状态是否相同
        # 因为AI翻译会批量修改数据，必须确保能撤销
        self.workbench.undo_stack.append(copy.deepcopy(self.workbench.translation_data))
        self.workbench.undo_targets.append(None)
        self.workbench.redo_stack.clear()
        self.workbench.redo_targets.clear()
        self.workbench._update_history_buttons()
        
        updated_count = 0
        skipped_count = 0
        
        # 直接使用ns和idx访问translation_data，而不是使用引用
        for ((ns, idx, _), translation) in zip(item_mapping, translations):
            if translation and translation.strip():
                # 获取item对象
                item = self.workbench.translation_data[ns]['items'][idx]
                
                # 获取原文，用于标点符号一致性检查
                original_text = item.get('en', '').strip()
                
                # 处理翻译结果：如果包含" -> "分隔符，则提取右侧的中文译文
                final_translation = translation.strip()
                if " -> " in final_translation:
                    # 提取" -> "右侧的内容作为最终译文
                    final_translation = final_translation.split(" -> ")[-1].strip()
                
                # 标点符号一致性处理：如果原文末尾没有标点符号，而译文末尾有，则移除译文末尾的标点
                # 定义需要处理的标点符号列表
                punctuation_marks = ".，,。！!？?；;：:"  # 中英文标点都处理
                
                if original_text and final_translation:
                    # 检查原文末尾是否有标点
                    original_has_punctuation = original_text[-1] in punctuation_marks
                    # 检查译文末尾是否有标点
                    translation_has_punctuation = final_translation[-1] in punctuation_marks
                    
                    # 如果原文没有标点但译文有，移除译文末尾的标点
                    if not original_has_punctuation and translation_has_punctuation:
                        # 移除译文末尾的标点符号
                        final_translation = final_translation.rstrip(punctuation_marks)
                
                # 获取先前的译文
                previous_translation = item.get('zh', '').strip()
                
                # 润色模式下：只有当译文有变化时才更新
                if translation_mode == "polish":
                    if final_translation != previous_translation:
                        # 更新翻译结果
                        item['zh'] = final_translation
                        item['source'] = 'AI翻译'
                        updated_count += 1
                    else:
                        # 译文没有变化，跳过更新
                        skipped_count += 1
                else:
                    # 其他模式：直接更新
                    item['zh'] = final_translation
                    item['source'] = 'AI翻译'
                    updated_count += 1
        
        # 更新UI
        self.workbench._populate_namespace_tree()
        self.workbench._populate_item_list()
        
        # 只有当有实际更新时才设置脏标志
        if updated_count > 0:
            self.workbench._set_dirty(True)
        
        # 更新状态和日志
        if translation_mode == "polish":
            status_text = f"AI翻译润色完成，成功更新 {updated_count} 条翻译，跳过 {skipped_count} 条无变化译文"
        else:
            status_text = f"AI翻译完成，成功更新 {updated_count} 条翻译"
        
        self.workbench.status_label.config(text=status_text)
        self.workbench.log_callback(status_text, "SUCCESS")
        
        # 更新菜单栏状态
        if self.workbench.main_window:
            self.workbench.main_window.update_menu_state()
    
    def _start_export(self, selected_modules):
        """开始导出文本"""
        from tkinter import filedialog
        
        # 检查是否有选中的模组
        if not selected_modules:
            # 显示提示，要求先选中模组
            from tkinter import messagebox
            messagebox.showwarning("操作提示", "请先在左侧选择一个或多个模组进行处理。")
            # 恢复界面状态
            self.processing = False
            self.start_button.config(state="normal")
            self.cancel_button.config(text="取消")
            return
        
        # 获取导出设置，将显示值转换为内部值
        export_scope_display = self.export_scope_var.get()
        export_scope = self.export_scopes_values.get(export_scope_display, "all")
        
        export_method_display = self.export_method_var.get()
        export_method = self.export_method_values.get(export_method_display, "file")
        
        # 获取导出数据
        export_data = []
        
        for ns in selected_modules:
            items = self.workbench.translation_data.get(ns, {}).get("items", [])
            for idx, item in enumerate(items):
                en_text = item.get("en", "").strip()
                zh_text = item.get("zh", "").strip()
                source = item.get("source", "")
                
                # 根据导出范围过滤条目
                include = False
                if export_scope == "all":
                    # 导出全部有原文的条目
                    if en_text:
                        include = True
                elif export_scope == "pending":
                    # 仅导出待翻译的条目（有原文但无译文）
                    if en_text and not zh_text:
                        include = True
                elif export_scope == "completed":
                    # 仅导出已翻译的条目（有原文且有译文）
                    if en_text and zh_text:
                        include = True
                
                if include:
                    export_data.append({
                        "namespace": ns,
                        "key": item["key"],
                        "en": item["en"],
                        "zh": item.get("zh", ""),
                        "source": source
                    })
        
        if not export_data:
            self.after(0, lambda: messagebox.showinfo("提示", "没有符合条件的条目需要导出。"))
            self.after(0, lambda: self.workbench.status_label.config(text="准备就绪"))
            self.after(0, lambda: setattr(self, "processing", False))
            self.after(0, lambda: self.start_button.config(state="normal"))
            return
        
        # 根据导出方式处理
        if export_method == "file":
            # 导出到文件
            file_path = filedialog.asksaveasfilename(
                title="选择导出文件",
                defaultextension=".json",
                filetypes=[("JSON 文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            
            if not file_path:
                self.processing = False
                self.start_button.config(state="normal")
                return
            
            try:
                # 保存到文件
                import json
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                
                status_text = f"导出完成，共导出 {len(export_data)} 条记录"
                self.after(0, lambda s=status_text: self.workbench.status_label.config(text=s))
                self.after(0, lambda: self.workbench.log_callback(f"成功导出 {len(export_data)} 条记录到 {file_path}", "SUCCESS"))
            except Exception as e:
                logging.error(f"导出文件失败: {e}")
                self.after(0, lambda err=e: messagebox.showerror("导出失败", f"导出文件时发生错误:\n{err}"))
        else:
            # 导出到剪贴板
            try:
                import json
                export_text = json.dumps(export_data, ensure_ascii=False, indent=4)
                self.clipboard_clear()
                self.clipboard_append(export_text)
                
                status_text = f"已将 {len(export_data)} 条记录复制到剪贴板"
                self.after(0, lambda s=status_text: self.workbench.status_label.config(text=s))
                self.after(0, lambda: self.workbench.log_callback(f"成功将 {len(export_data)} 条记录复制到剪贴板", "SUCCESS"))
                self.after(0, lambda: messagebox.showinfo("导出完成", f"已将 {len(export_data)} 条记录复制到剪贴板"))
            except Exception as e:
                logging.error(f"复制到剪贴板失败: {e}")
                self.after(0, lambda err=e: messagebox.showerror("导出失败", f"复制到剪贴板时发生错误:\n{err}"))
        
        self.after(0, lambda: setattr(self, "processing", False))
        self.after(0, lambda: self.start_button.config(state="normal"))
    
    def _start_import(self, selected_modules):
        """开始导入翻译"""
        # 检查是否有选中的模组
        if not selected_modules:
            # 显示提示，要求先选中模组
            from tkinter import messagebox
            messagebox.showwarning("操作提示", "请先在左侧选择一个或多个模组进行处理。")
            # 恢复界面状态
            self.processing = False
            self.start_button.config(state="normal")
            self.cancel_button.config(text="取消")
            return
        
        # 这里可以调用workbench的导入功能
        # 暂时使用现有的导入机制
        self.processing = False
        self.start_button.config(state="normal")
        
        # 根据导入来源执行不同操作，将显示值转换为内部值
        import_source_display = self.import_source_var.get()
        import_source = self.import_sources_values.get(import_source_display, "file")
        if import_source == "file":
            self.workbench._import_from_file()
        else:
            self.workbench._import_from_clipboard()