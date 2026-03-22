import logging
import threading
import concurrent.futures
from utils import config_manager

class DownloadManager:
    """下载管理器，使用多线程处理下载任务"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DownloadManager, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化下载管理器"""
        self._executor = None
        self._max_workers = self._get_max_workers()
        self._lock = threading.Lock()
    
    def _get_max_workers(self):
        """获取最大工作线程数"""
        config = config_manager.load_config()
        return config.get('download_threads', 5)
    
    def get_executor(self):
        """获取线程池执行器"""
        with self._lock:
            # 检查线程数是否有变化
            current_workers = self._get_max_workers()
            if current_workers != self._max_workers or self._executor is None:
                # 关闭旧的执行器
                if self._executor:
                    self._executor.shutdown(wait=False)
                # 创建新的执行器
                self._max_workers = current_workers
                self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers)
                logging.info(f"下载管理器线程池已更新，线程数: {self._max_workers}")
            return self._executor
    
    def submit(self, fn, *args, **kwargs):
        """提交下载任务"""
        executor = self.get_executor()
        logging.info(f"提交下载任务到线程池，当前线程数: {self._max_workers}")
        return executor.submit(fn, *args, **kwargs)
    
    def shutdown(self, wait=True):
        """关闭线程池"""
        with self._lock:
            if self._executor:
                self._executor.shutdown(wait=wait)
                self._executor = None
    
    def get_max_workers(self):
        """获取当前最大工作线程数"""
        return self._max_workers

# 全局下载管理器实例
download_manager = DownloadManager()
