import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import os
import sys

# 确保单文件打包兼容性
base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 确保导入路径正确
# 检测是否为打包环境（支持 PyInstaller 和 Nuitka）
is_frozen = getattr(sys, 'frozen', False) or getattr(sys, 'nuitka', False)
if is_frozen:  # 单文件打包环境
    sys.path.append(base_path)
    sys.path.append(os.path.dirname(base_path))
    sys.path.append(os.path.dirname(os.path.dirname(base_path)))
else:  # 非打包环境
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import config_manager
from gui import ui_utils
from gui.settings_components.general_settings import GeneralSettings
from gui.settings_components.ai_settings import AISettings
from gui.settings_components.resource_pack_settings import ResourcePackSettings
from gui.settings_components.external_services_settings import ExternalServicesSettings
from gui.settings_components.advanced_settings import AdvancedSettings
from gui.tab_pack_settings import TabPackSettings

class SettingsWindow(ttk.Toplevel):
    def __init__(self, parent, title="设置", workbench_instance=None, main_window_instance=None):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry("800x750")
        self.minsize(700, 600)
        self.config = config_manager.load_config()
        self.workbench_instance = workbench_instance
        self.main_window_instance = main_window_instance
        self._last_mod_list_name_mode = self.config.get("mod_list_name_mode", "namespace")
        
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
        
        # 绑定选项卡切换事件
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        # 创建各个选项卡，添加异常处理
        tab_creation_methods = [
            self._create_general_tab,
            self._create_ai_tab,
            self._create_translation_resources_tab,
            self._create_external_services_tab,
            self._create_pack_config_tab,
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
        
    def _create_general_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 通用 ")
        self.general_settings = GeneralSettings(tab, self.config, self._save_config)
    
    def _create_ai_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" AI翻译 ")
        self.ai_settings = AISettings(tab, self.config, self._save_config)
    
    def _create_translation_resources_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 翻译资源 ")
        self.resource_pack_settings = ResourcePackSettings(tab, self.config, self._save_config)
    
    def _create_pack_config_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 资源包配置 ")
        self.pack_settings_manager = TabPackSettings(tab)
    
    def _create_external_services_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 外部服务 ")
        self.external_services_settings = ExternalServicesSettings(tab, self.config, self._save_config)

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
            
            # 仅当名称显示模式变更时，刷新所有已加载的 workbench
            new_mode = self.config.get("mod_list_name_mode", "namespace")
            if new_mode != self._last_mod_list_name_mode:
                self._last_mod_list_name_mode = new_mode
                self._notify_all_workbenches_namespace_displays()
        except Exception as e:
            ui_utils.show_error("保存失败", f"保存配置时发生错误：{str(e)}")

    def _notify_all_workbenches_namespace_displays(self):
        """刷新所有已加载的 TranslationWorkbench 列表名称显示。"""
        candidates = []
        seen_ids = set()

        if self.workbench_instance and hasattr(self.workbench_instance, "update_all_namespace_displays"):
            candidates.append(self.workbench_instance)

        main = getattr(self, "main_window_instance", None)
        if main and hasattr(main, "project_tabs"):
            for tab in main.project_tabs.values():
                wb = getattr(tab, "workbench_instance", None)
                if wb and hasattr(wb, "update_all_namespace_displays"):
                    candidates.append(wb)

        for wb in candidates:
            wb_id = id(wb)
            if wb_id in seen_ids:
                continue
            seen_ids.add(wb_id)
            wb.update_all_namespace_displays()
    
    def _collect_all_configs(self):
        """从所有设置组件收集配置"""
        # 收集通用设置
        if hasattr(self, 'general_settings'):
            self.config.update(self.general_settings.get_config())
        
        # 收集 AI 设置
        if hasattr(self, 'ai_settings'):
            self.config.update(self.ai_settings.get_config())
        
        # 收集翻译资源设置
        if hasattr(self, 'resource_pack_settings'):
            self.config.update(self.resource_pack_settings.get_config())
        
        # 收集外部服务设置
        if hasattr(self, 'external_services_settings'):
            self.config.update(self.external_services_settings.get_config())

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
    
    def _on_tab_changed(self, event):
        """选项卡切换时的处理"""
        # 获取当前选中的选项卡
        current_tab_id = self.notebook.select()
        # 将选项卡ID转换为widget对象
        current_tab = self.notebook.nametowidget(current_tab_id)
        # 清除当前选项卡中所有Entry组件的文本选中状态
        self._clear_entry_selections(current_tab)
    
    def _clear_entry_selections(self, widget):
        """递归清除widget及其子widget中所有Entry的文本选中状态"""
        if isinstance(widget, (ttk.Entry, tk.Entry)):
            widget.after_idle(widget.selection_clear)
        for child in widget.winfo_children():
            self._clear_entry_selections(child)
    
    def destroy(self):
        """关闭窗口时保存配置"""
        self._save_config()
        super().destroy()
