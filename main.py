# main.py

import tkinter as tk
import ttkbootstrap as ttk
import logging
import sys
from pathlib import Path

# 将项目根目录添加到Python的模块搜索路径中
try:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
except NameError:
    script_dir = Path.cwd()
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

# 导入新的日志设置函数和主窗口
from utils.logger_setup import setup_logging
from gui.main_window import MainWindow
from utils.config_manager import load_config

if __name__ == '__main__':
    # 加载配置
    config = load_config()
    
    # 使用 ttkbootstrap Window
    root = ttk.Window(themename="lumen")
    
    # 实例化 MainWindow，它内部会完成日志系统的设置
    app = MainWindow(root) 
    
    # 在主循环开始前，打印一条高级别日志
    logging.info("应用程序启动成功，主窗口已显示。")
    
    root.mainloop()
