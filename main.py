import ttkbootstrap as ttk
import sys
import logging
import os
import time
from pathlib import Path
from gui.main_window import MainWindow
from utils import config_manager
from utils.error_logger import ErrorLogger

# 清理旧文件

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

# 设置全局异常处理器
def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # 忽略键盘中断，正常退出
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 记录未处理的异常
    ErrorLogger.log_general_error(
        error_title="未处理的异常",
        error_message=str(exc_value),
        exception=exc_value,
        error_level="CRITICAL"
    )
    
    # 使用默认的异常处理器显示错误
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# 注册全局异常处理器
sys.excepthook = handle_unhandled_exception

def main():
    """
    应用程序主入口点。
    """
    # 清理旧文件
    cleanup_old_files()
    
    # 固定使用亮色主题，不再支持主题切换
    theme_name = "litera"
    
    try:
        root = ttk.Window(themename=theme_name)
        app = MainWindow(root)
        
        root.mainloop()
    except Exception as e:
        # 捕获主程序中的异常
        ErrorLogger.log_general_error(
            error_title="主程序异常",
            error_message=str(e),
            exception=e,
            error_level="CRITICAL"
        )
        # 显示错误信息给用户
        import tkinter.messagebox as messagebox
        messagebox.showerror(
            "程序错误",
            f"程序发生严重错误，已退出。\n\n错误信息: {str(e)}\n\n详细日志已保存到错误日志文件夹。"
        )

if __name__ == "__main__":
    main()
