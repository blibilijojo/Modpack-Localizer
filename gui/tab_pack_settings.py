import tkinter as tk
from tkinter import simpledialog, filedialog, ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
from utils import config_manager
from gui.custom_widgets import ToolTip

PACK_FORMATS = {
    "1.21 (Format 34)": 34, "1.20.5 - 1.20.6 (Format 32)": 32, "1.20.3 - 1.20.4 (Format 22)": 22,
    "1.20.2 (Format 18)": 18, "1.20 - 1.20.1 (Format 15)": 15, "1.19.4 (Format 13)": 13,
    "1.19.3 (Format 12)": 12, "1.19 - 1.19.2 (Format 9)": 9, "1.18 - 1.18.2 (Format 8)": 8,
    "1.17 - 1.17.1 (Format 7)": 7, "1.16.2 - 1.16.5 (Format 6)": 6, "1.15 - 1.16.1 (Format 5)": 5,
    "1.13 - 1.14.4 (Format 4)": 4, "1.11 - 1.12.2 (Format 3)": 3,
    "1.9 - 1.10.2 (Format 2)": 2, "1.6.1 - 1.8.9 (Format 1)": 1,
}

PLACEHOLDER_TOOLTIP_TEXT = """支持使用动态占位符, 在生成时会自动替换为真实数据:
  - {timestamp}: 生成时间 (格式: YYYYMMDD_HHMMSS)
  - {total}: 翻译条目总数, 等"""

class TabPackSettings:
    def __init__(self, parent_frame):
        self.frame = parent_frame
        self.config = config_manager.load_config()

        preset_frame = tk_ttk.LabelFrame(self.frame, text="预案管理", padding=10)
        preset_frame.pack(fill="x", pady=5)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, state="readonly")
        self.preset_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.preset_combo.bind('<<ComboboxSelected>>', self._on_preset_selected)
        self.preset_combo.bind('<FocusIn>', lambda e: e.widget.selection_clear())
        self.preset_combo.bind('<FocusOut>', lambda e: e.widget.selection_clear())
        
        preset_btn_frame = ttk.Frame(preset_frame)
        preset_btn_frame.pack(side="left")
        save_btn = ttk.Button(preset_btn_frame, text="保存", command=self._save_preset, bootstyle="primary-outline", width=6)
        save_btn.pack(side="left", padx=2)
        save_as_btn = ttk.Button(preset_btn_frame, text="另存为", command=self._save_as_new_preset, bootstyle="info-outline", width=8)
        save_as_btn.pack(side="left", padx=2)
        delete_btn = ttk.Button(preset_btn_frame, text="删除", command=self._delete_preset, bootstyle="danger-outline", width=6)
        delete_btn.pack(side="left", padx=2)

        metadata_frame = tk_ttk.LabelFrame(self.frame, text="预案内容 (pack.mcmeta & pack.png)", padding=10)
        metadata_frame.pack(fill="x", pady=10)
        metadata_frame.columnconfigure(1, weight=1)
        self.pack_format_var = tk.StringVar()
        self.pack_desc_var = tk.StringVar()
        self.pack_icon_var = tk.StringVar()

        ttk.Label(metadata_frame, text="游戏版本:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        format_combo = ttk.Combobox(metadata_frame, textvariable=self.pack_format_var, values=list(PACK_FORMATS.keys()), state="readonly")
        format_combo.grid(row=0, column=1, sticky="ew", padx=5)
        format_combo.bind('<FocusIn>', lambda e: e.widget.selection_clear())
        format_combo.bind('<FocusOut>', lambda e: e.widget.selection_clear())

        ttk.Label(metadata_frame, text="资源包简介:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        desc_entry = ttk.Entry(metadata_frame, textvariable=self.pack_desc_var)
        desc_entry.grid(row=1, column=1, sticky="ew", padx=5)
        ToolTip(desc_entry, PLACEHOLDER_TOOLTIP_TEXT)

        ttk.Label(metadata_frame, text="资源包图标:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        icon_frame = ttk.Frame(metadata_frame)
        icon_frame.grid(row=2, column=1, sticky="ew")
        icon_frame.columnconfigure(0, weight=1)
        ttk.Entry(icon_frame, textvariable=self.pack_icon_var).grid(row=0, column=0, sticky="ew", padx=5)
        ttk.Button(icon_frame, text="浏览...", bootstyle="primary-outline", command=self._browse_icon).grid(row=0, column=1)

        self._load_presets()
        if self.preset_combo["values"]:
            self.preset_var.set(self.preset_combo["values"][0])
            self._on_preset_selected()

    def _apply_settings_to_ui(self, settings_data: dict):
        self.pack_format_var.set(settings_data.get("pack_format_key", list(PACK_FORMATS.keys())[4]))
        self.pack_desc_var.set(settings_data.get("pack_description", ""))
        self.pack_icon_var.set(settings_data.get("pack_icon_path", ""))

    def _get_current_ui_settings(self) -> dict:
        pack_format_key = self.pack_format_var.get()
        return {
            "pack_format_key": pack_format_key,
            "pack_format": PACK_FORMATS.get(pack_format_key, 15),
            "pack_description": self.pack_desc_var.get(),
            "pack_icon_path": self.pack_icon_var.get(),
        }

    def _browse_icon(self):
        path = filedialog.askopenfilename(title="选择PNG图标", filetypes=[("PNG图片", "*.png")])
        if path: self.pack_icon_var.set(path)

    def _load_presets(self):
        self.config = config_manager.load_config()
        presets = self.config.get("pack_settings_presets", {})
        self.preset_combo["values"] = list(presets.keys())

    def _on_preset_selected(self, event=None):
        preset_name = self.preset_var.get()
        presets = self.config.get("pack_settings_presets", {})
        self._apply_settings_to_ui(presets.get(preset_name, {}))

    def _save_preset(self):
        preset_name = self.preset_var.get()
        if not preset_name:
            self._save_as_new_preset()
            return
        
        presets = self.config.get("pack_settings_presets", {})
        presets[preset_name] = self._get_current_ui_settings()
        self.config["pack_settings_presets"] = presets
        config_manager.save_config(self.config)
        ui_utils.show_info("成功", f"预案 '{preset_name}' 已保存")
        self._load_presets()

    def _save_as_new_preset(self):
        new_name = simpledialog.askstring("另存为新预案", "请输入新预案的名称:")
        if not new_name or not new_name.strip(): return
        
        new_name = new_name.strip()
        presets = self.config.get("pack_settings_presets", {})
        if new_name in presets and not ui_utils.show_warning("覆盖预案", f"预案 '{new_name}' 已存在, 要覆盖吗？"):
            return

        presets[new_name] = self._get_current_ui_settings()
        self.config["pack_settings_presets"] = presets
        config_manager.save_config(self.config)
        self.preset_combo["values"] = list(presets.keys())
        self.preset_var.set(new_name)
        ui_utils.show_info("成功", f"新预案 '{new_name}' 已创建")

    def _delete_preset(self):
        preset_name = self.preset_var.get()
        if not preset_name: return
        
        presets = self.config.get("pack_settings_presets", {})
        if len(presets) <= 1:
            ui_utils.show_error("操作失败", "不能删除最后一个预案")
            return

        if ui_utils.show_warning("确认删除", f"确定要删除预案 '{preset_name}' 吗？"):
            presets.pop(preset_name, None)
            self.config["pack_settings_presets"] = presets
            config_manager.save_config(self.config)
            self._load_presets()
            if self.preset_combo["values"]:
                self.preset_var.set(self.preset_combo["values"][0])
            self._on_preset_selected()