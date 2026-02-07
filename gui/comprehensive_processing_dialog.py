import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading
from pathlib import Path
import json
import logging

from utils import config_manager
from services.ai_translator import AITranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools

class ComprehensiveProcessingDialog(tk.Toplevel):
    def __init__(self, parent, workbench_instance):
        super().__init__(parent)
        self.workbench = workbench_instance
        self.title("翻译控制台")
        self.geometry("600x450")
        self.transient(parent)
        self.grab_set()
        
        # 初始化变量
        self.processing = False
        
        # 创建主容器
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="翻译控制台", font=("Microsoft YaHei UI", 12, "bold"))
        title_label.pack(anchor="w", pady=(0, 20))
        
        # 1. 选择操作类型
        operation_frame = ttk.LabelFrame(main_frame, text="操作类型", padding="10")
        operation_frame.pack(fill="x", pady=(0, 15))
        
        self.operation_var = tk.StringVar(value="ai_translate")
        
        operations = [
            ("AI翻译", "ai_translate"),
            ("导出文本", "export"),
            ("导入翻译", "import")
        ]
        
        for text, value in operations:
            ttk.Radiobutton(operation_frame, text=text, variable=self.operation_var, value=value, bootstyle="primary").pack(anchor="w", pady=2)
        
        # 2. 选择处理范围
        scope_frame = ttk.LabelFrame(main_frame, text="处理范围", padding="10")
        scope_frame.pack(fill="x", pady=(0, 15))
        
        self.scope_var = tk.StringVar(value="current")
        
        scopes = [
            ("当前模组", "current"),
            ("所有模组", "all")
        ]
        
        for text, value in scopes:
            ttk.Radiobutton(scope_frame, text=text, variable=self.scope_var, value=value, bootstyle="primary").pack(anchor="w", pady=2)
        
        # 3. 选择内容类型
        content_frame = ttk.LabelFrame(main_frame, text="内容类型", padding="10")
        content_frame.pack(fill="x", pady=(0, 15))
        
        self.content_var = tk.StringVar(value="pending")
        
        contents = [
            ("待翻译文本", "pending"),
            ("已翻译文本", "completed"),
            ("所有文本", "all")
        ]
        
        for text, value in contents:
            ttk.Radiobutton(content_frame, text=text, variable=self.content_var, value=value, bootstyle="primary").pack(anchor="w", pady=2)
        
        # 4. 导入选项（仅在导入操作时显示）
        self.import_options_frame = ttk.LabelFrame(main_frame, text="导入选项", padding="10")
        self.import_options_frame.pack(fill="x", pady=(0, 15))
        self.import_options_frame.pack_forget()
        
        self.import_source_var = tk.StringVar(value="file")
        
        import_sources = [
            ("从文件导入", "file"),
            ("从剪贴板导入", "clipboard")
        ]
        
        for text, value in import_sources:
            ttk.Radiobutton(self.import_options_frame, text=text, variable=self.import_source_var, value=value, bootstyle="primary").pack(anchor="w", pady=2)
        
        # 5. AI翻译选项（仅在AI翻译时显示）
        self.ai_options_frame = ttk.LabelFrame(main_frame, text="AI翻译选项", padding="10")
        self.ai_options_frame.pack(fill="x", pady=(0, 15))
        self.ai_options_frame.pack_forget()
        
        # 显示状态
        self.status_var = tk.StringVar(value="准备就绪")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(anchor="w", pady=(0, 15))
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 15))
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", anchor="e")
        
        self.cancel_button = ttk.Button(button_frame, text="取消", command=self._on_cancel, bootstyle="secondary")
        self.cancel_button.pack(side="right", padx=(10, 0))
        
        self.start_button = ttk.Button(button_frame, text="开始处理", command=self._on_start, bootstyle="success")
        self.start_button.pack(side="right")
        
        # 绑定事件
        self.operation_var.trace_add("write", self._on_operation_change)
        
        # 初始化界面
        self._on_operation_change()
        
    def _on_operation_change(self, *args):
        """根据操作类型显示/隐藏相应选项"""
        operation = self.operation_var.get()
        
        # 隐藏所有选项
        self.import_options_frame.pack_forget()
        self.ai_options_frame.pack_forget()
        
        # 根据操作类型显示相应选项
        if operation == "import":
            self.import_options_frame.pack(fill="x", pady=(0, 15))
        elif operation == "ai_translate":
            self.ai_options_frame.pack(fill="x", pady=(0, 15))
        
        self.update_idletasks()
    
    def _on_start(self):
        """开始处理"""
        if self.processing:
            return
        
        operation = self.operation_var.get()
        scope = self.scope_var.get()
        content_type = self.content_var.get()
        
        # 保存当前编辑
        self.workbench._save_current_edit()
        
        # 禁用界面
        self.processing = True
        self.start_button.config(state="disabled")
        self.cancel_button.config(text="取消")
        self.progress_var.set(0)
        
        # 根据操作类型执行不同的处理
        if operation == "ai_translate":
            self._start_ai_translation(scope, content_type)
        elif operation == "export":
            self._start_export(scope, content_type)
        elif operation == "import":
            self._start_import(scope, content_type)
    
    def _on_cancel(self):
        """取消处理"""
        if self.processing:
            # 这里可以添加取消逻辑
            self.processing = False
            self.status_var.set("处理已取消")
            self.start_button.config(state="normal")
            self.cancel_button.config(text="关闭")
        else:
            self.destroy()
    
    def _get_processing_items(self, scope, content_type):
        """获取符合条件的处理项"""
        items_to_process = []
        
        # 确定要处理的命名空间
        if scope == "current":
            selection = self.workbench.ns_tree.selection()
            if not selection:
                messagebox.showwarning("范围错误", "请先在左侧选择一个项目以确定处理范围。")
                return None
            namespaces = selection
        else:
            namespaces = self.workbench.ns_tree.get_children()
        
        # 遍历命名空间，筛选符合条件的条目
        for ns in namespaces:
            items = self.workbench.translation_data.get(ns, {}).get("items", [])
            for idx, item in enumerate(items):
                en_text = item.get("en", "").strip()
                zh_text = item.get("zh", "").strip()
                source = item.get("source", "")
                
                # 根据内容类型筛选
                if content_type == "pending":
                    if not zh_text and en_text:
                        items_to_process.append((ns, idx, item))
                elif content_type == "completed":
                    if zh_text:
                        items_to_process.append((ns, idx, item))
                elif content_type == "all":
                    items_to_process.append((ns, idx, item))
        
        return items_to_process
    
    def _start_ai_translation(self, scope, content_type):
        """开始AI翻译"""
        items_to_process = self._get_processing_items(scope, content_type)
        if items_to_process is None:
            self.processing = False
            self.start_button.config(state="normal")
            return
        
        if not items_to_process:
            messagebox.showinfo("提示", "没有符合条件的条目需要处理。")
            self.processing = False
            self.start_button.config(state="normal")
            return
        
        self.status_var.set("正在准备AI翻译...")
        self.workbench.log_callback("正在准备AI翻译...", "INFO")
        
        # 在工作线程中执行AI翻译
        threading.Thread(target=self._ai_translation_worker, args=(items_to_process,), daemon=True).start()
    
    def _ai_translation_worker(self, items_to_process):
        """AI翻译工作线程"""
        try:
            # 提取要翻译的文本
            texts_to_translate = [item[2]['en'] for item in items_to_process]
            
            # 获取设置
            s = self.workbench.current_settings
            
            # 初始化翻译器
            translator = AITranslator(s['api_keys'], s.get('api_endpoint'))
            
            # 分批次处理
            batches = [texts_to_translate[i:i + s['ai_batch_size']] for i in range(0, len(texts_to_translate), s['ai_batch_size'])]
            total_batches = len(batches)
            translations_nested = [None] * total_batches
            
            # 使用线程池执行翻译
            with ThreadPoolExecutor(max_workers=s['ai_max_threads']) as executor:
                future_map = {executor.submit(translator.translate_batch, (i, batch, s['model'], s['prompt'], s.get('ai_stream_timeout', 30))): i for i, batch in enumerate(batches)}
                
                for i, future in enumerate(as_completed(future_map), 1):
                    if not self.processing:
                        break
                    
                    batch_idx = future_map[future]
                    translations_nested[batch_idx] = future.result()
                    
                    # 更新进度
                    progress = (i / total_batches) * 100
                    status_text = f"AI翻译中... 已完成 {i}/{total_batches} 个批次"
                    
                    self.after(0, lambda p=progress: self.progress_var.set(p))
                    self.after(0, lambda s=status_text: self.status_var.set(s))
                    self.workbench.log_callback(status_text, "INFO")
            
            if not self.processing:
                return
            
            # 合并翻译结果
            translations = list(itertools.chain.from_iterable(filter(None, translations_nested)))
            
            if len(translations) != len(texts_to_translate):
                raise ValueError(f"AI返回数量不匹配! 预期:{len(texts_to_translate)}, 实际:{len(translations)}")
            
            # 更新翻译结果
            self.after(0, self._update_translations, items_to_process, translations)
            
        except Exception as e:
            logging.error(f"AI翻译失败: {e}", exc_info=True)
            self.after(0, lambda: messagebox.showerror("AI翻译失败", f"执行AI翻译时发生错误:\n{e}"))
            self.after(0, lambda: self.status_var.set(f"处理失败: {str(e)}"))
        finally:
            self.after(0, lambda: setattr(self, "processing", False))
            self.after(0, lambda: self.start_button.config(state="normal"))
    
    def _update_translations(self, items_to_process, translations):
        """更新翻译结果"""
        # 记录操作前的状态用于撤销
        self.workbench._record_action(target_iid=None)
        
        updated_count = 0
        
        for (ns, idx, item), translation in zip(items_to_process, translations):
            if translation and translation.strip():
                item['zh'] = translation.strip()
                item['source'] = 'AI翻译'
                updated_count += 1
        
        # 更新UI
        self.workbench._populate_namespace_tree()
        self.workbench._populate_item_list()
        self.workbench._set_dirty(True)
        
        # 更新状态
        self.status_var.set(f"AI翻译完成，成功更新 {updated_count} 条翻译")
        self.workbench.log_callback(f"AI翻译完成，成功更新 {updated_count} 条翻译", "SUCCESS")
        
        # 更新菜单栏状态
        if self.workbench.main_window:
            self.workbench.main_window.update_menu_state()
    
    def _start_export(self, scope, content_type):
        """开始导出文本"""
        # 这里可以调用workbench的导出功能
        # 暂时使用现有的导出机制
        from tkinter import filedialog
        
        file_path = filedialog.asksaveasfilename(
            title="选择导出文件",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            self.processing = False
            self.start_button.config(state="normal")
            return
        
        # 调用现有的导出功能
        # 这里需要重构workbench的导出功能以支持筛选
        self.workbench._save_current_edit()
        
        # 获取导出数据
        export_data = self._get_export_data(scope, content_type)
        
        if export_data:
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=4)
            
            self.status_var.set(f"导出完成，共导出 {len(export_data)} 条记录")
            self.workbench.log_callback(f"成功导出 {len(export_data)} 条记录到 {file_path}", "SUCCESS")
        else:
            self.status_var.set("没有符合条件的数据可导出")
        
        self.processing = False
        self.start_button.config(state="normal")
    
    def _get_export_data(self, scope, content_type):
        """获取导出数据"""
        export_data = []
        
        # 确定要处理的命名空间
        if scope == "current":
            selection = self.workbench.ns_tree.selection()
            if not selection:
                return None
            namespaces = selection
        else:
            namespaces = self.workbench.ns_tree.get_children()
        
        # 遍历命名空间，筛选符合条件的条目
        for ns in namespaces:
            ns_data = self.workbench.translation_data.get(ns, {})
            items = ns_data.get("items", [])
            
            for idx, item in enumerate(items):
                en_text = item.get("en", "").strip()
                zh_text = item.get("zh", "").strip()
                source = item.get("source", "")
                
                # 根据内容类型筛选
                if content_type == "pending":
                    if not zh_text and en_text:
                        export_data.append({
                            "key": item["key"],
                            "en": item["en"],
                            "zh": item.get("zh", "")
                        })
                elif content_type == "completed":
                    if zh_text:
                        export_data.append({
                            "key": item["key"],
                            "en": item["en"],
                            "zh": item.get("zh", "")
                        })
                elif content_type == "all":
                    export_data.append({
                        "key": item["key"],
                        "en": item["en"],
                        "zh": item.get("zh", "")
                    })
        
        return export_data
    
    def _start_import(self, scope, content_type):
        """开始导入翻译"""
        # 这里可以调用workbench的导入功能
        # 暂时使用现有的导入机制
        self.processing = False
        self.start_button.config(state="normal")
        
        # 根据导入来源执行不同操作
        import_source = self.import_source_var.get()
        if import_source == "file":
            self.workbench._import_from_file()
        else:
            self.workbench._import_from_clipboard()
        
        self.destroy()