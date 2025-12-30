import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from utils import config_manager

class LevelFilter(logging.Filter):
    def __init__(self, level):
        super().__init__()
        self.level = level
    def filter(self, record):
        return record.levelno == self.level

def cleanup_old_logs(logs_dir, days=10):
    """
    清理指定天数前的旧日志文件
    Args:
        logs_dir: 日志文件夹路径
        days: 保留日志的天数
    """
    logs_dir = Path(logs_dir)
    if not logs_dir.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for log_file in logs_dir.glob("*.log"):
        try:
            # 获取文件创建时间
            file_time = datetime.fromtimestamp(log_file.stat().st_ctime)
            # 如果文件超过指定天数，删除
            if file_time < cutoff_date:
                log_file.unlink()
                logging.debug(f"已删除旧日志文件: {log_file}")
        except Exception as e:
            logging.error(f"清理旧日志时出错: {e}")

def setup_logging(gui_callback=None):
    """
    配置日志系统
    Args:
        gui_callback: GUI日志回调函数
    """
    # 创建日志文件夹
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # 生成日志文件名（使用当前时间）
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = logs_dir / f"ModpackLocalizer_{current_time}.log"
    
    # 清理10天前的旧日志
    cleanup_old_logs(logs_dir, days=10)
    
    # 加载配置
    config = config_manager.load_config()
    log_level_str = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # 配置第三方库日志级别
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # 移除现有处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 定义日志格式
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - %(message)s',
        datefmt='%H:%M:%S'
    )
    gui_formatter = logging.Formatter('%(message)s')
    
    # 文件处理器
    file_handler = logging.FileHandler(
        log_filename, mode='a', encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # GUI处理器（如果提供）
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
    
    logging.info(f"日志系统初始化完成。文件日志路径: {log_filename}")
    logging.info(f"文件日志级别设置为: {log_level_str}")
    logging.info(f"系统将自动清理10天前的日志文件")