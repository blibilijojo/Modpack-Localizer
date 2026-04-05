import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets

class GeneralSettings:
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
        
        # 社区词典匹配设置
        self.use_community_dict_key_var = tk.BooleanVar(value=self.config.get("use_community_dict_key", True))
        self.use_community_dict_origin_var = tk.BooleanVar(value=self.config.get("use_community_dict_origin", True))
        
        # 列表名称显示模式
        self.mod_list_name_mode_var = tk.StringVar(value=self.config.get("mod_list_name_mode", "namespace"))
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.output_dir_var.trace_add("write", lambda *args: self.save_callback())
        self.pack_as_zip_var.trace_add("write", lambda *args: self.save_callback())
        self.use_community_dict_key_var.trace_add("write", lambda *args: self.save_callback())
        self.use_community_dict_origin_var.trace_add("write", lambda *args: self.save_callback())
        self.mod_list_name_mode_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建输出设置
        self._create_output_settings(main_frame)
        
        # 创建翻译匹配设置
        self._create_matching_settings(main_frame)
        
        # 创建列表显示设置
        self._create_list_display_settings(main_frame)
    
    def _create_output_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="输出设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)
        
        self._create_path_entry(frame, "资源包输出目录:", self.output_dir_var, "directory", "用于存放最终生成的汉化资源包的文件夹")
        
        zip_check = ttk.Checkbutton(frame, text="输出为ZIP压缩包", variable=self.pack_as_zip_var, bootstyle="primary")
        zip_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(zip_check, "开启后，将直接生成一个ZIP格式的资源包文件，而不是文件夹。")
    
    def _create_matching_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="翻译匹配", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(0, weight=1)
        
        # 社区词典匹配设置
        community_frame = ttk.LabelFrame(frame, text="社区词典匹配")
        community_frame.pack(fill="x", pady=5, padx=5, ipady=5, ipadx=5)
        
        community_key_check = ttk.Checkbutton(community_frame, text="启用社区词典 Key 匹配", variable=self.use_community_dict_key_var, bootstyle="primary")
        community_key_check.pack(anchor="w", pady=3, padx=5)
        custom_widgets.ToolTip(community_key_check, "使用社区词典中的 Key 进行匹配。\nKey 匹配准确性高，但覆盖范围可能有限。")
        
        community_origin_check = ttk.Checkbutton(community_frame, text="启用社区词典原文匹配", variable=self.use_community_dict_origin_var, bootstyle="primary")
        community_origin_check.pack(anchor="w", pady=3, padx=5)
        custom_widgets.ToolTip(community_origin_check, "使用社区词典中的原文进行匹配。\n原文匹配覆盖范围广，但可能在极少数情况下导致误翻。")
    
    def _create_list_display_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="列表显示", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        
        # 创建下拉框
        mode_label = ttk.Label(frame, text="名称显示模式:")
        mode_label.pack(side="left", padx=5, pady=5)
        
        # 定义选项
        mode_options = [
            ("命名空间（文件名称）", "namespace_jar"),
            ("文件名称（命名空间）", "jar_namespace"),
            ("命名空间", "namespace"),
            ("文件名称", "jar")
        ]
        
        # 创建下拉框
        mode_combobox = ttk.Combobox(frame, state="readonly")
        mode_combobox['values'] = [option[0] for option in mode_options]
        
        # 设置默认值
        current_value = self.mod_list_name_mode_var.get()
        for i, (option_text, option_value) in enumerate(mode_options):
            if option_value == current_value:
                mode_combobox.current(i)
                break
        
        mode_combobox.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        # 绑定变化事件
        def on_mode_change(event):
            selected_index = mode_combobox.current()
            if selected_index != -1:
                selected_value = mode_options[selected_index][1]
                self.mod_list_name_mode_var.set(selected_value)
                self.save_callback()
                # 清除文本选中状态
                mode_combobox.selection_clear()
        
        mode_combobox.bind("<<ComboboxSelected>>", on_mode_change)
    
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
            "use_community_dict_key": self.use_community_dict_key_var.get(),
            "use_community_dict_origin": self.use_community_dict_origin_var.get(),
            "mod_list_name_mode": self.mod_list_name_mode_var.get()
        }
