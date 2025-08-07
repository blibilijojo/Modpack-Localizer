# gui/dictionary_search_window.py

import tkinter as tk
import ttkbootstrap as ttk
import logging
from utils.dictionary_searcher import DictionarySearcher
from utils.config_manager import load_config
from gui import ui_utils

class DictionarySearchWindow(tk.Toplevel):
    SEARCH_MODES = {
        "原文查译文": "en",
        "译文查原文": "zh"
    }

    def __init__(self, parent, initial_query=""):
        super().__init__(parent)
        self.parent = parent
        self.initial_query = initial_query
        
        logging.info("初始化词典查询窗口...")
        self.config = load_config()
        self.searcher = DictionarySearcher(self.config.get("community_dict_path"))

        self._setup_window()
        self._create_widgets()

        if not self.searcher.is_available():
            self.search_entry.config(state="disabled")
            self.search_button.config(state="disabled")
            self.mode_combo.config(state="disabled")
            self.after(100, lambda: ui_utils.show_error(
                "词典不可用", 
                "未找到或无法加载社区词典文件。\n请在主界面的“路径设置”中指定正确的 `Dict-Sqlite.db` 文件。", 
                parent=self
            ))
        
        if self.initial_query:
            self.search_var.set(self.initial_query)
            self.after(50, self._perform_search)

    def _setup_window(self):
        self.title("社区词典查询")
        self.geometry("800x600")
        self.minsize(600, 400)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        search_frame = ttk.Frame(main_frame)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0,5))
        self.search_entry.bind("<Return>", lambda e: self._perform_search())
        
        self.mode_var = tk.StringVar(value="原文查译文")
        self.mode_combo = ttk.Combobox(search_frame, textvariable=self.mode_var,
                                       values=list(self.SEARCH_MODES.keys()),
                                       state="readonly", width=12)
        self.mode_combo.grid(row=0, column=1, padx=(0,5))
        self.mode_combo.bind('<MouseWheel>', lambda e: "break")

        self.search_button = ttk.Button(search_frame, text="搜索", command=self._perform_search, bootstyle="primary")
        self.search_button.grid(row=0, column=2)

        table_frame = ttk.Frame(main_frame)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_frame, columns=("key", "origin", "trans", "version"), show="headings")
        self.tree.heading("key", text="Key")
        self.tree.heading("origin", text="原文 (Origin)")
        self.tree.heading("trans", text="译文 (Translation)")
        self.tree.heading("version", text="版本")

        self.tree.column("key", width=200, stretch=False)
        self.tree.column("origin", width=250, stretch=True)
        self.tree.column("trans", width=250, stretch=True)
        self.tree.column("version", width=80, stretch=False, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _perform_search(self):
        logging.info("UI请求执行搜索...")
        if not self.searcher.is_available():
            logging.warning("搜索请求被中止，因为词典不可用。")
            return
            
        query = self.search_var.get()
        if not query.strip():
            logging.info("搜索请求被中止，因为查询内容为空。")
            return
            
        self.search_button.config(state="disabled", text="搜索中...")
        self.tree.delete(*self.tree.get_children())
        self.update_idletasks()

        search_mode = self.SEARCH_MODES[self.mode_var.get()]
        logging.info(f"准备在 '{search_mode}' 模式下搜索 '{query}'")
        
        results = []
        if search_mode == "en":
            results = self.searcher.search_by_english(query)
        elif search_mode == "zh":
            results = self.searcher.search_by_chinese(query)
        
        logging.info(f"搜索操作完成，从 searcher 获得 {len(results)} 条结果。")
        self.search_button.config(state="normal", text="搜索")

        if not results:
            logging.info("结果为空，在表格中插入'无结果'提示。")
            self.tree.insert("", "end", values=("无结果", f"未能找到与 '{query}' 相关的条目", "", ""))
        else:
            logging.info(f"正在向表格中填充 {len(results)} 条结果...")
            for item in results:
                # FIX: Use the correct, case-sensitive keys from the database schema
                self.tree.insert("", "end", values=(
                    item.get('KEY', ''),
                    item.get('ORIGIN_NAME', ''),
                    item.get('TRANS_NAME', ''),
                    item.get('VERSION', '')
                ))
            logging.info("结果填充完毕。")

    def on_close(self):
        logging.info("关闭词典查询窗口...")
        if self.searcher:
            self.searcher.close()
        self.destroy()