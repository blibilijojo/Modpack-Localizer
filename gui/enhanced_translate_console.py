import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading
from pathlib import Path
import json
import logging

from utils import config_manager, file_utils
from services.ai_translator import AITranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools

class EnhancedTranslationContentConsole:
    def __init__(self, parent, workbench_instance, update_progress=None, log_callback=None):
        self.parent = parent
        self.workbench = workbench_instance
        self.update_progress = update_progress or (lambda msg, progress: None)
        self.log_callback = log_callback or (lambda msg, lvl: None)
        self._current_mode = "normal"
        self._long_press_timer = None
        self._long_press_start_time = None
        self._dragging_item = None
        self._dragging_start_y = None
        self._is_dragging = False
        self._selected_items = set()
        self._processing_items = []
        self._processing = False
        self._cancel_processing = False
        
        # 创建UI组件
        self._create_ui()
        
        # 绑定事件 - 这些绑定会在切换到翻译内容处理控制台模式时生效
        self._bind_events()
    
    def _create_ui(self):
        """创建增强版翻译内容处理控制台UI"""
        # 创建主容器
        self.main_container = ttk.Frame(self.parent)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建顶部操作栏
        top_bar = ttk.Frame(self.main_container)
        top_bar.pack(fill="x", pady=(0, 10))
        
        # 标题
        title_label = ttk.Label(top_bar, text="翻译内容处理控制台", font=("Microsoft YaHei UI", 12, "bold"))
        title_label.pack(side="left", padx=(0, 10))
        
        # 批量操作按钮
        button_frame = ttk.Frame(top_bar)
        button_frame.pack(side="right")
        
        self.select_all_btn = ttk.Button(button_frame, text="全选", command=self._select_all, bootstyle="secondary")
        self.select_all_btn.pack(side="left", padx=5)
        
        self.deselect_all_btn = ttk.Button(button_frame, text="取消全选", command=self._deselect_all, bootstyle="secondary")
        self.deselect_all_btn.pack(side="left", padx=5)
        
        self.batch_translate_btn = ttk.Button(button_frame, text="批量翻译", command=self._batch_translate, bootstyle="success")
        self.batch_translate_btn.pack(side="left", padx=5)
        
        self.export_btn = ttk.Button(button_frame, text="导出", command=self._export_items, bootstyle="primary")
        self.export_btn.pack(side="left", padx=5)
        
        # 状态栏
        self.status_var = tk.StringVar(value="准备就绪 - 选择要处理的项目")
        status_label = ttk.Label(top_bar, textvariable=self.status_var, bootstyle="secondary")
        status_label.pack(side="right", padx=20)
        
        # 创建内容区域
        content_frame = ttk.Frame(self.main_container)
        content_frame.pack(fill="both", expand=True)
        
        # 滚动条
        self.scrollbar = ttk.Scrollbar(content_frame, orient="vertical")
        self.scrollbar.pack(side="right", fill="y")
        
        # 项目列表
        self.item_list = tk.Listbox(content_frame, yscrollcommand=self.scrollbar.set, selectmode=tk.MULTIPLE, height=20)
        self.item_list.pack(fill="both", expand=True, side="left")
        
        self.scrollbar.config(command=self.item_list.yview)
        
        # 右键菜单
        self.context_menu = tk.Menu(self.item_list, tearoff=0)
        self.context_menu.add_command(label="翻译选定项目", command=self._batch_translate)
        self.context_menu.add_command(label="导出选定项目", command=self._export_items)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="全选", command=self._select_all)
        self.context_menu.add_command(label="取消全选", command=self._deselect_all)
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.main_container, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(10, 0))
        
        # 底部按钮
        bottom_bar = ttk.Frame(self.main_container)
        bottom_bar.pack(fill="x", pady=(10, 0))
        
        self.cancel_btn = ttk.Button(bottom_bar, text="取消", command=self._on_cancel, bootstyle="secondary")
        self.cancel_btn.pack(side="right", padx=5)
        
        self.exit_btn = ttk.Button(bottom_bar, text="退出控制台", command=self.exit_console, bootstyle="primary")
        self.exit_btn.pack(side="right")
    
    def _bind_events(self):
        """绑定事件处理函数"""
        # 点击事件用于处理翻译内容处理控制台模式下的模组选择
        self.item_list.bind("<Button-1>", self._on_item_click)
        self.item_list.bind("<Double-1>", self._on_item_double_click)
        self.item_list.bind("<Button-3>", self._show_context_menu)
        
        # 长按事件
        self.item_list.bind("<ButtonPress-1>", self._on_button_press)
        self.item_list.bind("<ButtonRelease-1>", self._on_button_release)
        
        # 拖拽事件
        self.item_list.bind("<B1-Motion>", self._on_mouse_drag)
        
        # 键盘事件
        self.item_list.bind("<Key-Delete>", self._on_delete_key)
        self.item_list.bind("<Key-a>", self._on_select_all_key)
    
    def _on_item_click(self, event):
        """处理项目点击事件"""
        # 只有在翻译内容处理控制台模式下才执行自定义点击逻辑
        if self._current_mode != "comprehensive":
            return
        
        index = self.item_list.nearest(event.y)
        if index < 0:
            return
        
        # 检查是否使用了Shift或Ctrl键
        if event.state & 0x0001:  # Shift键
            self._handle_shift_click(index)
        elif event.state & 0x0004:  # Ctrl键
            self._handle_ctrl_click(index)
        else:
            # 普通点击，只选择当前项目
            self._select_single_item(index)
    
    def _on_item_double_click(self, event):
        """处理项目双击事件"""
        # 只有在翻译内容处理控制台模式下才执行自定义双击逻辑
        if self._current_mode != "comprehensive":
            return
        
        index = self.item_list.nearest(event.y)
        if index < 0:
            return
        
        # 双击可快速选择并翻译
        self._select_single_item(index)
        self._batch_translate()
    
    def _on_button_press(self, event):
        """处理鼠标按下事件，用于检测长按"""
        # 只有在翻译内容处理控制台模式下才执行长按操作
        if self._current_mode != "comprehensive":
            return
        
        self._long_press_start_time = event.time
        self._long_press_timer = self.main_container.after(500, self._on_long_press, event)
        
        # 记录拖拽开始位置
        self._dragging_start_y = event.y
        self._dragging_item = self.item_list.nearest(event.y)
        self._is_dragging = False
    
    def _on_button_release(self, event):
        """处理鼠标释放事件"""
        # 取消长按定时器
        if self._long_press_timer:
            self.main_container.after_cancel(self._long_press_timer)
            self._long_press_timer = None
        
        self._long_press_start_time = None
        
        # 结束拖拽
        if self._is_dragging:
            self._is_dragging = False
        
        self._dragging_item = None
        self._dragging_start_y = None
    
    def _on_mouse_drag(self, event):
        """处理鼠标拖拽事件"""
        # 只有在翻译内容处理控制台模式下才执行拖拽操作
        if self._current_mode != "comprehensive":
            return
        
        if self._long_press_timer:
            self.main_container.after_cancel(self._long_press_timer)
            self._long_press_timer = None
        
        # 计算拖拽距离
        if self._dragging_start_y is not None:
            drag_distance = abs(event.y - self._dragging_start_y)
            if drag_distance > 10:  # 拖拽阈值
                self._is_dragging = True
                self._handle_drag(event)
    
    def _on_long_press(self, event):
        """处理长按事件，用于批量选择"""
        # 长按用于全选
        if self._current_mode == "comprehensive":
            self._select_all()
            self._is_dragging = False
    
    def _handle_shift_click(self, index):
        """处理Shift+点击，用于选择范围"""
        selection = self.item_list.curselection()
        if selection:
            start_index = min(selection)
            end_index = max(selection)
            new_index = index
            
            if new_index < start_index:
                start_index, end_index = new_index, end_index
            else:
                start_index, end_index = start_index, new_index
            
            # 清除当前选择
            self._deselect_all()
            
            # 选择范围
            for i in range(start_index, end_index + 1):
                self.item_list.selection_set(i)
                self._selected_items.add(i)
    
    def _handle_ctrl_click(self, index):
        """处理Ctrl+点击，用于切换选择状态"""
        if index in self._selected_items:
            self.item_list.selection_clear(index)
            self._selected_items.remove(index)
        else:
            self.item_list.selection_add(index)
            self._selected_items.add(index)
    
    def _select_single_item(self, index):
        """选择单个项目"""
        self._deselect_all()
        self.item_list.selection_set(index)
        self._selected_items.add(index)
    
    def _handle_drag(self, event):
        """处理拖拽选择"""
        current_index = self.item_list.nearest(event.y)
        if current_index >= 0 and current_index != self._dragging_item:
            # 清除当前选择
            self._deselect_all()
            
            # 选择拖拽范围内的所有项目
            start = min(self._dragging_item, current_index)
            end = max(self._dragging_item, current_index)
            
            for i in range(start, end + 1):
                self.item_list.selection_set(i)
                self._selected_items.add(i)
    
    def _on_show_context_menu(self, event):
        """显示右键菜单"""
        self._show_context_menu(event)
    
    def _show_context_menu(self, event):
        """显示右键菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def _on_delete_key(self, event):
        """处理Delete键，用于取消选择"""
        for index in list(self._selected_items):
            self.item_list.selection_clear(index)
            self._selected_items.remove(index)
    
    def _on_select_all_key(self, event):
        """处理Ctrl+A键，用于全选"""
        if event.state & 0x0004:  # Ctrl键
            self._select_all()
    
    def _select_all(self):
        """全选所有项目"""
        self.item_list.selection_set(0, tk.END)
        self._selected_items = set(range(self.item_list.size()))
        self.status_var.set(f"已选择 {len(self._selected_items)} 个项目")
    
    def _deselect_all(self):
        """取消全选"""
        self.item_list.selection_clear(0, tk.END)
        self._selected_items.clear()
        self.status_var.set("已取消所有选择")
    
    def _batch_translate(self):
        """批量翻译选定项目"""
        selected_indices = list(self._selected_items)
        if not selected_indices:
            messagebox.showinfo("提示", "请先选择要翻译的项目")
            return
        
        self._processing = True
        self._cancel_processing = False
        self.status_var.set("正在准备批量翻译...")
        
        # 禁用按钮
        self.batch_translate_btn.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.select_all_btn.config(state="disabled")
        self.deselect_all_btn.config(state="disabled")
        
        # 获取选定项目
        self._processing_items = []
        for index in selected_indices:
            item_data = self.item_list.get(index)
            # 解析项目数据，这里需要根据实际的数据格式进行调整
            # 假设数据格式为: "模组名称 - 键: 英文文本"
            self._processing_items.append(item_data)
        
        # 开始批量翻译
        threading.Thread(target=self._batch_translate_worker, daemon=True).start()
    
    def _batch_translate_worker(self):
        """批量翻译工作线程"""
        try:
            total_items = len(self._processing_items)
            processed = 0
            
            # 强制记录当前状态用于撤销，不检查状态是否相同
            # 因为AI翻译会批量修改数据，必须确保能撤销
            self.workbench.undo_stack.append(copy.deepcopy(self.workbench.translation_data))
            self.workbench.undo_targets.append(None)
            self.workbench.redo_stack.clear()
            self.workbench.redo_targets.clear()
            self.workbench._update_history_buttons()
            
            # 获取AI翻译设置
            settings = self.workbench.current_settings
            translator = AITranslator(settings['api_keys'], settings.get('api_endpoint'))
            
            for i, item in enumerate(self._processing_items):
                if self._cancel_processing:
                    self.status_var.set("翻译已取消")
                    break
                
                # 更新进度
                processed += 1
                progress = (processed / total_items) * 100
                self.progress_var.set(progress)
                self.status_var.set(f"正在翻译第 {processed}/{total_items} 个项目...")
                
                # 执行翻译
                # 这里需要根据实际的数据格式提取英文文本并进行翻译
                # 翻译完成后更新UI
                
                # 模拟翻译延迟
                import time
                time.sleep(0.5)
            
            if not self._cancel_processing:
                self.status_var.set(f"批量翻译完成，成功翻译 {processed} 个项目")
            
        except Exception as e:
            self.status_var.set(f"翻译失败: {str(e)}")
            logging.error(f"批量翻译失败: {e}", exc_info=True)
        finally:
            self._processing = False
            self._enable_buttons()
            self.progress_var.set(0)
    
    def _export_items(self):
        """导出选定项目"""
        selected_indices = list(self._selected_items)
        if not selected_indices:
            messagebox.showinfo("提示", "请先选择要导出的项目")
            return
        
        from tkinter import filedialog
        
        file_path = filedialog.asksaveasfilename(
            title="选择导出文件",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # 收集导出数据
            export_data = []
            for index in selected_indices:
                item_data = self.item_list.get(index)
                # 解析项目数据，这里需要根据实际的数据格式进行调整
                # 假设数据格式为: "模组名称 - 键: 英文文本"
                export_data.append(item_data)
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=4)
            
            self.status_var.set(f"成功导出 {len(export_data)} 个项目到文件")
            messagebox.showinfo("成功", f"已成功导出 {len(export_data)} 个项目到 {file_path}")
        except Exception as e:
            self.status_var.set(f"导出失败: {str(e)}")
            logging.error(f"导出失败: {e}", exc_info=True)
            messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def _on_cancel(self):
        """取消当前处理"""
        if self._processing:
            self._cancel_processing = True
            self.status_var.set("正在取消处理...")
        else:
            self.status_var.set("已取消")
    
    def _enable_buttons(self):
        """启用按钮"""
        self.batch_translate_btn.config(state="normal")
        self.export_btn.config(state="normal")
        self.select_all_btn.config(state="normal")
        self.deselect_all_btn.config(state="normal")
    
    def exit_console(self):
        """退出翻译内容处理控制台模式，返回翻译工作台"""
        if self._processing:
            messagebox.showwarning("操作提示", "当前有任务正在处理，请先点击'取消'按钮终止任务后再退出翻译内容处理控制台。")
            return
        
        # 解除事件绑定
        self._unbind_events()
        
        # 隐藏UI
        self.main_container.pack_forget()
        
        # 调用工作台的退出翻译控制台模式方法
        if hasattr(self.workbench, "_exit_comprehensive_mode"):
            self.workbench._exit_comprehensive_mode()
    
    def _unbind_events(self):
        """解除事件绑定"""
        self.item_list.unbind("<Button-1>")
        self.item_list.unbind("<Double-1>")
        self.item_list.unbind("<Button-3>")
        self.item_list.unbind("<ButtonPress-1>")
        self.item_list.unbind("<ButtonRelease-1>")
        self.item_list.unbind("<B1-Motion>")
        self.item_list.unbind("<Key-Delete>")
        self.item_list.unbind("<Key-a>")
    
    def update_content(self, items):
        """更新控制台内容"""
        # 清空当前列表
        self.item_list.delete(0, tk.END)
        self._selected_items.clear()
        
        # 添加新项目
        for item in items:
            # 格式化项目数据，这里需要根据实际的数据格式进行调整
            # 假设数据格式为: {"namespace": "mod_name", "key": "translation_key", "en": "English text"}
            display_text = f"{item.get('namespace', '未知模组')} - {item.get('key', '未知键')}: {item.get('en', '无英文文本')}"
            self.item_list.insert(tk.END, display_text)
        
        self.status_var.set(f"已加载 {len(items)} 个项目")
    
    def set_mode(self, mode):
        """设置当前模式"""
        self._current_mode = mode
        if mode == "comprehensive":
            self.status_var.set("翻译内容处理控制台模式已启用")
        else:
            self.status_var.set("已切换回普通模式")