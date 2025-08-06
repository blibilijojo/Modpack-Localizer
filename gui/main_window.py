# gui/main_window.py

import tkinter as tk
import ttkbootstrap as ttk
import logging
from gui.tab_main_control import TabMainControl
from gui.tab_ai_service import TabAiService
from gui.tab_ai_parameters import TabAiParameters
from gui.tab_pack_settings import TabPackSettings
# 导入新的日志设置函数
from utils.logger_setup import setup_logging

class MainWindow:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("Minecraft 整合包汉化工坊 Pro")
        # --- MODIFIED: Adjusted window height and minsize ---
        self.root.geometry("850x950") 
        self.root.minsize(800, 850)

        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        notebook_frame = ttk.Frame(main_pane)
        main_pane.add(notebook_frame, weight=1)

        notebook = ttk.Notebook(notebook_frame)
        notebook.pack(fill="both", expand=True)

        # --- 创建四个选项卡的实例 ---
        ai_service_tab = TabAiService(notebook)
        ai_parameters_tab = TabAiParameters(notebook)
        pack_settings_tab = TabPackSettings(notebook)
        main_control_tab = TabMainControl(notebook, ai_service_tab, ai_parameters_tab, pack_settings_tab)

        # --- 按新顺序添加到 Notebook ---
        notebook.add(main_control_tab.frame, text=" 一键汉化 ")
        notebook.add(ai_service_tab.frame, text=" AI 服务 ")
        notebook.add(ai_parameters_tab.frame, text=" AI 参数 ")
        notebook.add(pack_settings_tab.frame, text=" 资源包设置 ")

        main_pane.add(main_control_tab.get_log_frame(), weight=1)

        # --- 将日志设置的调用放在这里 ---
        # 这样可以确保 main_control_tab.log_message 已经存在并可以作为回调函数传递
        setup_logging(main_control_tab.log_message)