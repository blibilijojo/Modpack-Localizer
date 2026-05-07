from __future__ import annotations
import logging
import json
import threading
from pathlib import Path
import tkinter as tk
import ttkbootstrap as ttk
from utils import config_manager
from services.ai_translator import AITranslator
from services.punctuation_corrector import punctuation_corrector


class WorkbenchAIMixin:
    """AI translation, terms, import/export functionality mixin for TranslationWorkbench."""

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
            
            # 忽略 _comment 键值的条目
            if key == '_comment' or (key and key.startswith('_comment_')):
                skipped_count += 1
                continue
            
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
                        # 获取原文和当前译文
                        en_text = item.get('en', '').strip()
                        current_zh = item.get('zh', '').strip()
                        
                        # 如果导入的文本与当前译文相同，跳过
                        if zh == current_zh:
                            skipped_count += 1
                            found = True
                            break
                        
                        # 如果导入的文本与原文相同，跳过
                        if zh == en_text:
                            skipped_count += 1
                            found = True
                            break
                        
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
                community_dict_dir = config.get("community_dict_dir", "")
                
                if community_dict_dir:
                    community_dict_path = str(Path(community_dict_dir) / "Dict-Sqlite.db")
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
            
            items_to_translate_info = [
                {
                    'ns': ns,
                    'idx': idx,
                    'en': item['en'],
                    'key': item.get('key', '')
                }
                for ns, data in self.translation_data.items()
                for idx, item in enumerate(data.get('items', []))
                if not item.get('zh', '').strip() and item.get('en', '').strip()
            ]
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
            
            translation_inputs = [
                {"text": info['en'], "key": info.get('key', '')}
                for info in items_to_translate_info
            ]
            # 每次翻译时都从配置文件加载最新设置
            import utils.config_manager
            s = utils.config_manager.load_config()
            translator = AITranslator(s.get('api_services', []), disable_cooldown=s.get('disable_key_cooldown', False))
            # 保存当前翻译器实例
            self._current_translator = translator
            
            # 检查取消标志
            if self._ai_translation_cancelled:
                self.log_callback("AI翻译已取消，停止执行", "INFO")
                return
            
            # 分批次处理文本
            batches = [translation_inputs[i:i + s['ai_batch_size']] for i in range(0, len(translation_inputs), s['ai_batch_size'])]
            total_batches, translations_nested = len(batches), [None] * len(batches)
            
            # 创建并保存AI翻译线程池
            from concurrent.futures import ThreadPoolExecutor
            self._current_ai_executor = ThreadPoolExecutor(max_workers=s['ai_max_threads'])
            try:
                future_map = {
                    self._current_ai_executor.submit(
                        translator.translate_batch,
                        (i, batch, s['model'], utils.config_manager.DEFAULT_PROMPT.strip())
                    ): i
                    for i, batch in enumerate(batches)
                }
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
            
            if len(translations) != len(translation_inputs): raise ValueError(f"AI返回数量不匹配! 预期:{len(translation_inputs)}, 实际:{len(translations)}")
            
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
        for ns, data in self.translation_data.items():
            for item in data.get('items', []):
                if item.get('zh', '').strip():
                    final_lookup[ns][item['key']] = item['zh']
        
        final_translations = dict(final_lookup)
        if self.finish_callback:
            self.status_label.config(text="正在处理，请稍候...")
            try:
                self.finish_callback(final_translations, self.translation_data)
            except Exception as e:
                logging.error(f"完成回调执行失败: {e}", exc_info=True)
                self.status_label.config(text=f"处理失败: {e}")
                if self.log_callback:
                    self.log_callback(f"完成回调执行失败: {e}", "CRITICAL")

    def _deduplicate_translations(self, translation_data: dict) -> dict:
        """对翻译数据进行去重处理，移除重复的译文

        Args:
            translation_data: 原始翻译数据

        Returns:
            dict: 去重后的翻译数据
        """
        import copy

        result = copy.deepcopy(translation_data)
        total_removed = 0

        for ns, data in result.items():
            items = data.get('items', [])
            if not items:
                continue

            seen_translations = {}  # {原文：译文}
            unique_items = []
            removed_count = 0

            for item in items:
                en_text = item.get('en', '').strip()
                zh_text = item.get('zh', '').strip()

                if not zh_text:
                    unique_items.append(item)
                    continue

                if en_text in seen_translations:
                    if seen_translations[en_text] == zh_text:
                        removed_count += 1
                        continue
                    else:
                        unique_items.append(item)
                        seen_translations[en_text] = zh_text
                else:
                    seen_translations[en_text] = zh_text
                    unique_items.append(item)

            data['items'] = unique_items
            total_removed += removed_count

            if removed_count > 0:
                logging.info(f"命名空间 '{ns}' 去重：移除 {removed_count} 条重复译文")

        logging.info(f"去重处理完成，共移除 {total_removed} 条重复译文")
        return result

    def _export_current_namespace_json(self):
        """导出当前模组的语言文件为 JSON 格式"""
        self._save_current_edit()
        
        # 检查是否有选中的模组（命名空间树）
        ns_selection = self.ns_tree.selection()
        if not ns_selection:
            messagebox.showwarning("提示", "请先在左侧选择一个模组", parent=self)
            return
        
        current_ns = ns_selection[0]  # 获取选中的命名空间 IID
        
        # 获取当前命名空间的翻译数据
        translations = {}
        ns_data = self.translation_data.get(current_ns, {})
        for item in ns_data.get('items', []):
            zh_translation = item.get('zh', '').strip()
            if zh_translation:
                translations[item['key']] = zh_translation
        
        # 获取原始英文文件内容
        template_content = self.raw_english_files.get(current_ns, '{}')
        
        # 确定文件格式
        if ":" in current_ns:
            base_namespace, file_format = current_ns.split(":", 1)
        else:
            base_namespace = current_ns
            file_format = 'json'  # 默认为 json 格式
        
        if file_format != 'json':
            messagebox.showwarning("不支持的格式", f"当前命名空间 {current_ns} 的格式为 {file_format}，暂不支持导出", parent=self)
            return
        
        # 使用 builder 的方法生成 JSON 文件
        from core.builder import Builder
        builder = Builder()
        output_content = builder._build_json_file(template_content, translations)
        
        # 选择保存路径
        default_filename = f"{base_namespace}_zh_cn.json"
        file_path = filedialog.asksaveasfilename(
            title="导出 JSON",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(output_content)
            
            messagebox.showinfo(
                "导出成功", 
                f"已成功导出 {len(translations)} 条翻译记录到:\n{file_path}",
                parent=self
            )
            logging.info(f"成功导出命名空间 {current_ns} 的 JSON 文件到 {file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"导出 JSON 文件时出错：\n{e}", parent=self)
            logging.error(f"导出 JSON 失败：{e}")

    def _import_current_namespace_json(self):
        """从 JSON 文件导入翻译到当前模组"""
        self._save_current_edit()
        
        # 检查是否有选中的模组（命名空间树）
        ns_selection = self.ns_tree.selection()
        if not ns_selection:
            messagebox.showwarning("提示", "请先在左侧选择一个模组", parent=self)
            return
        
        current_ns = ns_selection[0]  # 获取选中的命名空间 IID
        
        # 确定文件格式
        if ":" in current_ns:
            base_namespace, file_format = current_ns.split(":", 1)
        else:
            base_namespace = current_ns
            file_format = 'json'  # 默认为 json 格式
        
        if file_format != 'json':
            messagebox.showwarning("不支持的格式", f"当前命名空间 {current_ns} 的格式为 {file_format}，暂不支持导入", parent=self)
            return
        
        # 选择要导入的 JSON 文件
        file_path = filedialog.askopenfilename(
            title="导入 JSON",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # 使用正则表达式解析 JSON 文件，避免 json.load() 自动转义
            import_data = {}
            JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
            for match in JSON_KEY_VALUE_PATTERN.finditer(file_content):
                key = match.group(1)
                value = match.group(2)
                # 处理 Unicode 转义序列（如\u963f），但保留\n等转义字符
                # 先将\n、\t等常见转义字符暂时替换为占位符
                temp_value = value.replace('\\n', '__NEWLINE__')
                temp_value = temp_value.replace('\\t', '__TAB__')
                temp_value = temp_value.replace('\\r', '__CARRIAGE__')
                # 处理 Unicode 转义序列
                temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
                # 恢复占位符为原始转义字符
                temp_value = temp_value.replace('__NEWLINE__', '\\n')
                temp_value = temp_value.replace('__TAB__', '\\t')
                temp_value = temp_value.replace('__CARRIAGE__', '\\r')
                # 处理引号，将 \" 替换为 "
                temp_value = temp_value.replace('\\"', '"')
                # 处理 _comment 条目，为每个 _comment 添加序号
                if key == '_comment':
                    continue  # 跳过 _comment 键
                else:
                    import_data[key] = temp_value
            
            # 验证导入数据格式
            if not isinstance(import_data, dict):
                messagebox.showerror("导入失败", "导入数据格式不正确，请确保是有效的 JSON 对象。", parent=self)
                return
            
            # 获取当前命名空间的翻译数据
            ns_data = self.translation_data.get(current_ns, {})
            items = ns_data.get('items', [])
            
            # 统计导入结果
            updated_count = 0
            skipped_count = 0
            not_found_count = 0
            
            # 遍历导入的数据，更新翻译
            for key, zh_translation in import_data.items():
                # 忽略 _comment 键值的条目
                if key == '_comment' or key.startswith('_comment_'):
                    continue
                
                if not isinstance(zh_translation, str):
                    continue
                
                zh_translation = zh_translation.strip()
                if not zh_translation:
                    continue
                
                # 查找匹配的条目
                found = False
                for item in items:
                    if item['key'] == key:
                        # 获取原文和当前译文
                        en_text = item.get('en', '').strip()
                        current_zh = item.get('zh', '').strip()
                        
                        # 如果导入的文本与当前译文相同，跳过
                        if zh_translation == current_zh:
                            skipped_count += 1
                            found = True
                            break
                        
                        # 如果导入的文本与原文相同，跳过
                        if zh_translation == en_text:
                            skipped_count += 1
                            found = True
                            break
                        
                        # 更新翻译
                        item['zh'] = zh_translation
                        item['source'] = 'JSON 导入'
                        updated_count += 1
                        found = True
                        break
                
                if not found:
                    not_found_count += 1
            
            # 在修改数据之后，保存当前状态用于撤销/重做
            details = {
                'source': 'file',
                'namespace': current_ns,
                'total_items': len(import_data),
                'file_path': file_path,
                'updated_count': updated_count,
                'not_found_count': not_found_count
            }
            self.record_operation('IMPORT', details, target_iid=None)
            
            # 更新 UI
            self._full_ui_refresh()
            self._set_dirty(True)
            
            # 显示导入结果
            message = f"导入完成！\n"
            message += f"成功更新：{updated_count} 条\n"
            message += f"跳过（译文相同或与原文相同）: {skipped_count} 条\n"
            message += f"未找到匹配项：{not_found_count} 条"
            messagebox.showinfo("导入结果", message, parent=self)
            logging.info(f"成功从 {file_path} 导入 {updated_count} 条翻译到命名空间 {current_ns}")
            
        except json.JSONDecodeError:
            messagebox.showerror("导入失败", "JSON 文件格式不正确，请确保是有效的 JSON 格式。", parent=self)
            logging.error(f"导入 JSON 失败：JSON 格式错误")
        except Exception as e:
            messagebox.showerror("导入失败", f"导入 JSON 文件时出错：\n{e}", parent=self)
            logging.error(f"导入 JSON 失败：{e}")

    def _on_github_upload(self):
        """GitHub 汉化仓库上传按钮点击事件"""
        if not self.type_config.enable_github_upload:
            return

        # 保存当前编辑
        self._save_current_edit()
        
        # 加载 GitHub 配置
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
        # 更新GitHub上传UI中的命名空间和分支（包括版本计算）
        self._github_upload_ui.update_namespace_and_branch(current_namespace)
