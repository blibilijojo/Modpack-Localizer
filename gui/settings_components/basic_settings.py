from __future__ import annotations
import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from gui import custom_widgets
from gui.settings_components.shared_utils import create_path_entry, create_mode_combobox

class BasicSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback

        self._create_variables()
        self._create_widgets()

    def _create_variables(self):
        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
        self.pack_as_zip_var = tk.BooleanVar(value=self.config.get("pack_as_zip", False))
        self.use_origin_name_lookup_var = tk.BooleanVar(value=self.config.get("use_origin_name_lookup", True))
        self.mod_list_name_mode_var = tk.StringVar(value=self.config.get("mod_list_name_mode", "namespace"))
        self._bind_events()

    def _bind_events(self):
        self.output_dir_var.trace_add("write", lambda *args: self.save_callback())
        self.pack_as_zip_var.trace_add("write", lambda *args: self.save_callback())
        self.use_origin_name_lookup_var.trace_add("write", lambda *args: self.save_callback())
        self.mod_list_name_mode_var.trace_add("write", lambda *args: self.save_callback())

    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self._create_basic_settings(main_frame)

    def _create_basic_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="基础设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(0, weight=1)

        output_frame = tk_ttk.LabelFrame(frame, text="输出设置", padding="10")
        output_frame.pack(fill="x", pady=(0, 10))
        output_frame.columnconfigure(1, weight=1)

        create_path_entry(output_frame, "默认输出文件夹:", self.output_dir_var, "directory",
                          "用于存放最终生成的汉化资源包的文件夹", self.save_callback)

        zip_check = ttk.Checkbutton(output_frame, text="打包为.zip压缩包", variable=self.pack_as_zip_var, bootstyle="primary")
        zip_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(zip_check, "开启后, 将直接生成一个.zip格式的资源包文件, 而不是文件夹。")

        matching_frame = tk_ttk.LabelFrame(frame, text="翻译匹配设置", padding="10")
        matching_frame.pack(fill="x", pady=(0, 10))
        matching_frame.columnconfigure(0, weight=1)

        origin_check = ttk.Checkbutton(matching_frame, text="启用原文匹配", variable=self.use_origin_name_lookup_var, bootstyle="primary")
        origin_check.pack(anchor="w", pady=5, padx=5)
        custom_widgets.ToolTip(origin_check, "推荐开启。\n当key查找失败时，尝试使用英文原文进行二次查找。\n能极大提升词典利用率，但可能在极少数情况下导致误翻。")

        name_mode_frame = tk_ttk.LabelFrame(frame, text="模组任务列表名称显示模式", padding="10")
        name_mode_frame.pack(fill="x", pady=(0, 10))

        mode_label = ttk.Label(name_mode_frame, text="显示模式:")
        mode_label.pack(side="left", padx=5, pady=5)

        create_mode_combobox(name_mode_frame, self.mod_list_name_mode_var, self.save_callback)

    def get_config(self):
        return {
            "output_dir": self.output_dir_var.get(),
            "pack_as_zip": self.pack_as_zip_var.get(),
            "use_origin_name_lookup": self.use_origin_name_lookup_var.get(),
            "mod_list_name_mode": self.mod_list_name_mode_var.get()
        }
