import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets

class BasicSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 创建变量
        self._create_variables()
        
        # 创建UI
        self._create_widgets()
    
    def _create_variables(self):
        # 输出设置
        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
        self.pack_as_zip_var = tk.BooleanVar(value=self.config.get("pack_as_zip", False))
        
        # 翻译匹配设置
        self.use_origin_name_lookup_var = tk.BooleanVar(value=self.config.get("use_origin_name_lookup", True))
        
        # 网络设置
        self.use_proxy_var = tk.BooleanVar(value=self.config.get("use_github_proxy", True))
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.output_dir_var.trace_add("write", lambda *args: self.save_callback())
        self.pack_as_zip_var.trace_add("write", lambda *args: self.save_callback())
        self.use_origin_name_lookup_var.trace_add("write", lambda *args: self.save_callback())
        self.use_proxy_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建基础设置
        self._create_basic_settings(main_frame)
    
    def _create_basic_settings(self, parent):
        # 基础设置框架
        frame = tk_ttk.LabelFrame(parent, text="基础设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 输出设置分组
        output_frame = tk_ttk.LabelFrame(frame, text="输出设置", padding="10")
        output_frame.pack(fill="x", pady=(0, 10))
        output_frame.columnconfigure(1, weight=1)
        
        self._create_path_entry(output_frame, "默认输出文件夹:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")
        
        zip_check = ttk.Checkbutton(output_frame, text="打包为.zip压缩包", variable=self.pack_as_zip_var, bootstyle="primary")
        zip_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(zip_check, "开启后, 将直接生成一个.zip格式的资源包文件, 而不是文件夹。")
        
        # 翻译匹配设置分组
        matching_frame = tk_ttk.LabelFrame(frame, text="翻译匹配设置", padding="10")
        matching_frame.pack(fill="x", pady=(0, 10))
        matching_frame.columnconfigure(0, weight=1)
        
        origin_check = ttk.Checkbutton(matching_frame, text="启用原文匹配", variable=self.use_origin_name_lookup_var, bootstyle="primary")
        origin_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(origin_check, "推荐开启。\n当key查找失败时，尝试使用英文原文进行二次查找。\n能极大提升词典利用率，但可能在极少数情况下导致误翻。")
        
        # 网络设置分组
        network_frame = tk_ttk.LabelFrame(frame, text="网络设置", padding="10")
        network_frame.pack(fill="x")
        network_frame.columnconfigure(0, weight=1)
        
        proxy_check = ttk.Checkbutton(network_frame, text="使用代理加速下载", variable=self.use_proxy_var, bootstyle="primary")
        proxy_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(proxy_check, "开启后，在下载社区词典或程序更新时会自动使用内置的代理服务。")
    
    def _create_path_entry(self, parent, label_text, var, browse_type, tooltip):
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill="x", pady=5)
        label = ttk.Label(row_frame, text=label_text, width=15)
        label.pack(side="left")
        custom_widgets.ToolTip(label, tooltip)
        entry = ttk.Entry(row_frame, textvariable=var, takefocus=False)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        
        browse_cmd = lambda: ui_utils.browse_directory(var) if browse_type == "directory" else ui_utils.browse_file(var)
        ttk.Button(row_frame, text="浏览...", command=browse_cmd, bootstyle="primary-outline").pack(side="left")
        
        # 防止自动选中文本
        entry.after_idle(entry.selection_clear)
    
    def get_config(self):
        return {
            "output_dir": self.output_dir_var.get(),
            "pack_as_zip": self.pack_as_zip_var.get(),
            "use_origin_name_lookup": self.use_origin_name_lookup_var.get(),
            "use_github_proxy": self.use_proxy_var.get()
        }
