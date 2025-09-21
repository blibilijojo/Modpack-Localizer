import tkinter as tk
import ttkbootstrap as ttk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog
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
from services.gemini_translator import GeminiTranslator
from gui import ui_utils
from gui.custom_widgets import ToolTip

class TranslationWorkbench(tk.Toplevel):
    def __init__(self, parent, initial_data: dict, namespace_formats: dict, raw_english_files: dict, current_settings: dict, log_callback=None, project_path: str | None = None, finish_button_text: str = "完成并生成资源包"):
        super().__init__(parent)
        self.parent = parent
        self.translation_data = initial_data
        self.namespace_formats = namespace_formats
        self.raw_english_files = raw_english_files
        self.current_settings = current_settings
        self.log_callback = log_callback or (lambda msg, lvl: None)
        self.final_translations = None
        self.current_selection_info = None
        self.sort_column = '#0'
        self.sort_reverse = False
        self.original_headings = {}
        
        self.current_project_path = project_path
        self.is_dirty = False
        self.base_title = "翻译工作台"

        self.undo_stack = []
        self.redo_stack = []
        self.undo_targets = []
        self.redo_targets = []
        
        self.finish_button_text = finish_button_text

        self._setup_window()
        self._create_widgets()

        self._record_action(target_iid=None) 
        self._update_history_buttons()
        self.bind_all("<Control-z>", self._undo)
        self.bind_all("<Control-y>", self._redo)

        self._setup_treeview_tags()
        self._populate_namespace_tree()
        self._update_ui_state(interactive=True, item_selected=False)
        self._set_dirty(False)

    def _setup_window(self):
        self.title(self.base_title)
        self.geometry("1200x800")
        self.minsize(1000, 600)
        self.resizable(True, True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

    def _set_initial_sash_position(self):
        try:
            width = self.main_pane.winfo_width()
            self.main_pane.sashpos(0, width // 3)
        except tk.TclError:
            pass

    def _create_widgets(self):
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        left_frame = ttk.Frame(self.main_pane, padding=5)
        ttk.Label(left_frame, text="模组列表", bootstyle="primary").pack(anchor="w", pady=(0, 5))
        self.ns_tree = ttk.Treeview(left_frame, columns=("pending", "completed"), show="tree headings")
        
        columns_to_sort = {
            "#0": "模组 (文件名)",
            "pending": "待翻译",
            "completed": "已翻译"
        }

        for col, text in columns_to_sort.items():
            self.original_headings[col] = text
            self.ns_tree.heading(col, text=text, command=lambda c=col: self._sort_by_column(c))
        
        self.ns_tree.column("#0", width=220, minwidth=160, stretch=True)
        self.ns_tree.column("pending", width=60, stretch=False, anchor="center")
        self.ns_tree.column("completed", width=60, stretch=False, anchor="center")
        
        self.ns_tree.pack(fill="both", expand=True)
        self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        self.main_pane.add(left_frame, weight=1)

        right_pane = ttk.PanedWindow(self.main_pane, orient=tk.VERTICAL)
        self.main_pane.add(right_pane, weight=2)

        table_container = ttk.Frame(right_pane, padding=5)
        self.trans_tree = ttk.Treeview(table_container, columns=("key", "english", "chinese", "source"), show="headings")
        self.trans_tree.heading("key", text="原文Key"); self.trans_tree.column("key", width=200, stretch=False)
        self.trans_tree.heading("english", text="原文"); self.trans_tree.column("english", width=250, stretch=True)
        self.trans_tree.heading("chinese", text="译文"); self.trans_tree.column("chinese", width=250, stretch=True)
        self.trans_tree.heading("source", text="来源"); self.trans_tree.column("source", width=120, stretch=False)
        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y"); self.trans_tree.pack(fill="both", expand=True)
        self.trans_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        right_pane.add(table_container, weight=3)
        
        editor_frame = ttk.LabelFrame(right_pane, text="翻译编辑器", padding=10)
        editor_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(editor_frame, text="原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=5, pady=5)
        self.en_text_display = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word", state="disabled", relief="flat", background=self.cget('bg'))
        self.en_text_display.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        zh_header_frame = ttk.Frame(editor_frame); zh_header_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=(5,0))
        ttk.Label(zh_header_frame, text="译文:", anchor="nw").pack(side="left")
        shortcut_info_label = ttk.Label(zh_header_frame, text="快捷键: Enter = 跳转到下一个条目 | Ctrl+Enter = 跳转到下一个待翻译项", bootstyle="secondary")
        shortcut_info_label.pack(side="right")
        
        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word", state="disabled")
        self.zh_text_input.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.zh_text_input.bind("<<Modified>>", self._on_text_modified)
        self.zh_text_input.bind("<FocusOut>", lambda e: self._save_current_edit())
        self.zh_text_input.bind("<Return>", self._save_and_jump_sequential)
        self.zh_text_input.bind("<Control-Return>", self._save_and_jump_pending)

        editor_btn_frame = ttk.Frame(editor_frame); editor_btn_frame.grid(row=3, column=1, sticky="e", pady=(5,0))
        self.ai_translate_button = ttk.Button(editor_btn_frame, text="🚀 一键 AI 翻译 (空缺项)", command=self._run_ai_translation_async, bootstyle="success-outline")
        self.ai_translate_button.pack(side="left", padx=(0, 10))
        self.add_to_dict_btn = ttk.Button(editor_btn_frame, text="⭐ 存入个人词典", command=self._add_to_user_dictionary, state="disabled", bootstyle="info-outline")
        self.add_to_dict_btn.pack(side="left", padx=(0, 10))
        
        self.undo_btn = ttk.Button(editor_btn_frame, text="撤销", command=self._undo, bootstyle="info-outline")
        self.undo_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.undo_btn, "撤销上一步操作 (Ctrl+Z)")

        self.redo_btn = ttk.Button(editor_btn_frame, text="重做", command=self._redo, bootstyle="info-outline")
        self.redo_btn.pack(side="left", padx=(0, 10))
        ToolTip(self.redo_btn, "重做已撤销的操作 (Ctrl+Y)")

        ttk.Button(editor_btn_frame, text="查询词典", command=self._open_dict_search, bootstyle="info-outline").pack(side="left")
        right_pane.add(editor_frame, weight=1)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        self.status_label = ttk.Label(btn_frame, text="请选择一个模组以开始")
        self.status_label.pack(side="left", fill="x", expand=True)
        
        self.cancel_button = ttk.Button(btn_frame, text="取消", command=self._on_close_request, bootstyle="secondary")
        self.cancel_button.pack(side="right", padx=10)
        
        self.finish_button = ttk.Button(btn_frame, text=self.finish_button_text, command=self._on_finish, bootstyle="success")
        self.finish_button.pack(side="right")
        self.save_button = ttk.Button(btn_frame, text="保存项目...", command=self._save_project, bootstyle="info")
        self.save_button.pack(side="right", padx=10)
        
        self.after(1, self._set_initial_sash_position)

    def _record_action(self, target_iid: str | None):
        if self.undo_stack and self.translation_data == self.undo_stack[-1]:
            return
        
        self.undo_stack.append(copy.deepcopy(self.translation_data))
        self.undo_targets.append(target_iid)
        self.redo_stack.clear()
        self.redo_targets.clear()
        self._update_history_buttons()

    def _undo(self, event=None):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            target_to_reselect = self.undo_targets.pop()
            self.redo_targets.append(target_to_reselect)
            
            self.translation_data = copy.deepcopy(self.undo_stack[-1])
            
            self._set_dirty(True)
            self._full_ui_refresh(target_to_reselect)
            self._update_history_buttons()

    def _redo(self, event=None):
        if self.redo_stack:
            self.undo_stack.append(self.redo_stack.pop())
            target_to_reselect = self.redo_targets.pop()
            self.undo_targets.append(target_to_reselect)
            
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
            ns, _ = iid.rsplit('___', 1)
            
            if self.ns_tree.exists(ns) and (not self.ns_tree.selection() or self.ns_tree.selection()[0] != ns):
                self.ns_tree.selection_set(ns)
                self.ns_tree.focus(ns)
                self.ns_tree.see(ns)
                self._populate_item_list()
            
            if self.trans_tree.exists(iid):
                self.trans_tree.selection_set(iid)
                self.trans_tree.focus(iid)
                self.trans_tree.see(iid)
        except Exception as e:
            logging.warning(f"在撤销/重做后尝试自动选择条目 '{iid}' 时出错: {e}")
    
    def _full_ui_refresh(self, target_to_select: str | None = None):
        self._save_current_edit(record_undo=False) 
        
        selected_ns = self.ns_tree.selection()[0] if self.ns_tree.selection() else None
        
        self._populate_namespace_tree()
        
        if selected_ns and self.ns_tree.exists(selected_ns):
            self.ns_tree.selection_set(selected_ns)
        
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
            self.sort_reverse = False
        
        items.sort(key=lambda t: t[1], reverse=self.sort_reverse)
        
        for index, (k, v) in enumerate(items):
            self.ns_tree.move(k, '', index)
    
    def _setup_treeview_tags(self):
        source_colors = { "个人词典[Key]": "#4a037b", "个人词典[原文]": "#4a037b", "模组自带": "#006400", "第三方汉化包": "#008080", "社区词典[Key]": "#00008b", "社区词典[原文]": "#00008b", "待翻译": "#b22222", "AI翻译": "#008b8b", "手动校对": "#0000cd" }
        for source, color in source_colors.items(): self.trans_tree.tag_configure(source, foreground=color)
        self.trans_tree.tag_configure("手动校对", font=('Microsoft YaHei UI', 9, 'bold'))

    def _populate_namespace_tree(self):
        self.ns_tree.delete(*self.ns_tree.get_children())
        for ns, data in sorted(self.translation_data.items()):
            items = data.get('items', [])
            if not items: continue
            
            untranslated_count = sum(1 for item in items if not item.get('zh', '').strip())
            total_count = len(items)
            completed_count = total_count - untranslated_count
            
            display_text = f"{ns} ({data.get('jar_name', 'Unknown')})"
            self.ns_tree.insert("", "end", iid=ns, text=display_text, values=(untranslated_count, completed_count))

    def _update_namespace_summary(self, ns: str):
        if not self.ns_tree.exists(ns): return
        items = self.translation_data[ns].get('items', [])
        untranslated_count = sum(1 for item in items if not item.get('zh', '').strip())
        completed_count = len(items) - untranslated_count
        self.ns_tree.set(ns, "pending", untranslated_count)
        self.ns_tree.set(ns, "completed", completed_count)

    def _populate_item_list(self):
        self.trans_tree.delete(*self.trans_tree.get_children())
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]): return
        ns = selection[0]
        for idx, item_data in enumerate(self.translation_data.get(ns, {}).get('items', [])):
            source = item_data.get('source', '')
            self.trans_tree.insert("", "end", iid=f"{ns}___{idx}",
                                   values=(item_data['key'], item_data['en'], item_data.get('zh', ''), source),
                                   tags=(source,))

    def _on_namespace_selected(self, event=None):
        self._save_current_edit()
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]): return
        
        self.current_selection_info = None
        self._populate_item_list()
        self._clear_editor()
        self._update_ui_state(interactive=True, item_selected=False)
        self.status_label.config(text=f"已选择模组: {selection[0]}")

    def _on_item_selected(self, event=None):
        self._save_current_edit()
        selection = self.trans_tree.selection()
        if not selection: return

        row_id = selection[0]
        try: ns, idx_str = row_id.rsplit('___', 1); idx = int(idx_str)
        except ValueError: return
        
        self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': row_id}
        item_data = self.translation_data[ns]['items'][idx]
        
        self.zh_text_input.edit_modified(False)
        self._set_editor_content(item_data['en'], item_data.get('zh', ''))
        self.zh_text_input.edit_modified(False)
        self._update_ui_state(interactive=True, item_selected=True)
        self.status_label.config(text=f"正在编辑: {ns} / {item_data['key']}")
        self.zh_text_input.focus_set()

    def _on_text_modified(self, event=None):
        if self.zh_text_input.edit_modified():
            self._save_current_edit()
            self.zh_text_input.edit_modified(False)
            
    def _save_current_edit(self, record_undo=True):
        if not self.current_selection_info: return
        info = self.current_selection_info
        new_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        item = self.translation_data[info['ns']]['items'][info['idx']]
        
        original_zh = item.get('zh', '').strip()
        if original_zh == new_zh_text: return

        self._set_dirty(True)
        item['zh'] = new_zh_text
        is_now_pending = not new_zh_text
        
        new_source = '手动校对' if not is_now_pending else '待翻译'
        item['source'] = new_source
        
        if record_undo:
            self._record_action(target_iid=info['row_id'])

        self.trans_tree.item(info['row_id'], values=(item['key'], item['en'], item['zh'], new_source), tags=(new_source,))
        self._update_namespace_summary(info['ns'])

    def _set_dirty(self, is_dirty: bool):
        self.is_dirty = is_dirty
        title = self.base_title
        
        file_name = f" - {Path(self.current_project_path).name}" if self.current_project_path else ""
        dirty_marker = "*" if self.is_dirty else ""
        
        self.title(f"{title}{file_name}{dirty_marker}")

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
            messagebox.showerror("保存失败", f"保存项目文件时出错：\n{e}")
            return False

    def _save_project(self) -> bool:
        path_to_save = self.current_project_path
        if not path_to_save:
            path_to_save = filedialog.asksaveasfilename(
                title="保存项目", 
                defaultextension=".sav", 
                filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json")]
            )
            if not path_to_save: 
                return False
        
        return self._perform_save(path_to_save)

    def _on_close_request(self):
        self.unbind_all("<Control-z>")
        self.unbind_all("<Control-y>")
        
        self._save_current_edit()

        if self.is_dirty:
            response = messagebox.askyesnocancel(
                "保存更改?", 
                f"项目有未保存的更改，是否要保存？",
                parent=self
            )
            if response is True:
                if self._save_project():
                    self.final_translations = None
                    self.destroy()
            elif response is False:
                self.final_translations = None
                self.destroy()
            else:
                self.bind_all("<Control-z>", self._undo)
                self.bind_all("<Control-y>", self._redo)
                return
        else:
            self.final_translations = None
            self.destroy()
            
    def _save_and_jump_sequential(self, event=None):
        self._save_and_jump(lambda items, current_id: items[(items.index(current_id) + 1) % len(items)])
        return "break"

    def _save_and_jump_pending(self, event=None):
        def find_next_pending(items, current_id):
            start_index = items.index(current_id)
            for row_id in items[start_index+1:] + items[:start_index+1]:
                ns, idx_str = row_id.rsplit('___', 1)
                item = self.translation_data[ns]['items'][int(idx_str)]
                if not item.get('zh', '').strip():
                    return row_id
            ui_utils.show_info("恭喜", f"模组 '{self.current_selection_info['ns']}' 中已没有待翻译的条目！", parent=self)
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

    def _update_ui_state(self, interactive: bool, item_selected: bool):
        if interactive:
            base_state = "normal"
            self.ns_tree.config(selectmode="browse")
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

        self.ai_translate_button.config(state=base_state)
        self.save_button.config(state=base_state)
        self.finish_button.config(state=base_state)
        self.cancel_button.config(state=base_state)
        
        if item_selected and interactive:
            self.add_to_dict_btn.config(state="normal")
            self.zh_text_input.config(state="normal", cursor="xterm")
        else:
            self.add_to_dict_btn.config(state="disabled")
            self.zh_text_input.config(state="disabled", cursor="")

    def _clear_editor(self):
        self._set_editor_content("", "")
        
    def _set_editor_content(self, en_text: str, zh_text: str):
        self.en_text_display.config(state="normal"); self.en_text_display.delete("1.0", "end"); self.en_text_display.insert("1.0", en_text); self.en_text_display.config(state="disabled")
        self.zh_text_input.config(state="normal"); self.zh_text_input.delete("1.0", "end"); self.zh_text_input.insert("1.0", zh_text)

    def _add_to_user_dictionary(self):
        if not self.current_selection_info: return
        info = self.current_selection_info; item_data = self.translation_data[info['ns']]['items'][info['idx']]
        key, origin_name = item_data['key'], item_data['en']
        translation = self.zh_text_input.get("1.0", "end-1c").strip()
        if not translation:
            messagebox.showwarning("操作无效", "译文不能为空！", parent=self); return
        save_by_key = messagebox.askyesnocancel("选择保存模式", f"如何保存这条翻译？\n\n- [是] 按“Key”保存 (最高优先级)\n- [否] 按“原文”保存 (较高优先级)\n- [取消] 不执行任何操作", parent=self)
        if save_by_key is None: return
        user_dict = config_manager.load_user_dict()
        if save_by_key: user_dict["by_key"][key] = translation; mode_str = f"Key: {key}"
        else: user_dict["by_origin_name"][origin_name] = translation; mode_str = f"原文: {origin_name}"
        config_manager.save_user_dict(user_dict)
        self.status_label.config(text=f"成功！已将“{translation}”存入个人词典 ({mode_str})")
        self._set_dirty(True)

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        initial_query = ""
        if self.current_selection_info:
            item_data = self.translation_data[self.current_selection_info['ns']]['items'][self.current_selection_info['idx']]
            initial_query = item_data['en']
        DictionarySearchWindow(self, initial_query=initial_query)
        
    def _run_ai_translation_async(self):
        self._save_current_edit()
        self._update_ui_state(interactive=False, item_selected=False)
        self.status_label.config(text="正在准备AI翻译...")
        self.log_callback("正在准备AI翻译...", "INFO")
        threading.Thread(target=self._ai_translation_worker, daemon=True).start()

    def _ai_translation_worker(self):
        try:
            items_to_translate_info = [{'ns': ns, 'idx': idx, 'en': item['en']} for ns, data in self.translation_data.items() for idx, item in enumerate(data.get('items', [])) if not item.get('zh', '').strip()]
            if not items_to_translate_info:
                self.after(0, lambda: self.status_label.config(text="没有需要AI翻译的空缺条目。"))
                self.log_callback("没有需要AI翻译的空缺条目。", "INFO"); return
            
            texts_to_translate = [info['en'] for info in items_to_translate_info]
            s = self.current_settings
            translator = GeminiTranslator(s['api_keys'], s.get('api_endpoint'))
            batches = [texts_to_translate[i:i + s['ai_batch_size']] for i in range(0, len(texts_to_translate), s['ai_batch_size'])]
            total_batches, translations_nested = len(batches), [None] * len(batches)
            
            with ThreadPoolExecutor(max_workers=s['ai_max_threads']) as executor:
                future_map = {executor.submit(translator.translate_batch, (i, batch, s['model'], s['prompt'])): i for i, batch in enumerate(batches)}
                for i, future in enumerate(as_completed(future_map), 1):
                    batch_idx = future_map[future]
                    translations_nested[batch_idx] = future.result()
                    msg = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    self.after(0, lambda m=msg: self.status_label.config(text=m)); self.log_callback(msg, "INFO")
            
            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            if len(translations) != len(texts_to_translate): raise ValueError(f"AI返回数量不匹配! 预期:{len(texts_to_translate)}, 实际:{len(translations)}")
            self.after(0, self._update_ui_after_ai, items_to_translate_info, translations)
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("AI翻译失败", f"执行AI翻译时发生错误:\n{e}", parent=self)); self.log_callback(f"AI翻译失败: {e}", "ERROR")
        finally:
            try:
                if self.winfo_exists():
                    self.after(0, self._update_ui_state, True, bool(self.current_selection_info))
            except tk.TclError:
                pass

    def _is_valid_translation(self, text: str | None) -> bool:
        if not text or not text.strip():
            return False
        if re.search(r'[\u4e00-\u9fff]', text):
            return True
        if re.search(r'[a-zA-Z]', text):
            return False
        return True

    def _update_ui_after_ai(self, translated_info, translations):
        valid_translation_count = 0
        for info, translation in zip(translated_info, translations):
            if self._is_valid_translation(translation):
                item = self.translation_data[info['ns']]['items'][info['idx']]
                item['zh'] = translation
                item['source'] = 'AI翻译'
                valid_translation_count += 1
            else:
                logging.warning(f"AI为 '{info['en']}' 返回的译文 '{translation}' 无效，已忽略。")
        
        self._record_action(target_iid=None)
        self._set_dirty(True)
        total_returned = len(translations)
        msg = f"AI翻译完成！共收到 {total_returned} 条结果，其中 {valid_translation_count} 条为有效译文。"
        self.status_label.config(text=msg)
        self.log_callback(msg, "SUCCESS")
        
        self._populate_namespace_tree()
        self._populate_item_list()
        self._clear_editor()
        self.current_selection_info = None
        self._update_ui_state(interactive=True, item_selected=False)

    def _on_finish(self):
        self._save_current_edit()
        final_lookup = defaultdict(dict)
        latest_data = self.undo_stack[-1] if self.undo_stack else self.translation_data
        for ns, data in latest_data.items():
            for item in data.get('items', []):
                if item.get('zh', '').strip():
                    final_lookup[ns][item['key']] = item['zh']
        
        self.final_translations = dict(final_lookup)
        self.destroy()