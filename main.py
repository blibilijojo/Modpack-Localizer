# main.py

import tkinter as tk
import ttkbootstrap as ttk
import logging
import sys
import os
from pathlib import Path
import time

# 将版本号更新为 1.2.1
__version__ = "1.2.1"

def cleanup_old_files():
    """在程序启动时清理上一次更新留下的临时文件。"""
    try:
        if not getattr(sys, 'frozen', False):
            # 如果不是打包后的exe，则不执行任何操作
            return

        current_exe_path = Path(sys.executable)
        old_file = current_exe_path.with_suffix(current_exe_path.suffix + ".old")

        if old_file.exists():
            logging.info(f"检测到旧版本文件: {old_file}，准备清理...")
            # 增加一点延迟和重试，以防新程序启动太快，旧程序还未完全释放句柄
            time.sleep(1)
            os.remove(old_file)
            logging.info(f"成功删除旧版本文件。")
    except Exception as e:
        # 清理失败不是致命错误，记录日志即可
        logging.warning(f"删除旧版本文件失败，可能需要手动删除: {e}")

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
    # 在最开始执行清理
    cleanup_old_files()

    # 加载配置
    config = load_config()
    
    # 使用 ttkbootstrap Window
    root = ttk.Window(themename="lumen")
    
    # 实例化 MainWindow，它内部会完成日志系统的设置
    app = MainWindow(root) 
    
    # 在主循环开始前，打印一条高级别日志
    logging.info(f"应用程序 v{__version__} 启动成功，主窗口已显示。")
    
    root.mainloop()