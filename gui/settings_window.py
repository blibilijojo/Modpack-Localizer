import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import os
import sys

# 确保单文件打包兼容性
base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 确保导入路径正确
if not hasattr(sys, 'frozen'):  # 非打包环境
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import config_manager
from gui import ui_utils
from gui.settings_components.basic_settings import BasicSettings
from gui.settings_components.ai_settings import AISettings
from gui.settings_components.resource_pack_settings import ResourcePackSettings

from gui.settings_components.advanced_settings import AdvancedSettings
from gui.tab_pack_settings import TabPackSettings

class SettingsWindow(ttk.Toplevel):
    def __init__(self, parent, title="设置"):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry("800x750")
        self.minsize(700, 600)
        self.config = config_manager.load_config()
        
        # 添加加载状态
        self.loading = False
        self.loading_label = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建选项卡控件
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # 创建各个选项卡，添加异常处理
        tab_creation_methods = [
            self._create_basic_tab,
            self._create_ai_tab,
            self._create_resource_pack_tab,
            self._create_pack_settings_tab,
            self._create_advanced_tab
        ]
        
        for method in tab_creation_methods:
            try:
                method()
            except Exception as e:
                print(f"创建选项卡失败 {method.__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                # 记录错误但继续执行，确保其他选项卡能正常显示
        
    def _create_basic_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 基础设置 ")
        self.basic_settings = BasicSettings(tab, self.config, self._save_config)
    
    def _create_ai_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" AI 翻译 ")
        self.ai_settings = AISettings(tab, self.config, self._save_config)
    
    def _create_resource_pack_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 资源包 ")
        self.resource_pack_settings = ResourcePackSettings(tab, self.config, self._save_config)
    
    def _create_pack_settings_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 生成预案 ")
        self.pack_settings_manager = TabPackSettings(tab)
    

    
    def _create_advanced_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 高级 ")
        self.advanced_settings = AdvancedSettings(tab, self.config, self._save_config)
    
    def _save_config(self, updated_config=None):
        """保存配置"""
        try:
            if updated_config:
                self.config.update(updated_config)
            else:
                # 从所有组件收集配置
                self._collect_all_configs()
            
            config_manager.save_config(self.config)
        except Exception as e:
            ui_utils.show_error("保存失败", f"保存配置时发生错误：{str(e)}")
    
    def _collect_all_configs(self):
        """从所有设置组件收集配置"""
        # 收集基础设置
        if hasattr(self, 'basic_settings'):
            self.config.update(self.basic_settings.get_config())
        
        # 收集AI设置
        if hasattr(self, 'ai_settings'):
            self.config.update(self.ai_settings.get_config())
        
        # 收集资源包设置
        if hasattr(self, 'resource_pack_settings'):
            self.config.update(self.resource_pack_settings.get_config())
        

        
        # 收集高级设置
        if hasattr(self, 'advanced_settings'):
            self.config.update(self.advanced_settings.get_config())
    
    def _show_loading(self, message="加载中..."):
        """显示加载状态"""
        if self.loading_label:
            self.loading_label.destroy()
        self.loading_label = ttk.Label(self, text=message, bootstyle="primary")
        self.loading_label.pack(pady=10)
        self.loading = True
        self.update_idletasks()
        
    def _hide_loading(self):
        """隐藏加载状态"""
        if self.loading_label:
            self.loading_label.destroy()
            self.loading_label = None
        self.loading = False
        self.update_idletasks()
    
    def destroy(self):
        """关闭窗口时保存配置"""
        self._save_config()
        super().destroy()
