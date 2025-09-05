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

def cleanup_stale_log_lock(base_dir: Path):
    """
    在日志系统初始化之前，检查并清理可能残留的日志锁文件。
    使用程序基础目录以确保路径准确。
    """
    try:
        lock_file_path = base_dir / "ModpackLocalizer.log.lock"
        if lock_file_path.exists():
            print(f"[PRE-LOG] 检测到残留的日志锁文件: {lock_file_path}，正在尝试移除...")
            os.remove(lock_file_path)
            print("[PRE-LOG] 成功移除旧的日志锁文件。")
    except PermissionError:
         print(f"[PRE-LOG] 无法移除旧的日志锁文件，它可能正被另一个进程占用。请检查任务管理器。")
    except Exception as e:
        print(f"[PRE-LOG] 移除旧的日志锁文件时出错: {e}")


# 尽早确定脚本目录，以便清理函数使用
try:
    script_dir = Path(__file__).resolve().parent
except NameError:
    script_dir = Path.cwd()

if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from utils.logger_setup import setup_logging
from utils.config_manager import load_config
from gui.main_window import MainWindow

if __name__ == '__main__':
    cleanup_old_files()
    cleanup_stale_log_lock(script_dir)  # <-- 使用更可靠的 script_dir
    
    config = load_config()
    root = ttk.Window(themename="lumen")
    app = MainWindow(root) 
    logging.info(f"应用程序 v{__version__} 启动成功，主窗口已显示。")
    root.mainloop()