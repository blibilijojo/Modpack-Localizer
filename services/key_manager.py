from __future__ import annotations
import logging
import queue
import threading
import time
import asyncio
from collections.abc import Callable


class KeyManager:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("至少需要一个有效的API密钥")
        self.available_keys = queue.Queue()
        for key in api_keys:
            self.available_keys.put(key)
        self.cooldown_keys = {}
        self.lock = threading.Lock()
        logging.info(f"密钥管理器已初始化，可用密钥数量: {self.available_keys.qsize()}")

    def _check_cooldowns(self):
        with self.lock:
            current_time = time.monotonic()
            keys_to_reactivate = [key for key, end_time in self.cooldown_keys.items() if current_time >= end_time]
            for key in keys_to_reactivate:
                del self.cooldown_keys[key]
                self.available_keys.put(key)
                logging.info(f"密钥 ...{key[-4:]} 已结束冷却，回归可用队列。")

    def get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        while True:
            self._check_cooldowns()
            try:
                key = self.available_keys.get(timeout=0.1)
                return key
            except queue.Empty:
                if should_abort and should_abort():
                    return None
                time.sleep(0.5)

    def release_key(self, key: str):
        self.available_keys.put(key)

    def penalize_key(self, key: str, cooldown_seconds: int):
        with self.lock:
            cooldown_end_time = time.monotonic() + cooldown_seconds
            self.cooldown_keys[key] = cooldown_end_time
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")

    async def async_get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        while True:
            self._check_cooldowns()
            try:
                key = self.available_keys.get(block=False)
                return key
            except queue.Empty:
                if should_abort and should_abort():
                    return None
                await asyncio.sleep(0.5)

    async def async_release_key(self, key: str):
        self.available_keys.put(key)

    async def async_penalize_key(self, key: str, cooldown_seconds: int):
        with self.lock:
            cooldown_end_time = time.monotonic() + cooldown_seconds
            self.cooldown_keys[key] = cooldown_end_time
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
