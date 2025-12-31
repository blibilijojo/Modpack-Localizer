import tkinter as tk
from tkinter import messagebox, ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
import requests
import threading

class GitHubProxySettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 初始化代理数据
        self.proxy_data = {}
        
        # 创建UI
        self._create_widgets()
        
        # 加载代理列表
        self._load_proxy_list()
    
    def _create_widgets(self):
        # 创建主容器
        container = ttk.Frame(self.parent)
        container.pack(fill="both", expand=True)
        
        # GitHub代理设置框架
        frame = tk_ttk.LabelFrame(container, text="GitHub代理设置", padding="10")
        frame.pack(fill="both", expand=True, pady=5, padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 说明文本
        ttk.Label(frame, text="管理GitHub加速代理URL，用于加速GitHub资源下载。", wraplength=700).pack(anchor="w", pady=5)
        
        # 代理表格区域
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建Treeview表格
        columns = ("url", "speed")
        self.proxy_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题和宽度
        self.proxy_tree.heading("url", text="代理URL", anchor="w")
        self.proxy_tree.heading("speed", text="速度")
        
        self.proxy_tree.column("url", width=300, anchor="w")
        self.proxy_tree.column("speed", width=100, anchor="center")
        
        # 添加滚动条
        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.proxy_tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.proxy_tree.xview)
        self.proxy_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # 布局
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        self.proxy_tree.pack(side="left", fill="both", expand=True)
        
        # 绑定事件
        self.proxy_tree.bind("<Double-1>", self._edit_proxy)
        
        # 操作按钮区域
        button_frame = ttk.LabelFrame(frame, text="操作", padding="10")
        button_frame.pack(fill="x", pady=5)
        button_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="button")
        
        # 第一行按钮：添加、删除、编辑
        ttk.Button(button_frame, text="一键添加预设代理", command=self._add_preset_proxies, bootstyle="success").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="删除选中", command=self._remove_selected_proxy, bootstyle="danger-outline").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="编辑选中", command=self._edit_proxy, bootstyle="warning-outline").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="清空", command=self._clear_proxies, bootstyle="secondary-outline").grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # 第二行按钮：测试功能
        ttk.Button(button_frame, text="测试选中代理", command=self._test_selected_proxy, bootstyle="info-outline").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="批量测试速度", command=self._batch_test_speed, bootstyle="info-outline").grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(button_frame, text="清空测试结果", command=self._clear_test_results, bootstyle="secondary-outline").grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        
        # 添加新代理区域
        add_proxy_frame = ttk.LabelFrame(frame, text="添加新代理", padding="10")
        add_proxy_frame.pack(fill="x", pady=5)
        add_proxy_frame.columnconfigure(1, weight=1)
        
        ttk.Label(add_proxy_frame, text="代理URL:", width=10).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.new_proxy_var = tk.StringVar(value="")
        ttk.Entry(add_proxy_frame, textvariable=self.new_proxy_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(add_proxy_frame, text="添加", command=self._add_proxy, bootstyle="success-outline").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
    
    def _load_proxy_list(self):
        """加载代理列表"""
        # 清除现有数据
        for item in self.proxy_tree.get_children():
            self.proxy_tree.delete(item)
        
        # 加载配置中的代理
        proxies = self.config.get("github_proxies", [])
        for proxy_url in proxies:
            # 初始化速度数据
            self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
    
    def _save_proxy_list(self):
        """保存代理列表"""
        proxies = []
        for item in self.proxy_tree.get_children():
            proxy_url = self.proxy_tree.item(item)['values'][0]
            proxies.append(proxy_url)
        
        self.config["github_proxies"] = proxies
        self.save_callback()
    
    def _add_proxy(self):
        """添加新代理"""
        proxy_url = self.new_proxy_var.get().strip()
        if not proxy_url:
            return
        
        # 验证URL格式
        if not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
            ui_utils.show_error("格式错误", "代理URL必须以http://或https://开头")
            return
        
        # 检查是否已存在
        for item in self.proxy_tree.get_children():
            existing_proxy = self.proxy_tree.item(item)['values'][0]
            if existing_proxy == proxy_url:
                ui_utils.show_warning("已存在", "该代理URL已存在")
                return
        
        # 添加到表格
        self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
        self.new_proxy_var.set("")
        self._save_proxy_list()
    
    def _remove_selected_proxy(self):
        """删除选中的代理"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            return
        
        for item in selected_items:
            self.proxy_tree.delete(item)
        
        self._save_proxy_list()
    
    def _edit_proxy(self, event=None):
        """编辑选中的代理"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            return
        
        item = selected_items[0]
        current_values = self.proxy_tree.item(item)['values']
        current_url = current_values[0]
        
        # 创建编辑窗口
        edit_window = tk.Toplevel(self.parent)
        edit_window.title("编辑代理")
        edit_window.geometry("400x150")
        edit_window.resizable(False, False)
        
        # 居中窗口
        edit_window.update_idletasks()
        width = edit_window.winfo_width()
        height = edit_window.winfo_height()
        x = (edit_window.winfo_screenwidth() // 2) - (width // 2)
        y = (edit_window.winfo_screenheight() // 2) - (height // 2)
        edit_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # 创建编辑界面
        frame = ttk.Frame(edit_window, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="代理URL:", width=10).grid(row=0, column=0, padx=5, pady=10, sticky="w")
        edit_var = tk.StringVar(value=current_url)
        ttk.Entry(frame, textvariable=edit_var).grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        frame.columnconfigure(1, weight=1)
        
        def save_edit():
            new_url = edit_var.get().strip()
            if not new_url:
                return
            
            # 验证URL格式
            if not (new_url.startswith("http://") or new_url.startswith("https://")):
                ui_utils.show_error("格式错误", "代理URL必须以http://或https://开头")
                return
            
            # 检查是否已存在（排除当前项）
            for tree_item in self.proxy_tree.get_children():
                if tree_item == item:
                    continue
                existing_proxy = self.proxy_tree.item(tree_item)['values'][0]
                if existing_proxy == new_url:
                    ui_utils.show_warning("已存在", "该代理URL已存在")
                    return
            
            # 更新表格
            self.proxy_tree.item(item, values=(new_url, current_values[1]))
            self._save_proxy_list()
            edit_window.destroy()
        
        # 按钮
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        ttk.Button(button_frame, text="保存", command=save_edit, bootstyle="primary").grid(row=0, column=0, padx=5, sticky="ew")
        ttk.Button(button_frame, text="取消", command=edit_window.destroy, bootstyle="secondary").grid(row=0, column=1, padx=5, sticky="ew")
    
    def _clear_proxies(self):
        """清空所有代理"""
        if messagebox.askyesno("确认清空", "确定要清空所有代理吗？"):
            self.proxy_tree.delete(*self.proxy_tree.get_children())
            self._save_proxy_list()
    
    def _add_preset_proxies(self):
        """一键添加预设的四个GitHub加速代理"""
        preset_proxies = [
            "https://gh-proxy.org/",
            "https://hk.gh-proxy.org/",
            "https://cdn.gh-proxy.org/",
            "https://edgeone.gh-proxy.org/"
        ]
        
        added_count = 0
        existing_proxies = [self.proxy_tree.item(item)['values'][0] for item in self.proxy_tree.get_children()]
        
        for proxy_url in preset_proxies:
            if proxy_url not in existing_proxies:
                # 添加到表格
                self.proxy_tree.insert("", tk.END, values=(proxy_url, "--"))
                added_count += 1
                existing_proxies.append(proxy_url)
        
        if added_count > 0:
            self._save_proxy_list()
            ui_utils.show_info("添加成功", f"已添加 {added_count} 个预设代理")
        else:
            ui_utils.show_warning("已存在", "所有预设代理已存在")
    
    def _test_selected_proxy(self):
        """测试选中代理的速度"""
        selected_items = self.proxy_tree.selection()
        if not selected_items:
            ui_utils.show_warning("未选择", "请先选择一个代理进行测试")
            return
        
        for item in selected_items:
            proxy_url = self.proxy_tree.item(item)['values'][0]
            self.proxy_tree.item(item, values=(proxy_url, "测试中..."))
            threading.Thread(target=self._test_proxy_speed, args=(item, proxy_url), daemon=True).start()
    
    def _batch_test_speed(self):
        """批量测试所有代理的速度"""
        items = self.proxy_tree.get_children()
        if not items:
            return
        
        for item in items:
            proxy_url = self.proxy_tree.item(item)['values'][0]
            self.proxy_tree.item(item, values=(proxy_url, "测试中..."))
            threading.Thread(target=self._test_proxy_speed, args=(item, proxy_url), daemon=True).start()
    
    def _test_proxy_speed(self, item, proxy_url):
        """测试单个代理的速度"""
        try:
            test_url = "https://github.com"
            start_time = requests.get(test_url, proxies={"http": proxy_url, "https": proxy_url}, timeout=5).elapsed.total_seconds()
            speed = f"{start_time:.2f}s"
            self.parent.after(0, lambda: self.proxy_tree.item(item, values=(proxy_url, speed)))
        except Exception as e:
            self.parent.after(0, lambda: self.proxy_tree.item(item, values=(proxy_url, "失败")))
    
    def _clear_test_results(self):
        """清空测试结果"""
        for item in self.proxy_tree.get_children():
            proxy_url = self.proxy_tree.item(item)['values'][0]
            self.proxy_tree.item(item, values=(proxy_url, "--"))
    
    def get_config(self):
        """获取当前配置"""
        proxies = []
        for item in self.proxy_tree.get_children():
            proxy_url = self.proxy_tree.item(item)['values'][0]
            proxies.append(proxy_url)
        
        return {
            "github_proxies": proxies
        }
