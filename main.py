# main.py

import tkinter as tk
import ttkbootstrap as ttk
import logging
import sys
import os
from pathlib import Path
import time

from _version import __version__

def cleanup_old_files():
    """在程序启动时清理上一次更新留下的临时文件。"""
    try:
        if not getattr(sys, 'frozen', False):
            return

        current_exe_path = Path(sys.executable)
        old_file = current_exe_path.with_suffix(current_exe_path.suffix + ".old")

        if old_file.exists():
            logging.info(f"检测到旧版本文件: {old_file}，准备清理...")
            time.sleep(1)
            os.remove(old_file)
            logging.info(f"成功删除旧版本文件。")
    except Exception as e:
        logging.warning(f"删除旧版本文件失败，可能需要手动删除: {e}")

try:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
except NameError:
    script_dir = Path.cwd()
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

from utils.logger_setup import setup_logging
from utils.config_manager import load_config
from gui.main_window import MainWindow

if __name__ == '__main__':
    cleanup_old_files()
    config = load_config()
    root = ttk.Window(themename="lumen")
    app = MainWindow(root) 
    logging.info(f"应用程序 v{__version__} 启动成功，主窗口已显示。")
    root.mainloop()