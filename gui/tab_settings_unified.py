from __future__ import annotations
import ttkbootstrap as ttk
from gui.settings_components.basic_settings import BasicSettings
from gui.settings_components.ai_settings import AISettings
from gui.settings_components.resource_pack_settings import ResourcePackSettings
from gui.tab_pack_settings import TabPackSettings
from gui.settings_components.advanced_settings import AdvancedSettings
from utils import config_manager


class UnifiedSettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.config = config_manager.load_config()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.basic_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.ai_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.resource_pack_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.pack_settings_tab_frame = ttk.Frame(self.notebook)
        self.advanced_tab_frame = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.basic_tab_frame, text=" 基础设置 ")
        self.notebook.add(self.ai_tab_frame, text=" AI 翻译 ")
        self.notebook.add(self.resource_pack_tab_frame, text=" 资源包 ")
        self.notebook.add(self.pack_settings_tab_frame, text=" 生成预案 ")
        self.notebook.add(self.advanced_tab_frame, text=" 高级 ")

        self.basic_settings = BasicSettings(self.basic_tab_frame, self.config, self._save_config)
        self.ai_settings = AISettings(self.ai_tab_frame, self.config, self._save_config)
        self.resource_pack_settings = ResourcePackSettings(self.resource_pack_tab_frame, self.config, self._save_config)
        self.pack_settings = TabPackSettings(self.pack_settings_tab_frame, self.config, self._save_config)
        self.advanced_settings = AdvancedSettings(self.advanced_tab_frame, self.config, self._save_config)

    def _save_config(self, updates=None):
        if updates:
            self.config.update(updates)
        self.config.update(self.basic_settings.get_config())
        self.config.update(self.ai_settings.get_config())
        self.config.update(self.resource_pack_settings.get_config())
        self.config.update(self.pack_settings.get_config())
        self.config.update(self.advanced_settings.get_config())
        config_manager.save_config(self.config)
