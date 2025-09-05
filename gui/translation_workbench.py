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

from utils import config_manager
from services.gemini_translator import GeminiTranslator
from gui.custom_widgets import ToolTip

class TranslationWorkbench(tk.Toplevel):
    def __init__(self, parent, initial_data: dict, namespace_formats: dict, current_settings: dict, log_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.translation_data = initial_data
        self.namespace_formats = namespace_formats
        self.current_settings = current_settings
        self.log_callback = log_callback or (lambda msg, lvl: None)
        self.final_translations = None
        self.current_selection_info = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_treeview_tags()
        self._populate_namespace_tree()
        self._update_ui_state()

    def _setup_window(self):
        self.title("翻译与校对工作台")
        self.geometry("1200x800")
        self.minsize(1000, 600)
        self.transient(self.parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

    def _create_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        left_frame = ttk.Frame(main_pane, padding=5)
        ttk.Label(left_frame, text="模组列表", bootstyle="primary").pack(anchor="w", pady=(0, 5))
        
        self.ns_tree = ttk.Treeview(left_frame, columns=("pending", "completed"), show="tree headings")
        self.ns_tree.heading("#0", text="模组 (文件名)")
        self.ns_tree.heading("pending", text="待翻译")
        self.ns_tree.heading("completed", text="已翻译")
        self.ns_tree.column("#0", width=220, stretch=True)
        self.ns_tree.column("pending", width=80, stretch=False, anchor="center")
        self.ns_tree.column("completed", width=80, stretch=False, anchor="center")
        
        self.ns_tree.pack(fill="both", expand=True)
        self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
        main_pane.add(left_frame, weight=3)

        right_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
        main_pane.add(right_pane, weight=4)

        table_container = ttk.Frame(right_pane, padding=5)
        table_container.pack(fill="both", expand=True)
        
        self.trans_tree = ttk.Treeview(table_container, columns=("key", "english", "chinese", "source"), show="headings")
        self.trans_tree.heading("key", text="原文Key"); self.trans_tree.column("key", width=200, stretch=False)
        self.trans_tree.heading("english", text="原文"); self.trans_tree.column("english", width=250, stretch=True)
        self.trans_tree.heading("chinese", text="译文"); self.trans_tree.column("chinese", width=250, stretch=True)
        self.trans_tree.heading("source", text="来源"); self.trans_tree.column("source", width=120, stretch=False)
        
        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.trans_tree.pack(fill="both", expand=True)
        self.trans_tree.bind("<<TreeviewSelect>>", self._on_translation_selected)
        right_pane.add(table_container, weight=3)
        
        editor_frame = ttk.LabelFrame(right_pane, text="翻译编辑器", padding=10)
        editor_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(editor_frame, text="原文:", anchor="nw").grid(row=0, column=0, sticky="nw", padx=5, pady=5)
        self.en_text_display = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word", state="disabled", relief="flat", background=self.cget('bg'))
        self.en_text_display.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        zh_header_frame = ttk.Frame(editor_frame)
        zh_header_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=(5,0))
        ttk.Label(zh_header_frame, text="译文:", anchor="nw").pack(side="left")
        self.save_button = ttk.Button(zh_header_frame, text="保存修改", command=self._save_detail_and_update_ui, state="disabled", bootstyle="success-outline")
        self.save_button.pack(side="right")
        ToolTip(self.save_button, "保存对此条目的修改\n\n快捷键:\nEnter: 保存并跳转到下一个条目\nCtrl+Enter: 保存并跳转到下一个待翻译条目")

        self.zh_text_input = scrolledtext.ScrolledText(editor_frame, height=3, wrap="word")
        self.zh_text_input.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.zh_text_input.bind("<Return>", self._save_and_jump_sequential)
        self.zh_text_input.bind("<Control-Return>", self._save_and_jump_pending)

        editor_btn_frame = ttk.Frame(editor_frame)
        editor_btn_frame.grid(row=3, column=1, sticky="e", pady=(5,0))
        
        self.ai_translate_button = ttk.Button(editor_btn_frame, text="🚀 一键 AI 翻译 (空缺项)", command=self._run_ai_translation_async, bootstyle="success-outline")
        self.ai_translate_button.pack(side="left", padx=(0, 10))
        self.add_to_dict_btn = ttk.Button(editor_btn_frame, text="⭐ 存入个人词典", command=self._add_to_user_dictionary, bootstyle="info-outline")
        self.add_to_dict_btn.pack(side="left", padx=(0, 10))
        ttk.Button(editor_btn_frame, text="查询词典", command=self._open_dict_search, bootstyle="info-outline").pack(side="left")
        right_pane.add(editor_frame, weight=1)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        self.status_label = ttk.Label(btn_frame, text="请选择一个模组以开始")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.save_project_button = ttk.Button(btn_frame, text="保存项目...", command=self._save_project, bootstyle="info")
        self.save_project_button.pack(side="left", padx=(0, 20))
        self.finish_button = ttk.Button(btn_frame, text="完成并生成资源包", command=self._on_finish, bootstyle="success")
        self.finish_button.pack(side="right")
        self.cancel_button = ttk.Button(btn_frame, text="取消", command=self._on_close_request, bootstyle="secondary")
        self.cancel_button.pack(side="right", padx=10)

    def _setup_treeview_tags(self):
        source_colors = {
            "个人词典[Key]": "#4a037b", "个人词典[原文]": "#4a037b",
            "模组自带": "#006400", "第三方汉化包": "#008080",
            "社区词典[Key]": "#00008b", "社区词典[原文]": "#00008b",
            "待翻译": "#b22222",
            "AI翻译": "#008b8b",
            "手动校对": "#0000cd",
        }
        for source, color in source_colors.items():
            self.trans_tree.tag_configure(source, foreground=color)
        
        bold_font = ('Microsoft YaHei UI', 9, 'bold')
        self.trans_tree.tag_configure("手动校对", font=bold_font)

    def _set_ui_interactive(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.ai_translate_button.config(state=state)
        self.add_to_dict_btn.config(state=state if self.current_selection_info else "disabled")
        self.save_project_button.config(state=state)
        self.finish_button.config(state=state)
        self.cancel_button.config(state=state)
        self.zh_text_input.config(state=state if self.current_selection_info else "disabled")
        self.save_button.config(state=state if self.current_selection_info else "disabled")
        
        if enabled:
            self.ns_tree.bind("<<TreeviewSelect>>", self._on_namespace_selected)
            self.trans_tree.bind("<<TreeviewSelect>>", self._on_translation_selected)
        else:
            self.ns_tree.unbind("<<TreeviewSelect>>")
            self.trans_tree.unbind("<<TreeviewSelect>>")

    def _add_to_user_dictionary(self):
        if not self.current_selection_info: return
        info = self.current_selection_info
        item_data = self.translation_data[info['ns']]['items'][info['idx']]
        key, origin_name = item_data['key'], item_data['en']
        translation = self.zh_text_input.get("1.0", "end-1c").strip()
        if not translation:
            messagebox.showwarning("操作无效", "译文不能为空！", parent=self)
            return
        save_by_key = messagebox.askyesnocancel("选择保存模式", f"如何保存这条翻译？\n\n- [是] 按“Key”保存 (最高优先级，精确匹配 {key}) \n- [否] 按“原文”保存 (较高优先级，模糊匹配 {origin_name})\n- [取消] 不执行任何操作", parent=self)
        if save_by_key is None: return
        user_dict = config_manager.load_user_dict()
        if save_by_key:
            user_dict["by_key"][key] = translation
            save_mode_str = f"Key: {key}"
        else:
            user_dict["by_origin_name"][origin_name] = translation
            save_mode_str = f"原文: {origin_name}"
        config_manager.save_user_dict(user_dict)
        self.status_label.config(text=f"成功！已将“{translation}”存入个人词典 ({save_mode_str})")

    def _open_dict_search(self):
        from gui.dictionary_search_window import DictionarySearchWindow
        initial_query = ""
        if self.current_selection_info:
            item_data = self.translation_data[self.current_selection_info['ns']]['items'][self.current_selection_info['idx']]
            initial_query = item_data['en']
        DictionarySearchWindow(self, initial_query=initial_query)
        
    def _populate_namespace_tree(self):
        self.ns_tree.delete(*self.ns_tree.get_children())
        
        for ns, data in sorted(self.translation_data.items()):
            items = data.get('items', [])
            if not items: continue

            jar_name = data.get('jar_name', 'Unknown')
            display_text = f"{ns} ({jar_name})"
            
            untranslated_count = sum(1 for item in items if item['source'] == '待翻译')
            completed_count = len(items) - untranslated_count
            
            self.ns_tree.insert("", "end", iid=ns, text=display_text, values=(untranslated_count, completed_count))
        
    def _on_namespace_selected(self, event=None):
        self._force_save_pending_edit()
        
        self.current_selection_info = None
        self.trans_tree.delete(*self.trans_tree.get_children())
        
        selection = self.ns_tree.selection()
        if selection and self.ns_tree.exists(selection[0]):
            self._populate_item_list()
        
        self._update_ui_state()

    def _populate_item_list(self):
        selection = self.ns_tree.selection()
        if not selection or not self.ns_tree.exists(selection[0]):
            return

        ns = selection[0]
        for idx, item_data in enumerate(self.translation_data.get(ns, {}).get('items', [])):
            self.trans_tree.insert("", "end", iid=f"{ns}___{idx}", 
                                   values=(item_data['key'], item_data['en'], item_data.get('zh', ''), item_data.get('source', '')),
                                   tags=(item_data.get('source', ''),))
    
    def _on_translation_selected(self, event=None):
        self._force_save_pending_edit()
        selection = self.trans_tree.selection()
        if not selection: return
        
        row_id = selection[0]
        try: 
            ns, idx_str = row_id.rsplit('___', 1)
            idx = int(idx_str)
        except ValueError: 
            return
            
        self.current_selection_info = {'ns': ns, 'idx': idx, 'row_id': row_id}
        item_data = self.translation_data[ns]['items'][idx]
        
        self.en_text_display.config(state="normal")
        self.en_text_display.delete("1.0", "end")
        self.en_text_display.insert("1.0", item_data['en'])
        self.en_text_display.config(state="disabled")
        
        self.zh_text_input.config(state="normal")
        self.zh_text_input.delete("1.0", "end")
        self.zh_text_input.insert("1.0", item_data.get('zh', ''))
        self._update_ui_state()

    def _force_save_pending_edit(self):
        self._perform_save()

    def _perform_save(self):
        if not self.current_selection_info: return None
        
        new_zh_text = self.zh_text_input.get("1.0", "end-1c").strip()
        info = self.current_selection_info
        item = self.translation_data[info['ns']]['items'][info['idx']]
        
        original_source = item.get('source')

        if item.get('zh', '') != new_zh_text:
            item['zh'] = new_zh_text
            item['source'] = '手动校对'
            
            self.trans_tree.item(info['row_id'], 
                                 values=(item['key'], item['en'], item['zh'], item['source']),
                                 tags=(item['source'],))
            self.status_label.config(text=f"已自动保存编辑: {info['row_id']}")
            
            if original_source == '待翻译':
                ns = info['ns']
                if self.ns_tree.exists(ns):
                    try:
                        current_values = self.ns_tree.item(ns, "values")
                        pending_count = int(current_values[0])
                        completed_count = int(current_values[1])
                        
                        new_pending = max(0, pending_count - 1)
                        new_completed = completed_count + 1
                        
                        self.ns_tree.set(ns, "pending", new_pending)
                        self.ns_tree.set(ns, "completed", new_completed)
                    except (ValueError, IndexError) as e:
                        print(f"Error updating namespace counts for '{ns}': {e}")
            return info['idx']
        return info['idx']

    def _save_detail_and_update_ui(self):
        if self._perform_save() is not None:
            self.save_button.config(text="已保存!", bootstyle="success")
            self.after(1500, lambda: self.save_button.config(text="保存修改", bootstyle="success-outline"))

    def _save_and_jump_sequential(self, event=None):
        saved_index = self._perform_save()
        if saved_index is not None:
            all_items = self.trans_tree.get_children()
            if not all_items: return
            
            try:
                current_tree_index = all_items.index(self.current_selection_info['row_id'])
                next_tree_index = (current_tree_index + 1) % len(all_items)
                next_item_id = all_items[next_tree_index]
                self.trans_tree.selection_set(next_item_id)
                self.trans_tree.focus(next_item_id)
                self.trans_tree.see(next_item_id)
            except ValueError:
                pass
        return "break"

    def _save_and_jump_pending(self, event=None):
        saved_index = self._perform_save()
        if saved_index is not None:
            all_items_data = self.translation_data[self.current_selection_info['ns']]['items']
            current_row_id = self.current_selection_info['row_id']
            
            search_order = list(range(saved_index + 1, len(all_items_data))) + list(range(0, saved_index + 1))
            
            next_pending_id = None
            for i in search_order:
                if all_items_data[i]['source'] == '待翻译':
                    next_pending_id = f"{self.current_selection_info['ns']}___{i}"
                    break
            
            if next_pending_id and next_pending_id != current_row_id:
                self.trans_tree.selection_set(next_pending_id)
                self.trans_tree.focus(next_pending_id)
                self.trans_tree.see(next_pending_id)
            elif not next_pending_id:
                messagebox.showinfo("恭喜", f"模组 '{self.current_selection_info['ns']}' 中已没有待翻译的条目！", parent=self)
                
        return "break"

    def _update_ui_state(self):
        is_item_selected = bool(self.current_selection_info)
        self.add_to_dict_btn.config(state="normal" if is_item_selected else "disabled")
        self.save_button.config(state="normal" if is_item_selected else "disabled")

        if is_item_selected:
            self.status_label.config(text=f"正在编辑: {self.current_selection_info['row_id']}")
            self.zh_text_input.config(state="normal")
        else:
            self.en_text_display.config(state="normal")
            self.en_text_display.delete("1.0", "end")
            self.en_text_display.config(state="disabled")
            
            self.zh_text_input.config(state="normal")
            self.zh_text_input.delete("1.0", "end")
            self.zh_text_input.config(state="disabled")
            
            self.status_label.config(text="请选择一个模组以查看条目")
    
    def _get_full_save_data(self) -> dict:
        return {
            "version": "2.1", 
            "timestamp": datetime.now().isoformat(), 
            "settings_snapshot": {
                "mods_dir": self.current_settings.get("mods_dir"), 
                "output_dir": self.current_settings.get("output_dir")
            }, 
            "pack_settings": self.current_settings.get("pack_settings"), 
            "workbench_data": self.translation_data, 
            "namespace_formats": self.namespace_formats
        }

    def _save_project(self) -> bool:
        self._force_save_pending_edit()
        save_path = filedialog.asksaveasfilename(title="保存翻译项目", defaultextension=".sav", filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json")])
        if not save_path: return False
        try:
            with open(save_path, 'w', encoding='utf-8') as f: 
                json.dump(self._get_full_save_data(), f, indent=4, ensure_ascii=False)
            self.status_label.config(text=f"项目已成功保存到: {Path(save_path).name}")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"保存项目文件时出错：\n{e}")
            return False
    
    def _run_ai_translation_async(self):
        self._force_save_pending_edit()
        self._set_ui_interactive(False)
        self.status_label.config(text="正在准备AI翻译...")
        self.log_callback("正在准备AI翻译...", "INFO")
        threading.Thread(target=self._ai_translation_worker, daemon=True).start()

    def _ai_translation_worker(self):
        try:
            items_to_translate_info = [{'ns': ns, 'idx': idx, 'en': item_data['en']} for ns, data in self.translation_data.items() for idx, item_data in enumerate(data.get('items', [])) if not item_data.get('zh', '').strip()]
            if not items_to_translate_info:
                self.after(0, lambda: self.status_label.config(text="没有需要AI翻译的空缺条目。"))
                self.log_callback("没有需要AI翻译的空缺条目。", "INFO")
                return
            
            texts_to_translate = [info['en'] for info in items_to_translate_info]
            translator = GeminiTranslator(self.current_settings['api_keys'], self.current_settings.get('api_endpoint'))
            batch_size = self.current_settings.get('ai_batch_size', 50)
            max_retries = self.current_settings.get('ai_max_retries', 3)
            retry_interval = self.current_settings.get('ai_retry_interval', 2)
            use_grounding = self.current_settings.get('use_grounding', False)

            text_batches = [texts_to_translate[i:i + batch_size] for i in range(0, len(texts_to_translate), batch_size)]
            total_batches, translations_nested = len(text_batches), [None] * len(text_batches)
            
            with ThreadPoolExecutor(max_workers=self.current_settings.get('ai_max_threads', 4)) as executor:
                future_to_batch_index = {
                    executor.submit(
                        translator.translate_batch, 
                        (i, batch, self.current_settings['model'], self.current_settings['prompt'], max_retries, retry_interval, use_grounding)
                    ): i 
                    for i, batch in enumerate(text_batches)
                }
                for i, future in enumerate(as_completed(future_to_batch_index), 1):
                    batch_index = future_to_batch_index[future]
                    translations_nested[batch_index] = future.result()
                    status_msg = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    self.after(0, lambda msg=status_msg: self.status_label.config(text=msg))
                    self.log_callback(status_msg, "INFO")

            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            if len(translations) != len(texts_to_translate): 
                raise ValueError(f"AI返回数量不匹配! 预期:{len(texts_to_translate)}, 实际:{len(translations)}")
            self.after(0, self._update_ui_after_ai, items_to_translate_info, translations)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("AI翻译失败", f"执行AI翻译时发生错误:\n{e}", parent=self))
            self.log_callback(f"AI翻译失败: {e}", "ERROR")
        finally:
            self.after(0, self._set_ui_interactive, True)
            self.after(0, self._update_ui_state)

    def _update_ui_after_ai(self, translated_info, translations):
        for info, translation in zip(translated_info, translations):
            item = self.translation_data[info['ns']]['items'][info['idx']]
            item['zh'] = translation
            item['source'] = 'AI翻译'
        
        final_msg = f"AI翻译完成！共处理了 {len(translations)} 个条目。"
        self.status_label.config(text=final_msg)
        self.log_callback(final_msg, "SUCCESS")
        self._populate_namespace_tree()
        self._populate_item_list()

    def _on_finish(self):
        self._force_save_pending_edit()
        final_lookup = defaultdict(dict)
        for ns, data in self.translation_data.items():
            for item in data.get('items', []):
                if item.get('zh', '').strip():
                    final_lookup[ns][item['key']] = item['zh']
        
        self.final_translations = dict(final_lookup)
        self.destroy()
        
    def _on_close_request(self):
        self._force_save_pending_edit()
        response = messagebox.askyesnocancel("确认关闭", "您确定要关闭翻译工作台吗？\n\n- “是”：不保存并关闭\n- “否”：保存项目后关闭\n- “取消”：返回工作台", parent=self, icon=messagebox.QUESTION)
        
        if response is True:
            self.final_translations = None
            self.destroy()
        elif response is False:
            if self._save_project():
                self.final_translations = None
                self.destroy()