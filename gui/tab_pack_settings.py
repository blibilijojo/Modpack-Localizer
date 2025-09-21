import tkinter as tk
from tkinter import simpledialog, filedialog
import ttkbootstrap as ttk
from gui import ui_utils
from utils import config_manager
from gui.custom_widgets import ToolTip
PACK_FORMATS = {
    "1.21 (Format 34)": 34, "1.20.5 - 1.20.6 (Format 32)": 32, "1.20.3 - 1.20.4 (Format 22)": 22,
    "1.20.2 (Format 18)": 18, "1.20 - 1.20.1 (Format 15)": 15, "1.19.4 (Format 13)": 13,
    "1.19.3 (Format 12)": 12, "1.19 - 1.19.2 (Format 9)": 9, "1.18 - 1.18.2 (Format 8)": 8,
    "1.17 - 1.17.1 (Format 7)": 7, "1.16.2 - 1.16.5 (Format 6)": 6, "1.15 - 1.16.1 (Format 5)": 5,
    "1.13 - 1.14.4 (Format 4)": 4,
    "1.11 - 1.12.2 (Format 3)": 3,
    "1.9 - 1.10.2 (Format 2)": 2,
    "1.6.1 - 1.8.9 (Format 1)": 1,
}
PLACEHOLDER_TOOLTIP_TEXT = """
支持使用动态占位符, 在生成时会自动替换为真实数据:
  - {timestamp}: 生成时间 (格式: YYYYMMDD_HHMMSS)
  - {total}: 翻译条目总数
  - {ai_count}: AI 翻译的条目数
  - {ai_percent}: AI 翻译的百分比
  - {human_count}: 人工及社区贡献的条目数
  - {human_percent}: 人工及社区贡献的百分比
如果此字段留空, 将自动使用包含上述所有信息的默认模板。
此简介也将作为生成的文件夹或zip文件的默认名称 (若预案名称为空)。
"""
class TabPackSettings:
    def __init__(self, parent):
        self.frame = ttk.Frame(parent, padding="10")
        self.config = config_manager.load_config()
        preset_frame = ttk.LabelFrame(self.frame, text="预案管理", padding=10)
        preset_frame.pack(fill="x", pady=5)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, state="readonly")
        self.preset_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.preset_combo.bind('<MouseWheel>', lambda e: "break")
        self.preset_combo.bind('<<ComboboxSelected>>', lambda e: (self.preset_combo.after_idle(self.preset_combo.selection_clear), self._on_preset_selected(e)))
        preset_btn_frame = ttk.Frame(preset_frame)
        preset_btn_frame.pack(side="left")
        save_btn = ttk.Button(preset_btn_frame, text="保存", command=self._save_preset, bootstyle="primary-outline", width=6)
        save_btn.pack(side="left", padx=2)
        ToolTip(save_btn, "保存当前设置到选中的预案\n如果未选择预案, 会创建一个新的")
        save_as_btn = ttk.Button(preset_btn_frame, text="另存为", command=self._save_as_new_preset, bootstyle="info-outline", width=8)
        save_as_btn.pack(side="left", padx=2)
        ToolTip(save_as_btn, "将当前设置保存为一个新的预案\n预案名称也支持使用动态占位符, 如 '我的整合包_{timestamp}'")
        delete_btn = ttk.Button(preset_btn_frame, text="删除", command=self._delete_preset, bootstyle="danger-outline", width=6)
        delete_btn.pack(side="left", padx=2)
        ToolTip(delete_btn, "删除当前选中的预案")
        metadata_frame = ttk.LabelFrame(self.frame, text="资源包元数据 (pack.mcmeta & pack.png)", padding=10)
        metadata_frame.pack(fill="x", pady=10)
        metadata_frame.columnconfigure(1, weight=1)
        self.pack_format_var = tk.StringVar()
        self.pack_desc_var = tk.StringVar()
        self.pack_icon_var = tk.StringVar()
        ttk.Label(metadata_frame, text="游戏版本 (pack_format):", ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        format_combo = ttk.Combobox(metadata_frame, textvariable=self.pack_format_var, values=list(PACK_FORMATS.keys()), state="readonly")
        format_combo.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(format_combo, "选择汉化包的目标游戏版本\n这将决定pack.mcmeta文件中的pack_format数字")
        format_combo.bind('<MouseWheel>', lambda e: "break")
        format_combo.bind('<<ComboboxSelected>>', lambda e: format_combo.after_idle(format_combo.selection_clear))
        ttk.Label(metadata_frame, text="资源包简介:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        desc_entry = ttk.Entry(metadata_frame, textvariable=self.pack_desc_var)
        desc_entry.grid(row=1, column=1, sticky="ew", padx=5)
        ToolTip(desc_entry, PLACEHOLDER_TOOLTIP_TEXT)
        ttk.Label(metadata_frame, text="资源包图标 (pack.png):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        icon_frame = ttk.Frame(metadata_frame)
        icon_frame.grid(row=2, column=1, sticky="ew")
        icon_frame.columnconfigure(0, weight=1)
        ttk.Entry(icon_frame, textvariable=self.pack_icon_var).grid(row=0, column=0, sticky="ew", padx=5)
        ttk.Button(icon_frame, text="浏览...", bootstyle="primary-outline", command=self._browse_icon).grid(row=0, column=1)
        self.all_vars = [
            self.pack_format_var, self.pack_desc_var,
            self.pack_icon_var
        ]
        for var in self.all_vars:
            var.trace_add("write", self._auto_save)
        self._load_presets()
        self._load_last_used_settings()
    def apply_settings(self, settings_data: dict):
        for var in self.all_vars:
            trace_info = var.trace_info()
            if trace_info:
                var.trace_remove("write", trace_info[0][1])
        self.pack_format_var.set(settings_data.get("pack_format_key", list(PACK_FORMATS.keys())[0]))
        self.pack_desc_var.set(settings_data.get("pack_description", ""))
        self.pack_icon_var.set(settings_data.get("pack_icon_path", ""))
        for var in self.all_vars:
            var.trace_add("write", self._auto_save)
    def _auto_save(self, *args):
        self.get_current_settings()
    def _browse_icon(self):
        path = filedialog.askopenfilename(title="选择一个PNG作为图标", filetypes=[("PNG图片", "*.png"), ("所有文件", "*.*")] )
        if path:
            self.pack_icon_var.set(path)
    def _load_presets(self):
        self.config = config_manager.load_config()
        presets = self.config.get("pack_settings_presets", {})
        self.preset_combo["values"] = list(presets.keys())
    def _load_last_used_settings(self):
        last_settings = self.config.get("last_pack_settings", {})
        self.apply_settings(last_settings)
    def _on_preset_selected(self, event=None):
        preset_name = self.preset_var.get()
        presets = self.config.get("pack_settings_presets", {})
        preset_data = presets.get(preset_name, {})
        self.apply_settings(preset_data)
    def _save_preset(self):
        preset_name = self.preset_var.get()
        if not preset_name:
            self._save_as_new_preset()
            return
        presets = self.config.get("pack_settings_presets", {})
        presets[preset_name] = self.get_current_settings()
        self.config["pack_settings_presets"] = presets
        config_manager.save_config(self.config)
        ui_utils.show_info("成功", f"预案 '{preset_name}' 已保存")
        self._load_presets()
    def _save_as_new_preset(self):
        new_name = simpledialog.askstring("另存为新预案", "请输入新预案的名称:")
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        presets = self.config.get("pack_settings_presets", {})
        if new_name in presets:
            if not ui_utils.show_warning("覆盖预案", f"名为 '{new_name}' 的预案已存在, 要覆盖它吗？"):
                return
        presets[new_name] = self.get_current_settings()
        self.config["pack_settings_presets"] = presets
        config_manager.save_config(self.config)
        self.preset_combo["values"] = list(presets.keys())
        self.preset_var.set(new_name)
        ui_utils.show_info("成功", f"新预案 '{new_name}' 已创建")
    def _delete_preset(self):
        preset_name = self.preset_var.get()
        if not preset_name:
            return
        presets = self.config.get("pack_settings_presets", {})
        if len(presets) <= 1:
            ui_utils.show_error("操作失败", "不能删除最后一个预案")
            return
        if ui_utils.show_warning("确认删除", f"确定要删除预案 '{preset_name}' 吗？此操作无法撤销"):
            presets.pop(preset_name, None)
            self.config["pack_settings_presets"] = presets
            config_manager.save_config(self.config)
            self._load_presets()
            if self.preset_combo["values"]:
                self.preset_var.set(self.preset_combo["values"][0])
                self._on_preset_selected()
    def get_all_presets(self) -> dict:
        self.config = config_manager.load_config()
        return self.config.get("pack_settings_presets", {})
    def get_current_settings(self) -> dict:
        pack_format_key = self.pack_format_var.get()
        current_settings = {
            "pack_format_key": pack_format_key,
            "pack_format": PACK_FORMATS.get(pack_format_key, 3),
            "pack_description": self.pack_desc_var.get(),
            "pack_icon_path": self.pack_icon_var.get(),
        }
        self.config["last_pack_settings"] = current_settings
        config_manager.save_config(self.config)
        return current_settings