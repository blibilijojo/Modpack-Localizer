import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk

class CurseForgeSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback

        self._create_variables()

        self._create_widgets()

    def _create_variables(self):
        self.api_key_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)

        self._load_config()
        self._bind_events()

    def _bind_events(self):
        self.api_key_var.trace_add("write", lambda *args: self._save_settings())

    def _load_config(self):
        self.api_key_var.set(self.config.get('curseforge_api_key', ''))

    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._create_basic_settings(main_frame)

    def _create_basic_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="CurseForge API 设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)

        info_label = ttk.Label(frame, 
            text="官方版本已内置 API 密钥，可直接使用；\n如为自行构建或使用单文件版本，请自行输入密钥。", 
            bootstyle="secondary")
        info_label.pack(anchor="w", pady=(0, 10))

        key_frame = ttk.Frame(frame)
        key_frame.pack(fill="x", pady=5)
        key_frame.columnconfigure(1, weight=1)

        ttk.Label(key_frame, text="API密钥:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, show="*")
        self.key_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.key_entry.after_idle(self.key_entry.selection_clear)

        self.show_key_btn = ttk.Checkbutton(key_frame, text="显示密钥", variable=self.show_key_var, command=self._toggle_key_visibility)
        self.show_key_btn.grid(row=0, column=2, sticky="w", padx=5, pady=5)

        help_frame = tk_ttk.LabelFrame(parent, text="获取API密钥", padding="10")
        help_frame.pack(fill="x", pady=(0, 10), padx=5)

        help_text = (
            "1. 访问 https://console.curseforge.com 注册账号\n"
            "2. 在 API Keys 页面创建新的API密钥\n"
            "3. 复制密钥并粘贴到上方输入框中"
        )
        help_label = ttk.Label(help_frame, text=help_text, bootstyle="secondary")
        help_label.pack(anchor="w")

    def _toggle_key_visibility(self):
        if self.show_key_var.get():
            self.key_entry.config(show="")
        else:
            self.key_entry.config(show="*")

    def _save_settings(self):
        api_key = self.api_key_var.get().strip()
        
        # 检查是否为内置密钥
        is_builtin = False
        try:
            from utils.builtin_secrets import get_builtin_curseforge_key
            if get_builtin_curseforge_key() and api_key == get_builtin_curseforge_key():
                is_builtin = True
        except ImportError:
            pass
        
        # 如果是内置密钥，不触发保存（因为会被 config_manager 拦截）
        if is_builtin:
            return
        
        curseforge_config = {
            'curseforge_api_key': api_key
        }

        self.config.update(curseforge_config)

        self.save_callback(curseforge_config)

    def get_config(self):
        return {
            'curseforge_api_key': self.api_key_var.get().strip()
        }