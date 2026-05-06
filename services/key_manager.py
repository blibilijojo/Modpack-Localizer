from __future__ import annotations
import logging
import threading
import asyncio
import time
from collections.abc import Callable


class KeyManager:
    def __init__(self, api_keys: list[str], disable_cooldown: bool = False):
        if not api_keys:
            raise ValueError("至少需要一个有效的API密钥")
        self._all_keys: list[str] = list(api_keys)
        self._available: set[str] = set(api_keys)
        self._cooldowns: dict[str, float] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._async_queue: asyncio.Queue[str] | None = None
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._disable_cooldown = disable_cooldown
        mode_desc = "禁用冷却（多线程并发模式）" if disable_cooldown else "标准模式"
        logging.info(f"密钥管理器已初始化，可用密钥数量: {len(api_keys)}, 模式: {mode_desc}")

    def _check_cooldowns_locked(self):
        current_time = time.monotonic()
        reactivated = [k for k, end in self._cooldowns.items() if current_time >= end]
        for key in reactivated:
            del self._cooldowns[key]
            self._available.add(key)
            logging.info(f"密钥 ...{key[-4:]} 已结束冷却，回归可用集合。")

    def get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        with self._condition:
            while True:
                self._check_cooldowns_locked()
                if self._available:
                    key = next(iter(self._available))
                    return key
                if should_abort and should_abort():
                    return None
                self._condition.wait(timeout=0.5)

    def release_key(self, key: str):
        with self._condition:
            if key not in self._cooldowns:
                self._available.add(key)
            self._condition.notify()

    def penalize_key(self, key: str, cooldown_seconds: float):
        if self._disable_cooldown:
            logging.info(f"密钥 ...{key[-4:]} 调用失败，但冷却已禁用，密钥保持可用。")
            return
        with self._condition:
            cooldown_end = time.monotonic() + cooldown_seconds
            self._cooldowns[key] = cooldown_end
            self._available.discard(key)
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
            self._condition.notify()

    def _ensure_async_queue(self, loop: asyncio.AbstractEventLoop):
        if self._async_queue is None or self._async_loop is not loop:
            self._async_queue = asyncio.Queue()
            self._async_loop = loop
            with self._lock:
                for key in self._available:
                    self._async_queue.put_nowait(key)

    async def async_get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        loop = asyncio.get_running_loop()
        self._ensure_async_queue(loop)

        while True:
            with self._lock:
                self._check_cooldowns_locked()
                available_now = set(self._available)

            if self._async_queue.empty():
                for key in available_now:
                    try:
                        self._async_queue.put_nowait(key)
                    except asyncio.QueueFull:
                        break

            try:
                key = self._async_queue.get_nowait()
                with self._lock:
                    if key in self._available:
                        self._available.discard(key)
                        return key
                    elif key not in self._cooldowns:
                        self._available.discard(key)
                        return key
                continue
            except asyncio.QueueEmpty:
                pass

            if should_abort and should_abort():
                return None
            await asyncio.sleep(0.5)

    async def async_release_key(self, key: str):
        with self._condition:
            if key not in self._cooldowns:
                self._available.add(key)
            self._condition.notify()
        if self._async_queue is not None:
            try:
                self._async_queue.put_nowait(key)
            except asyncio.QueueFull:
                pass

    async def async_penalize_key(self, key: str, cooldown_seconds: float):
        if self._disable_cooldown:
            logging.info(f"密钥 ...{key[-4:]} 调用失败，但冷却已禁用，密钥保持可用。")
            return
        with self._condition:
            cooldown_end = time.monotonic() + cooldown_seconds
            self._cooldowns[key] = cooldown_end
            self._available.discard(key)
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
            self._condition.notify()
