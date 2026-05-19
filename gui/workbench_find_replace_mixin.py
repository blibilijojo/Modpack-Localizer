from __future__ import annotations
import logging
import tkinter as tk
import ttkbootstrap as ttk


class WorkbenchFindReplaceMixin:
    """TranslationWorkbench 的查找/替换功能混入类。"""

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
