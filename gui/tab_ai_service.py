# gui/tab_ai_service.py

import tkinter as tk
import ttkbootstrap as ttk
from tkinter import scrolledtext
from utils import config_manager
from gui.custom_widgets import ToolTip

class TabAiService:
    def __init__(self, parent):
        self.frame = ttk.Frame(parent, padding="10")
        self.config = config_manager.load_config()

        # --- UI Construction ---
        service_frame = ttk.LabelFrame(self.frame, text="AI 服务设置 (连接到Gemini)", padding=10)
        service_frame.pack(fill="x", expand=False, pady=(0, 10))

        api_label = ttk.Label(service_frame, text="Gemini API 密钥 (每行一个):")
        api_label.pack(anchor="w")
        ToolTip(api_label, "从 Google AI Studio 获取的API密钥\n可以填入多个，程序会在请求失败时自动轮换使用")
        self.api_keys_text = scrolledtext.ScrolledText(service_frame, height=4, width=60)
        self.api_keys_text.pack(fill="x", expand=True, pady=2)
        
        endpoint_label = ttk.Label(service_frame, text="自定义API服务器地址 (兼容OpenAI):")
        endpoint_label.pack(anchor="w", pady=(5, 0))
        ToolTip(endpoint_label, "可选。如果你使用了代理或第三方兼容Gemini的API服务，请在此处填写其地址\n例如: https://api.proxy.com/v1")
        self.api_endpoint_var = tk.StringVar()
        ttk.Entry(service_frame, textvariable=self.api_endpoint_var).pack(fill="x", pady=2)

        # --- Load and Bind ---
        self._load_settings_to_ui()
        self._bind_events()
    
    def _load_settings_to_ui(self):
        """Loads settings from config into the UI."""
        self.config = config_manager.load_config()
        self.api_keys_text.delete("1.0", tk.END)
        self.api_keys_text.insert(tk.END, "\n".join(self.config.get("api_keys", [])))
        self.api_endpoint_var.set(self.config.get("api_endpoint", ""))

    def _bind_events(self):
        """Binds all auto-save events."""
        self.api_keys_text.bind("<KeyRelease>", lambda e: self.get_and_save_settings())
        self.api_endpoint_var.trace_add("write", lambda *args: self.get_and_save_settings())

    def get_and_save_settings(self) -> dict:
        """Reads settings from UI, saves them, and returns them."""
        service_settings = {
            "api_keys": [k.strip() for k in self.api_keys_text.get("1.0", tk.END).strip().split('\n') if k.strip()],
            "api_endpoint": self.api_endpoint_var.get().strip(),
        }
        full_config = config_manager.load_config()
        full_config.update(service_settings)
        config_manager.save_config(full_config)
        self.config = full_config
        return service_settings