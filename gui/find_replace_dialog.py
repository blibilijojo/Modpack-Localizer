import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui.theme_utils import set_title_bar_theme

class FindReplaceDialog(tk.Toplevel):
    def __init__(self, parent, action_callback, initial_settings):
        super().__init__(parent)
        self.parent = parent
        self.action_callback = action_callback
        
        self.title("查找和替换")
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        set_title_bar_theme(self, self.parent.style)

        self.find_var = tk.StringVar(value=initial_settings.get("find_text", ""))
        self.replace_var = tk.StringVar(value=initial_settings.get("replace_text", ""))
        self.match_case_var = tk.BooleanVar(value=initial_settings.get("match_case", False))
        self.wrap_around_var = tk.BooleanVar(value=initial_settings.get("wrap", True))
        self.search_scope_var = tk.StringVar(value=initial_settings.get("scope", "current"))
        self.search_direction_var = tk.StringVar(value=initial_settings.get("direction", "down"))
        self.search_column_var = tk.StringVar(value=initial_settings.get("search_column", "all"))
        
        self._create_widgets()
        self.find_entry.focus_set()

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill="x", expand=True)
        entry_frame.columnconfigure(1, weight=1)
        
        ttk.Label(entry_frame, text="查找内容:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.find_entry = ttk.Entry(entry_frame, textvariable=self.find_var)
        self.find_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(entry_frame, text="替换为:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(entry_frame, textvariable=self.replace_var).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        options_container = ttk.Frame(main_frame)
        options_container.pack(fill="x", pady=10)
        
        options_frame = tk_ttk.LabelFrame(options_container, text="选项", padding=10)
        options_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ttk.Checkbutton(options_frame, text="大小写匹配", variable=self.match_case_var).pack(anchor="w")
        ttk.Checkbutton(options_frame, text="循环查找", variable=self.wrap_around_var).pack(anchor="w")
        
        column_frame = tk_ttk.LabelFrame(options_container, text="列范围", padding=10)
        column_frame.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Radiobutton(column_frame, text="全部列", variable=self.search_column_var, value="all").pack(anchor="w")
        ttk.Radiobutton(column_frame, text="原文", variable=self.search_column_var, value="en").pack(anchor="w")
        ttk.Radiobutton(column_frame, text="译文", variable=self.search_column_var, value="zh").pack(anchor="w")

        scope_frame = tk_ttk.LabelFrame(options_container, text="范围", padding=10)
        scope_frame.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Radiobutton(scope_frame, text="当前模组", variable=self.search_scope_var, value="current").pack(anchor="w")
        ttk.Radiobutton(scope_frame, text="所有模组", variable=self.search_scope_var, value="all").pack(anchor="w")

        direction_frame = tk_ttk.LabelFrame(options_container, text="方向", padding=10)
        direction_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Radiobutton(direction_frame, text="向上", variable=self.search_direction_var, value="up").pack(anchor="w")
        ttk.Radiobutton(direction_frame, text="向下", variable=self.search_direction_var, value="down").pack(anchor="w")
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        ttk.Button(btn_frame, text="查找下一个", command=lambda: self._trigger_action("find")).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(btn_frame, text="替换", command=lambda: self._trigger_action("replace")).grid(row=0, column=1, sticky="ew")
        ttk.Button(btn_frame, text="全部替换", command=lambda: self._trigger_action("replace_all")).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5,0))
    
    def get_current_params(self):
        return {
            "find_text": self.find_var.get(),
            "replace_text": self.replace_var.get(),
            "match_case": self.match_case_var.get(),
            "wrap": self.wrap_around_var.get(),
            "scope": self.search_scope_var.get(),
            "direction": self.search_direction_var.get(),
            "search_column": self.search_column_var.get()
        }

    def _trigger_action(self, action_type):
        if not self.find_var.get():
            self.bell()
            self.find_entry.focus_set()
            return

        params = self.get_current_params()
        self.action_callback(action_type, params)

    def _on_close(self):
        params = self.get_current_params()
        self.action_callback("close", params)
        self.destroy()