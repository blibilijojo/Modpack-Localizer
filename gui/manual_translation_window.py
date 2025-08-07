import tkinter as tk
import ttkbootstrap as ttk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog
from collections import defaultdict
import json
from datetime import datetime
from pathlib import Path
from utils import config_manager # 核心修改：导入 config_manager

class ManualTranslationWindow(tk.Toplevel):
    def __init__(self, parent, items_to_process: list | dict, existing_translations: dict, namespace_formats: dict, current_settings: dict):
        super().__init__(parent)
        self.parent = parent
        self.existing_translations = existing_translations
        self.namespace_formats = namespace_formats
        self.current_settings = current_settings
        self.result_translations = None
        self.current_selection_info = None
        self.after_id = None
        self.is_dirty = False
        
        self.is_programmatically_updating_text = False

        self._setup_window()
        if isinstance(items_to_process, list):
            self._process_data_from_list(items_to_process)
        else:
            self.data_by_namespace = defaultdict(list, items_to_process)

        self._create_widgets()
        self._populate_namespace_tree()
        self._update_ui_state()

    def _setup_window(self):
        self.title("手动翻译工作台")
        self.geometry("1100x800")
        self.minsize(900, 600)
        self.transient(self.parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

    def _process_data_from_list(self, items_to_translate: list):
        self.data_by_namespace = defaultdict(list)
        for namespace, key, en_val in items_to_translate:
            self.data_by_namespace[namespace].append({'key': key, 'en': en_val, 'zh': ''})

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
        self.trans_tree.heading("english", text="原文")
        self.trans_tree.heading("chinese", text="译文")
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
        ttk.Label(editor_frame, text="原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=5, pady=5)
        self.en_text_display = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word", state="disabled", relief="flat", background=self.cget('bg'))
        self.en_text_display.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(editor_frame, text="译文:", anchor="nw").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word")
        self.zh_text_input.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.zh_text_input.bind("<KeyRelease>", self._on_zh_text_changed)
        editor_btn_frame = ttk.Frame(editor_frame)
        editor_btn_frame.grid(row=2, column=1, sticky="e", pady=(5,0))
        
        # --- 核心修改：新增“存入个人词典”按钮 ---
        self.add_to_dict_btn = ttk.Button(editor_btn_frame, text="⭐ 存入个人词典", command=self._add_to_user_dictionary, bootstyle="info-outline")
        self.add_to_dict_btn.pack(side="left", padx=(0, 10))
        ttk.Button(editor_btn_frame, text="查询词典", command=self._open_dict_search, bootstyle="info-outline").pack(side="left")
        # --- 修改结束 ---

        right_pane.add(editor_frame, weight=1)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        self.status_label = ttk.Label(btn_frame, text="请选择一个条目进行翻译")
        self.status_label.pack(side="left", fill="x", expand=True)
        ttk.Button(btn_frame, text="保存项目...", command=self._save_project, bootstyle="info").pack(side="left", padx=(0, 20))
        ttk.Button(btn_frame, text="完成并生成资源包", command=self._on_finish, bootstyle="success").pack(side="right")
        ttk.Button(btn_frame, text="取消", command=self._on_close_request, bootstyle="secondary").pack(side="right", padx=10)

    # --- 新增：将当前翻译存入个人词典的方法 ---
    def _add_to_user_dictionary(self):
        if not self.current_selection_info:
            return

        info = self.current_selection_info
        item_data = self.data_by_namespace[info['ns']][info['idx']]
        key = item_data['key']
        origin_name = item_data['en']
        translation = self.zh_text_input.get("1.0", "end-1c").strip()

        if not translation:
            messagebox.showwarning("操作无效", "译文不能为空！", parent=self)
            return

        # 弹窗询问用户保存模式
        # askyesnocancel returns True for Yes, False for No, None for Cancel
        save_by_key = messagebox.askyesnocancel(
            "选择保存模式",
            f"如何保存这条翻译？\n\n- [是] 按“Key”保存 (最高优先级，精确匹配 {key}) \n- [否] 按“原文”保存 (较高优先级，模糊匹配 {origin_name})\n- [取消] 不执行任何操作",
            parent=self
        )

        if save_by_key is None: # 用户点击了取消
            return
        
        user_dict = config_manager.load_user_dict()
        
        if save_by_key: # 按Key保存
            user_dict["by_key"][key] = translation
            save_mode_str = f"Key: {key}"
        else: # 按原文保存
            user_dict["by_origin_name"][origin_name] = translation
            save_mode_str = f"原文: {origin_name}"

        config_manager.save_user_dict(user_dict)
        self.status_label.config(text=f"成功！已将“{translation}”存入个人词典 ({save_mode_str})")

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        initial_query = ""
        if self.current_selection_info:
            info = self.current_selection_info
            item_data = self.data_by_namespace[info['ns']][info['idx']]
            initial_query = item_data['en']
        DictionarySearchWindow(self, initial_query=initial_query)
        
    def _populate_namespace_tree(self):
        self._force_save_pending_edit()
        for ns, items in sorted(self.data_by_namespace.items()):
            self.ns_tree.insert("", "end", iid=ns, text=f"{ns} ({len(items)})")

    def _on_namespace_selected(self, event=None):
        self._force_save_pending_edit()
        self.current_selection_info = None
        self._update_ui_state()

        selection = self.ns_tree.selection()
        if not selection:
            self.trans_tree.delete(*self.trans_tree.get_children())
            return
            
        selected_ns = selection[0]

        self.trans_tree.delete(*self.trans_tree.get_children())
        items_for_ns = self.data_by_namespace.get(selected_ns, [])
        for idx, item_data in enumerate(items_for_ns):
            row_id_str = f"{selected_ns}___{idx}"
            self.trans_tree.insert("", "end", iid=row_id_str, values=(item_data['key'], item_data['en'], item_data.get('zh', '')))

    def _on_translation_selected(self, event=None):
        self._force_save_pending_edit()
        
        selection = self.trans_tree.selection()
        if not selection:
            return
        
        row_id = selection[0]
        try:
            ns, idx_str = row_id.rsplit('___', 1)
            idx = int(idx_str)
        except ValueError:
            return

        self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': row_id}
        item_data = self.data_by_namespace[ns][idx]
        
        self.is_programmatically_updating_text = True
        
        self.en_text_display.config(state="normal")
        self.en_text_display.delete("1.0", "end")
        self.en_text_display.insert("1.0", item_data['en'])
        self.en_text_display.config(state="disabled")
        
        self.zh_text_input.delete("1.0", "end")
        self.zh_text_input.insert("1.0", item_data.get('zh', ''))
        
        self.is_programmatically_updating_text = False
        
        self._update_ui_state()

    def _on_zh_text_changed(self, event=None):
        if self.is_programmatically_updating_text:
            return
            
        self.is_dirty = True
        if self.after_id:
            self.after_cancel(self.after_id)
        self.after_id = self.after(500, self._save_current_translation)

    def _force_save_pending_edit(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
            self._save_current_translation()
            
    def _save_current_translation(self):
        if not self.current_selection_info:
            return

        new_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        
        info = self.current_selection_info
        ns, idx, row_id = info['ns'], info['idx'], info['row_id']
        
        if self.data_by_namespace[ns][idx].get('zh', '') != new_zh_text:
            self.data_by_namespace[ns][idx]['zh'] = new_zh_text
            
            current_values = self.trans_tree.item(row_id, 'values')
            self.trans_tree.item(row_id, values=(current_values[0], current_values[1], new_zh_text))
            
            self.status_label.config(text=f"已自动保存编辑: {info['row_id']}")
        
    def _update_ui_state(self):
        is_item_selected = bool(self.current_selection_info)

        self.zh_text_input.config(state="normal" if is_item_selected else "disabled")
        self.add_to_dict_btn.config(state="normal" if is_item_selected else "disabled")

        if is_item_selected:
            self.status_label.config(text=f"正在编辑: {self.current_selection_info['row_id']}")
        else:
            self.en_text_display.config(state="normal")
            self.en_text_display.delete("1.0", "end")
            self.en_text_display.config(state="disabled")
            
            self.zh_text_input.delete("1.0", "end")
            
            self.status_label.config(text="请选择一个条目进行翻译")
    
    def _get_full_save_data(self) -> dict:
        return {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "settings_snapshot": {
                "mods_dir": self.current_settings.get("mods_dir"),
                "output_dir": self.current_settings.get("output_dir")
            },
            "pack_settings": self.current_settings.get("pack_settings"),
            "existing_translations": self.existing_translations,
            "manual_translation_data": self.data_by_namespace,
            "namespace_formats": self.namespace_formats
        }

    def _save_project(self) -> bool:
        self._force_save_pending_edit()
        save_path = filedialog.asksaveasfilename(
            title="保存翻译项目",
            defaultextension=".sav",
            filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json")]
        )
        if not save_path:
            return False
        try:
            save_data = self._get_full_save_data()
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4, ensure_ascii=False)
            self.is_dirty = False
            self.status_label.config(text=f"项目已成功保存到: {Path(save_path).name}")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"保存项目文件时出错：\n{e}")
            return False
    
    def _on_finish(self):
        self._force_save_pending_edit()
        final_lookup = self.existing_translations.copy()
        for ns, items in self.data_by_namespace.items():
            for item in items:
                if item.get('zh', '').strip():
                    if ns not in final_lookup:
                        final_lookup[ns] = {}
                    final_lookup[ns][item['key']] = item['zh']
        self.result_translations = final_lookup
        self.destroy()
        
    def _on_close_request(self):
        self._force_save_pending_edit()
        if self.is_dirty:
            response = messagebox.askyesnocancel(
                "未保存的更改",
                "您有未保存的翻译进度，是否要保存？\n\n- “是”：保存并关闭\n- “否”：不保存并关闭\n- “取消”：返回工作台",
                parent=self
            )
            if response is True:
                if self._save_project():
                    self.result_translations = None
                    self.destroy()
            elif response is False:
                self.result_translations = None
                self.destroy()
            else:
                return
        else:
            self.result_translations = None
            self.destroy()