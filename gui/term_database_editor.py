import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as ttkb
from core.term_database import TermDatabase
from gui import ui_utils
import threading
import time

class TermDatabaseEditor(ttkb.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("术语库编辑器")
        self.geometry("800x600")
        self.minsize(600, 400)
        self.transient(parent)
        self.grab_set()
        
        # 初始化术语库
        self.term_db = TermDatabase()
        
        # 当前选中的术语
        self.selected_term = None
        self.current_term_translations = []
        
        # 创建主布局
        self._create_widgets()
        
        # 填充术语列表
        self._refresh_term_list()
        
        # 绑定事件
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """
        创建界面组件
        """
        # 主容器
        main_container = ttkb.Frame(self, padding=10)
        main_container.pack(fill="both", expand=True)
        
        # 顶部工具栏
        toolbar = ttkb.Frame(main_container)
        toolbar.pack(fill="x", pady=(0, 10))
        
        # 搜索框
        search_frame = ttkb.Frame(toolbar)
        search_frame.pack(side="left", fill="x", expand=True)
        
        ttkb.Label(search_frame, text="搜索:").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttkb.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        search_entry.bind("<Return>", lambda e: self._refresh_term_list())
        
        # 领域选择
        ttkb.Label(search_frame, text="领域:").pack(side="left", padx=(10, 5))
        self.domain_var = tk.StringVar(value="all")
        self.domain_combobox = ttkb.Combobox(search_frame, textvariable=self.domain_var, state="readonly")
        self.domain_combobox.pack(side="left", padx=(0, 10))
        self.domain_combobox.bind("<<ComboboxSelected>>", lambda e: self._refresh_term_list())
        
        # 搜索按钮
        ttkb.Button(search_frame, text="搜索", command=self._refresh_term_list, bootstyle="primary-outline").pack(side="left")
        
        # 导入导出按钮
        import_btn = ttkb.Button(toolbar, text="导入CSV", command=self._import_terms, bootstyle="success-outline")
        import_btn.pack(side="right", padx=(0, 5))
        
        export_btn = ttkb.Button(toolbar, text="导出CSV", command=self._export_terms, bootstyle="info-outline")
        export_btn.pack(side="right")
        
        # 主内容区域
        content_frame = ttkb.PanedWindow(main_container, orient="horizontal")
        content_frame.pack(fill="both", expand=True)
        
        # 术语列表区域
        list_frame = ttkb.Frame(content_frame, padding=5)
        content_frame.add(list_frame, weight=1)
        
        # 术语列表
        list_label_frame = ttkb.LabelFrame(list_frame, text="术语列表", padding=5)
        list_label_frame.pack(fill="both", expand=True)
        
        # 列表控件
        self.term_listbox = tk.Listbox(list_label_frame, selectmode="single", height=20, width=60)
        self.term_listbox.pack(side="left", fill="both", expand=True)
        
        # 初始化列表为空，延迟加载
        self.term_listbox.terms = []
        
        # 滚动条
        scrollbar = ttkb.Scrollbar(list_label_frame, orient="vertical", command=self.term_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        
        # 添加水平滚动条
        hscrollbar = ttkb.Scrollbar(list_label_frame, orient="horizontal", command=self.term_listbox.xview)
        hscrollbar.pack(side="bottom", fill="x")
        
        self.term_listbox.config(yscrollcommand=scrollbar.set, xscrollcommand=hscrollbar.set)
        
        # 绑定列表选择事件
        self.term_listbox.bind("<<ListboxSelect>>", self._on_term_select)
        
        # 列表操作按钮
        list_buttons_frame = ttkb.Frame(list_frame, padding=5)
        list_buttons_frame.pack(fill="x")
        
        ttkb.Button(list_buttons_frame, text="添加术语", command=self._add_term, bootstyle="success").pack(side="left", padx=(0, 5))
        ttkb.Button(list_buttons_frame, text="导入社区词典", command=self._import_community_dictionary, bootstyle="info").pack(side="left", padx=(0, 5))
        ttkb.Button(list_buttons_frame, text="删除术语", command=self._delete_term, bootstyle="danger").pack(side="left")
        
        # 术语编辑区域
        edit_frame = ttkb.Frame(content_frame, padding=5)
        content_frame.add(edit_frame, weight=1)
        
        # 编辑表单
        edit_label_frame = ttkb.LabelFrame(edit_frame, text="术语详情", padding=10)
        edit_label_frame.pack(fill="both", expand=True)
        
        # 原文
        ttkb.Label(edit_label_frame, text="原文:").grid(row=0, column=0, sticky="w", pady=5)
        self.original_var = tk.StringVar()
        ttkb.Entry(edit_label_frame, textvariable=self.original_var).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        
        # 译文
        ttkb.Label(edit_label_frame, text="译文:").grid(row=1, column=0, sticky="w", pady=5)
        self.translation_var = tk.StringVar()
        ttkb.Entry(edit_label_frame, textvariable=self.translation_var).grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        
        # 领域
        ttkb.Label(edit_label_frame, text="领域:").grid(row=2, column=0, sticky="w", pady=5)
        self.edit_domain_var = tk.StringVar(value="general")
        domain_entry = ttkb.Entry(edit_label_frame, textvariable=self.edit_domain_var)
        domain_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
        
        # 注释
        ttkb.Label(edit_label_frame, text="注释:").grid(row=3, column=0, sticky="nw", pady=5)
        self.comment_var = tk.StringVar()
        comment_text = scrolledtext.ScrolledText(edit_label_frame, height=5, wrap="word")
        comment_text.grid(row=3, column=1, sticky="nsew", pady=5, padx=5)
        self.comment_text = comment_text
        
        # 配置编辑表单的列权重
        edit_label_frame.columnconfigure(1, weight=1)
        edit_label_frame.rowconfigure(3, weight=1)
        
        # 编辑操作按钮
        edit_buttons_frame = ttkb.Frame(edit_label_frame, padding=10)
        edit_buttons_frame.grid(row=4, column=0, columnspan=2, sticky="e")
        
        ttkb.Button(edit_buttons_frame, text="保存", command=self._save_term, bootstyle="primary").pack(side="right")
    
    def _refresh_term_list(self):
        """
        刷新术语列表，优化性能
        """
        # 清空列表
        self.term_listbox.delete(0, tk.END)
        
        # 获取搜索关键词和领域
        keyword = self.search_var.get().strip()
        domain = self.domain_var.get()
        
        # 加载所有术语
        if domain == "all":
            terms = self.term_db.get_all_terms()
        else:
            terms = self.term_db.get_all_terms(domain=domain)
        
        # 搜索过滤
        if keyword:
            filtered_terms = []
            keyword_lower = keyword.lower()
            for term in terms:
                if keyword_lower in term["original"].lower() or keyword_lower in term["translation"].lower():
                    filtered_terms.append(term)
            terms = filtered_terms
        
        # 按原文排序
        terms.sort(key=lambda x: x["original"])
        
        # 存储完整的术语列表
        self.term_listbox.terms = terms  
        
        # 限制显示的术语数量，避免UI卡死
        max_display = 5000  # 最多显示5000个术语
        display_terms = terms[:max_display]
        
        # 填充列表
        for term in display_terms:
            translations = ", ".join(term['translation'])
            display_text = f"{term['original']} -> [{translations}] [{term['domain']}]"
            self.term_listbox.insert(tk.END, display_text)
        
        # 如果有更多术语，显示提示
        if len(terms) > max_display:
            self.term_listbox.insert(tk.END, f"... 还有 {len(terms) - max_display} 个术语未显示，请使用搜索过滤")
        
        # 更新领域下拉框
        self._update_domain_combobox()
    
    def _update_domain_combobox(self):
        """
        更新领域下拉框选项
        """
        domains = self.term_db.get_domains()
        self.domain_combobox.config(values=["all"] + domains)
    
    def _on_term_select(self, event):
        """
        术语列表选择事件
        """
        selection = self.term_listbox.curselection()
        if selection:
            index = selection[0]
            if hasattr(self.term_listbox, 'terms') and index < len(self.term_listbox.terms):
                self.selected_term = self.term_listbox.terms[index]
                self._load_term_to_edit_form(self.selected_term)
    
    def _load_term_to_edit_form(self, term):
        """
        将术语加载到编辑表单，支持多译文显示
        """
        self.original_var.set(term["original"])
        
        # 显示第一个译文，或空字符串
        self.translation_var.set(term["translation"][0] if term["translation"] else "")
        
        # 显示所有译文在辅助区域
        self.edit_domain_var.set(term["domain"])
        self.comment_text.delete("1.0", tk.END)
        self.comment_text.insert("1.0", term["comment"])
        
        # 保存当前术语的所有译文
        self.current_term_translations = term["translation"]
    
    def _clear_edit_form(self):
        """
        清空编辑表单
        """
        self.selected_term = None
        self.original_var.set("")
        self.translation_var.set("")
        self.edit_domain_var.set("general")
        self.comment_text.delete("1.0", tk.END)
        self.current_term_translations = []
        # 取消列表选中状态
        self.term_listbox.selection_clear(0, tk.END)
    
    def _add_term(self):
        """
        添加新术语
        """
        self._clear_edit_form()
    
    def _edit_term(self):
        """
        编辑当前选中的术语
        """
        if not self.selected_term:
            messagebox.showwarning("警告", "请先选择一个术语进行编辑")
            return
    
    def _save_term(self):
        """
        保存术语，支持多个译文
        """
        original = self.original_var.get().strip()
        current_translation = self.translation_var.get().strip()
        domain = self.edit_domain_var.get().strip()
        comment = self.comment_text.get("1.0", tk.END).strip()
        
        # 验证输入
        if not original:
            messagebox.showerror("错误", "原文不能为空")
            return
        
        if not current_translation:
            messagebox.showerror("错误", "译文不能为空")
            return
        
        if not domain:
            domain = "general"
        
        if self.selected_term:
            # 更新现有术语
            # 获取所有译文，包括当前输入的译文
            all_translations = self.current_term_translations.copy()
            
            # 检查当前译文是否已存在，不存在则添加
            if current_translation not in all_translations:
                all_translations.append(current_translation)
            
            # 更新术语
            self.term_db.update_term(
                self.selected_term["id"],
                original=original,
                translation=all_translations,
                domain=domain,
                comment=comment
            )
            messagebox.showinfo("成功", "术语更新成功")
        else:
            # 添加新术语
            self.term_db.add_term(original, current_translation, domain, comment)
            messagebox.showinfo("成功", "术语添加成功")
        
        # 刷新列表
        self._refresh_term_list()
        self._clear_edit_form()
    
    def _delete_term(self):
        """
        删除当前选中的术语
        """
        selection = self.term_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个术语进行删除")
            return
        
        index = selection[0]
        if hasattr(self.term_listbox, 'terms') and index < len(self.term_listbox.terms):
            term = self.term_listbox.terms[index]
            result = messagebox.askyesno("确认删除", f"确定要删除术语 '{term['original']}' 吗？")
            if result:
                self.term_db.delete_term(term["id"])
                self._refresh_term_list()
                self._clear_edit_form()
                messagebox.showinfo("成功", "术语删除成功")
    
    def _import_terms(self):
        """
        从CSV文件导入术语
        """
        file_path = filedialog.askopenfilename(
            title="选择CSV文件",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        
        if file_path:
            count = self.term_db.import_terms_from_csv(file_path)
            messagebox.showinfo("导入完成", f"成功导入 {count} 个术语")
            self._refresh_term_list()
    
    def _export_terms(self):
        """
        将术语导出为CSV文件
        """
        file_path = filedialog.asksaveasfilename(
            title="保存CSV文件",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        
        if file_path:
            success = self.term_db.export_terms_to_csv(file_path)
            if success:
                messagebox.showinfo("导出完成", "术语导出成功")
            else:
                messagebox.showerror("导出失败", "术语导出失败")
    
    def _import_community_dictionary(self):
        """
        从社区词典导入术语
        """
        from utils.config_manager import load_config
        import sqlite3
        
        # 获取配置
        config = load_config()
        dict_path = config.get("community_dict_path", "")
        
        if not dict_path:
            messagebox.showwarning("警告", "请先在设置中配置社区词典路径")
            return
        
        # 先获取条目数量，用于显示确认对话框
        try:
            conn = sqlite3.connect(dict_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dict")
            total_entries = cursor.fetchone()[0]
            conn.close()
            
            if total_entries == 0:
                messagebox.showinfo("提示", "社区词典中没有找到条目")
                return
            
            # 显示导入确认
            result = messagebox.askyesno(
                "确认导入", 
                f"发现 {total_entries} 个社区词典条目，是否导入到术语库？"
            )
            
            if not result:
                return
            
            # 创建进度对话框
            progress_dialog = ProgressDialog(self, "导入社区词典", total_entries)
            
            # 定义导入线程函数
            def import_thread_func():
                try:
                    # 重新连接数据库获取所有条目
                    conn = sqlite3.connect(dict_path)
                    conn.row_factory = sqlite3.Row
                    
                    # 获取所有条目
                    sql = "SELECT KEY, ORIGIN_NAME, TRANS_NAME, VERSION FROM dict"
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    
                    # 获取现有术语，用于去重
                    existing_terms = self.term_db.get_all_terms()
                    existing_originals = {term["original"] for term in existing_terms}
                    
                    # 获取过滤配置
                    filter_config = config.get("community_dict_filter", {
                        "max_word_count": 0,
                        "require_chinese_translation": True
                    })
                    max_word_count = filter_config.get("max_word_count", 0)
                    require_chinese = filter_config.get("require_chinese_translation", True)
                    
                    import_count = 0
                    skipped_count = 0
                    filtered_count = 0
                    batch_terms = []
                    
                    # 检查译文是否包含中文
                    def has_chinese(text):
                        for char in text:
                            if '\u4e00' <= char <= '\u9fff':
                                return True
                        return False
                    
                    # 逐条处理，实时更新进度
                    for i, row in enumerate(cursor.fetchall()):
                        entry = dict(row)
                        original = entry.get("ORIGIN_NAME", "") or entry.get("KEY", "")
                        translation = entry.get("TRANS_NAME", "")
                        
                        # 过滤条件检查
                        skip = False
                        
                        # 1. 检查原文是否超过最大单词数限制（0表示不限制）
                        word_count = len(original.split())
                        if max_word_count > 0 and word_count > max_word_count:
                            skip = True
                            filtered_count += 1
                        
                        # 2. 检查译文是否包含中文（如果需要）
                        elif require_chinese and not has_chinese(translation):
                            skip = True
                            filtered_count += 1
                        
                        # 3. 检查是否已存在
                        elif original in existing_originals:
                            skip = True
                            skipped_count += 1
                        
                        # 4. 基本验证
                        elif not original or not translation:
                            skip = True
                            skipped_count += 1
                        
                        if not skip:
                            # 收集到批量列表中，不立即保存
                            batch_terms.append({
                                "original": original,
                                "translation": translation,
                                "domain": "community",
                                "comment": f"从社区词典导入，版本: {entry.get('VERSION', '未知')}"
                            })
                            import_count += 1
                            existing_originals.add(original)
                        
                        # 每处理10条更新一次进度，避免过于频繁的UI更新
                        if i % 10 == 0 or i == total_entries - 1:
                            progress_dialog.update_progress(
                                i + 1, 
                                total_entries, 
                                f"已处理 {i + 1}/{total_entries} 条，导入 {import_count} 条，跳过 {skipped_count} 条，过滤 {filtered_count} 条"
                            )
                    
                    conn.close()
                    
                    # 使用批量添加方法，减少文件写入次数
                    if batch_terms:
                        self.term_db.add_terms_batch(batch_terms)
                    
                    # 导入完成，刷新UI并显示结果
                    self.after(0, lambda: progress_dialog.close())
                    self.after(0, self._refresh_term_list)
                    self.after(0, self._clear_edit_form)
                    # 通知所有TermDatabase实例重新加载术语库
                    self.after(0, lambda: TermDatabase.notify_all_instances())
                    self.after(0, lambda: 
                        messagebox.showinfo("导入完成", f"成功导入 {import_count} 个术语，跳过 {skipped_count} 个重复条目，过滤 {filtered_count} 个不符合条件的条目")
                    )
                    
                except Exception as e:
                    # 处理异常
                    error_msg = f"导入社区词典时发生错误: {str(e)}"
                    self.after(0, lambda: progress_dialog.close())
                    self.after(0, lambda: messagebox.showerror("导入失败", error_msg))
                    import traceback
                    traceback.print_exc()
            
            # 启动导入线程
            import_thread = threading.Thread(target=import_thread_func, daemon=True)
            import_thread.start()
            
        except Exception as e:
            messagebox.showerror("导入失败", f"获取社区词典信息时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _on_close(self):
        """
        关闭窗口
        """
        self.destroy()
    
    def show(self):
        """
        显示窗口
        """
        self.wait_window()

class ProgressDialog(ttkb.Toplevel):
    def __init__(self, parent, title="进度", total=100):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x160")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, False)
        
        # 主容器
        main_frame = ttkb.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        # 标题标签
        self.title_label = ttkb.Label(main_frame, text="正在导入...", font=("Arial", 12, "bold"))
        self.title_label.pack(fill="x", pady=(0, 20))
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttkb.Progressbar(
            main_frame, 
            variable=self.progress_var, 
            maximum=total, 
            bootstyle="primary",
            length=500
        )
        self.progress_bar.pack(fill="x", pady=(0, 15))
        
        # 进度信息
        self.info_var = tk.StringVar(value="准备导入...")
        self.info_label = ttkb.Label(main_frame, textvariable=self.info_var, font=("Arial", 10))
        self.info_label.pack(fill="x")
        
        # 确保窗口显示在中心
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"600x160+{x}+{y}")
    
    def update_progress(self, current, total, message=""):
        """更新进度条"""
        if self.winfo_exists():
            self.progress_var.set(current)
            self.progress_bar.config(maximum=total)
            if message:
                self.info_var.set(message)
            self.update_idletasks()
    
    def close(self):
        """关闭对话框"""
        if self.winfo_exists():
            self.destroy()

# 测试代码
if __name__ == "__main__":
    root = ttkb.Window(themename="litera")
    root.withdraw()
    editor = TermDatabaseEditor(root)
    editor.show()
    root.destroy()