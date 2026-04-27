from __future__ import annotations
import ttkbootstrap as ttk
import sys
import logging
import os
import time
from pathlib import Path
from gui.main_window import MainWindow
from utils import config_manager
from utils.error_logger import ErrorLogger
from utils.file_utils import is_frozen as _is_frozen


def cleanup_old_files():
    try:
        if not _is_frozen():
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


def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    ErrorLogger.log_general_error(
        error_title="未处理的异常",
        error_message=str(exc_value),
        exception=exc_value,
        error_level="CRITICAL"
    )

    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = handle_unhandled_exception


def main():
    cleanup_old_files()

    theme_name = "litera"

    try:
        root = ttk.Window(themename=theme_name)
        app = MainWindow(root)

        root.mainloop()
    except Exception as e:
        ErrorLogger.log_general_error(
            error_title="主程序异常",
            error_message=str(e),
            exception=e,
            error_level="CRITICAL"
        )
        import tkinter.messagebox as messagebox
        messagebox.showerror(
            "程序错误",
            f"程序发生严重错误，已退出。\n\n错误信息: {str(e)}\n\n详细日志已保存到错误日志文件夹。"
        )


if __name__ == "__main__":
    main()
