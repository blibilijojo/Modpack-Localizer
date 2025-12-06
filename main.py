import ttkbootstrap as ttk
import sys
import logging
from gui.main_window import MainWindow
from utils import config_manager
from utils.error_logger import ErrorLogger

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
