import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk

class GitHubVersionSelectDialog(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("选择模组版本")
        self.geometry("500x500")
        self.minsize(400, 400)
        self.result = None
        
        # 设置为模态对话框
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._load_versions()
        
        # 居中显示
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        
        # 等待用户操作
        self.wait_window(self)
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill="both", expand=True)
        
        # 搜索框
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索版本:").pack(side="left", padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        search_entry.bind("<KeyRelease>", self._filter_versions)
        
        # 版本列表
        list_frame = ttk.LabelFrame(main_frame, text="可用版本")
        list_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # 创建树视图
        self.versions_tree = ttk.Treeview(list_frame, columns=("version", "date"), show="headings")
        self.versions_tree.heading("version", text="版本号")
        self.versions_tree.heading("date", text="发布日期")
        self.versions_tree.column("version", width=200)
        self.versions_tree.column("date", width=150)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.versions_tree.yview)
        self.versions_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.versions_tree.pack(fill="both", expand=True)
        
        # 绑定选择事件
        self.versions_tree.bind("<<TreeviewSelect>>", self._on_version_selected)
        self.versions_tree.bind("<Double-1>", self._on_double_click)
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 5))
        
        self.upload_btn = ttk.Button(btn_frame, text="上传", command=self._on_upload, bootstyle="success", state="disabled")
        self.upload_btn.pack(side="right", padx=5)
        
        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self._on_cancel, bootstyle="secondary")
        self.cancel_btn.pack(side="right", padx=5)
        
        # 状态标签
        self.status_var = tk.StringVar(value="请选择一个版本")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, bootstyle="secondary")
        self.status_label.pack(fill="x", pady=(10, 0))
    
    def _load_versions(self):
        """加载版本列表"""
        # 清空现有列表
        for item in self.versions_tree.get_children():
            self.versions_tree.delete(item)
        
        # 模拟版本数据
        # 实际项目中，这里应该从配置或API获取真实的版本列表
        versions = [
            {"version": "1.20.1", "date": "2024-01-15"},
            {"version": "1.20.0", "date": "2023-12-05"},
            {"version": "1.19.4", "date": "2023-06-07"},
            {"version": "1.19.3", "date": "2023-03-14"},
            {"version": "1.19.2", "date": "2022-08-05"},
            {"version": "1.18.2", "date": "2022-02-28"},
            {"version": "1.17.1", "date": "2021-07-06"},
            {"version": "1.16.5", "date": "2021-01-15"},
        ]
        
        # 添加版本到树视图
        for version_info in versions:
            self.versions_tree.insert("", "end", values=(version_info["version"], version_info["date"]), tags=(version_info["version"],))
        
        # 默认选择第一个版本
        if self.versions_tree.get_children():
            first_item = self.versions_tree.get_children()[0]
            self.versions_tree.selection_set(first_item)
            self._on_version_selected()
    
    def _filter_versions(self, event=None):
        """过滤版本列表"""
        filter_text = self.search_var.get().lower().strip()
        
        # 清空现有选择
        self.versions_tree.selection_remove(*self.versions_tree.selection())
        
        # 过滤版本
        for item in self.versions_tree.get_children():
            version = self.versions_tree.item(item, "values")[0].lower()
            if filter_text in version:
                self.versions_tree.item(item, tags=("visible",))
            else:
                self.versions_tree.item(item, tags=("hidden",))
        
        # 应用过滤
        self.versions_tree.tag_configure("hidden", foreground="gray")
        self.versions_tree.tag_configure("visible", foreground="")
    
    def _on_version_selected(self, event=None):
        """版本选择事件"""
        selection = self.versions_tree.selection()
        if selection:
            version = self.versions_tree.item(selection[0], "values")[0]
            self.status_var.set(f"已选择版本: {version}")
            self.upload_btn.config(state="normal")
        else:
            self.status_var.set("请选择一个版本")
            self.upload_btn.config(state="disabled")
    
    def _on_double_click(self, event=None):
        """双击选择版本"""
        selection = self.versions_tree.selection()
        if selection:
            self._on_upload()
    
    def _on_upload(self):
        """上传按钮点击事件"""
        selection = self.versions_tree.selection()
        if selection:
            self.result = self.versions_tree.item(selection[0], "values")[0]
            self.destroy()
    
    def _on_cancel(self):
        """取消按钮点击事件"""
        self.result = None
        self.destroy()
