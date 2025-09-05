# utils/logger_setup.py

import logging
import sys
from concurrent_log_handler import ConcurrentRotatingFileHandler
from utils import config_manager

class LevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno == self.level

def setup_logging(gui_callback=None):
    config = config_manager.load_config()
    log_level_str = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # --- 【新增】将第三方库的日志记录器级别调高，以屏蔽其 INFO 级输出 ---
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # --- 修改结束 ---

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - %(message)s',
        datefmt='%H:%M:%S'
    )
    gui_formatter = logging.Formatter('%(message)s')

    file_handler = ConcurrentRotatingFileHandler(
        'ModpackLocalizer.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

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

    logging.info(f"日志系统初始化完成。文件日志级别设置为: {log_level_str}")