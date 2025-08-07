# gui/manual_translation_window.py

import tkinter as tk
import ttkbootstrap as ttk
from tkinter import scrolledtext
from collections import defaultdict

class ManualTranslationWindow(tk.Toplevel):
    def __init__(self, parent, items_to_translate: list, existing_translations: dict):
        super().__init__(parent)
        self.parent = parent
        self.items_to_translate = items_to_translate
        self.existing_translations = existing_translations
        self.result = None
        self.current_selection_info = None  # Stores info about the currently selected item
        self.after_id = None # To debounce saving

        self._setup_window()
        self._process_data()
        self._create_widgets()
        self._populate_namespace_tree()
        self._update_ui_state()

    def _setup_window(self):
        self.title("手动翻译工作台")
        self.geometry("1100x800")
        self.minsize(900, 600)
        self.transient(self.parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _process_data(self):
        self.data_by_namespace = defaultdict(list)
        for namespace, key, en_val in self.items_to_translate:
            self.data_by_namespace[namespace].append(
                {'key': key, 'en': en_val, 'zh': ''}
            )

    def _create_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        left_frame = ttk.Frame(main_pane, padding=5)
        ttk.Label(left_frame, text="模组 (命名空间)", bootstyle="primary").pack(anchor="w", pady=(0, 5))
        self.ns_tree = ttk.Treeview(left_frame, show="tree")
        self.ns_tree.pack(fill="both", expand=True)
        self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        main_pane.add(left_frame, weight=1)

        right_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
        main_pane.add(right_pane, weight=4)

        table_frame = ttk.Frame(right_pane, padding=5)
        self.trans_tree = ttk.Treeview(table_frame, columns=("key", "english", "chinese"), show="headings")
        self.trans_tree.heading("key", text="原文Key")
        self.trans_tree.heading("english", text="英文原文")
        self.trans_tree.heading("chinese", text="中文译文")
        self.trans_tree.column("key", width=200, stretch=False)
        self.trans_tree.column("english", width=250, stretch=True)
        self.trans_tree.column("chinese", width=250, stretch=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.trans_tree.pack(fill="both", expand=True)
        self.trans_tree.bind("<<TreeviewSelect>>", self._on_translation_selected)
        right_pane.add(table_frame, weight=3)

        editor_frame = ttk.LabelFrame(right_pane, text="翻译编辑器", padding=10)
        editor_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(editor_frame, text="英文原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=5, pady=5)
        self.en_text_display = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word", state="disabled", relief="flat", background=self.cget('bg'))
        self.en_text_display.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(editor_frame, text="中文译文:", anchor="nw").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word")
        self.zh_text_input.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.zh_text_input.bind("<KeyRelease>", self._on_zh_text_changed)
        
        # --- NEW: Dictionary Search Button ---
        editor_btn_frame = ttk.Frame(editor_frame)
        editor_btn_frame.grid(row=2, column=1, sticky="e", pady=(5,0))
        ttk.Button(editor_btn_frame, text="查询词典", command=self._open_dict_search, bootstyle="info-outline").pack()

        right_pane.add(editor_frame, weight=1)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        self.status_label = ttk.Label(btn_frame, text="请选择一个条目进行翻译")
        self.status_label.pack(side="left", fill="x", expand=True)
        ttk.Button(btn_frame, text="完成并生成资源包", command=self._on_save, bootstyle="success").pack(side="right")
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, bootstyle="secondary").pack(side="right", padx=10)

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        
        initial_query = ""
        if self.current_selection_info:
            info = self.current_selection_info
            item_data = self.data_by_namespace[info['ns']][info['idx']]
            initial_query = item_data['en']
        
        DictionarySearchWindow(self, initial_query=initial_query)

    def _populate_namespace_tree(self):
        for ns, items in sorted(self.data_by_namespace.items()):
            self.ns_tree.insert("", "end", iid=ns, text=f"{ns} ({len(items)})")

    def _on_namespace_selected(self, event=None):
        selection = self.ns_tree.selection()
        if not selection: return
        
        selected_ns = selection[0]
        
        self.trans_tree.delete(*self.trans_tree.get_children())
            
        items_for_ns = self.data_by_namespace.get(selected_ns, [])
        for idx, item_data in enumerate(items_for_ns):
            row_id_str = f"{selected_ns}___{idx}"
            self.trans_tree.insert("", "end", iid=row_id_str, values=(item_data['key'], item_data['en'], item_data['zh']))
        
        self.current_selection_info = None
        self._update_ui_state()

    def _on_translation_selected(self, event=None):
        selection = self.trans_tree.selection()
        if not selection: 
            self.current_selection_info = None
            self._update_ui_state()
            return

        row_id = selection[0]
        ns, idx_str = row_id.rsplit('___', 1)
        idx = int(idx_str)
        
        self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': row_id}
        
        item_data = self.data_by_namespace[ns][idx]
        
        self.en_text_display.config(state="normal")
        self.en_text_display.delete("1.0", "end")
        self.en_text_display.insert("1.0", item_data['en'])
        self.en_text_display.config(state="disabled")

        # Unbind before inserting to prevent firing the change event
        self.zh_text_input.unbind("<KeyRelease>")
        self.zh_text_input.delete("1.0", "end")
        self.zh_text_input.insert("1.0", item_data['zh'])
        # Re-bind after inserting
        self.zh_text_input.bind("<KeyRelease>", self._on_zh_text_changed)
        
        self._update_ui_state()

    def _on_zh_text_changed(self, event=None):
        if self.after_id:
            self.after_cancel(self.after_id)
        self.after_id = self.after(500, self._save_current_translation) # Debounce save

    def _save_current_translation(self):
        if not self.current_selection_info: return
        
        new_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        
        info = self.current_selection_info
        ns, idx, row_id = info['ns'], info['idx'], info['row_id']
        
        self.data_by_namespace[ns][idx]['zh'] = new_zh_text
        
        current_values = self.trans_tree.item(row_id, 'values')
        self.trans_tree.item(row_id, values=(current_values[0], current_values[1], new_zh_text))

        self.after_id = None

    def _update_ui_state(self):
        if self.current_selection_info:
            self.zh_text_input.config(state="normal")
            self.status_label.config(text=f"正在编辑: {self.current_selection_info['row_id']}")
        else:
            self.zh_text_input.config(state="disabled")
            self.en_text_display.config(state="normal")
            self.en_text_display.delete("1.0", "end")
            self.en_text_display.config(state="disabled")
            self.zh_text_input.delete("1.0", "end")
            self.status_label.config(text="请选择一个条目进行翻译")

    def _on_save(self):
        if self.after_id: # If a debounced save is pending, do it now
            self.after_cancel(self.after_id)
            self._save_current_translation()
        
        final_lookup = self.existing_translations.copy()
        for ns, items in self.data_by_namespace.items():
            for item in items:
                if item['zh'] and item['zh'].strip():
                    if ns not in final_lookup:
                        final_lookup[ns] = {}
                    final_lookup[ns][item['key']] = item['zh']

        self.result = final_lookup
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()