import logging
import sys
# from logging.handlers import RotatingFileHandler  <-- 移除旧的导入
from concurrent_log_handler import ConcurrentRotatingFileHandler # <-- 导入新的、线程安全的处理器

# 自定义一个只传递特定级别日志的过滤器
class LevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno == self.level

def setup_logging(gui_callback=None):
    """
    配置全局日志系统，包含三个处理器：GUI, Console, File。
    """
    # 1. 获取根记录器，并设置最低级别为 DEBUG
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 2. 清除所有之前可能存在的处理器，避免日志重复输出
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 3. 创建格式化器
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - %(message)s',
        datefmt='%H:%M:%S'
    )
    gui_formatter = logging.Formatter('%(message)s')

    # 4. 创建并配置处理器

    # --- 文件处理器 (FileHandler) ---
    # 使用 ConcurrentRotatingFileHandler 替换 RotatingFileHandler
    # 它通过文件锁机制，确保在多线程环境下日志滚动操作的原子性和安全性。
    file_handler = ConcurrentRotatingFileHandler(
        'ModpackLocalizer.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # --- 控制台处理器 (StreamHandler) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # --- GUI 处理器 (如果提供了回调函数) ---
    if gui_callback:
        class GuiHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
            
            def emit(self, record):
                msg = self.format(record)
                self.callback(msg, record.levelname)

        gui_handler = GuiHandler(gui_callback)
        gui_handler.setLevel(logging.INFO)
        gui_handler.setFormatter(gui_formatter)
        root_logger.addHandler(gui_handler)

    logging.info("日志系统初始化完成。日志将同时输出到控制台、GUI和 ModpackLocalizer.log 文件。")