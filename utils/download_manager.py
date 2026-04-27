from __future__ import annotations
import logging
import threading
import concurrent.futures
from utils import config_manager

class DownloadManager:

    _instance: DownloadManager | None = None
    _creation_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._creation_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._max_workers = self._get_max_workers()
        self._executor_lock = threading.Lock()

    def _get_max_workers(self) -> int:
        config = config_manager.load_config()
        return config.get('download_threads', 5)

    def get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        with self._executor_lock:
            current_workers = self._get_max_workers()
            if current_workers != self._max_workers or self._executor is None:
                if self._executor:
                    self._executor.shutdown(wait=False)
                self._max_workers = current_workers
                self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers)
                logging.info(f"下载管理器线程池已更新，线程数: {self._max_workers}")
            return self._executor

    def submit(self, fn, *args, **kwargs):
        executor = self.get_executor()
        logging.info(f"提交下载任务到线程池，当前线程数: {self._max_workers}")
        return executor.submit(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True):
        with self._executor_lock:
            if self._executor:
                self._executor.shutdown(wait=wait)
                self._executor = None

    def get_max_workers(self) -> int:
        return self._max_workers

download_manager = DownloadManager()
