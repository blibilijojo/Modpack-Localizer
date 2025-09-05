# utils/retry_logic.py

import time
import random
import logging
import itertools
from typing import Callable, Any, Type
from functools import wraps

try:
    from openai import RateLimitError, APIError
    RETRY_EXCEPTIONS = (RateLimitError, APIError, ValueError) 
    RATE_LIMIT_EXCEPTIONS = (RateLimitError,)
except ImportError:
    RETRY_EXCEPTIONS = (Exception,)
    RATE_LIMIT_EXCEPTIONS = ()

class RateLimitTracker:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.consecutive_rate_limits = 0
        self.base_delay = 1.0
        self.max_delay = 300.0

    def is_rate_limit_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        if RATE_LIMIT_EXCEPTIONS and isinstance(error, RATE_LIMIT_EXCEPTIONS):
            return True
        return any(phrase in error_str for phrase in ["rate limit", "too many requests", "429", "quota exceeded"])

    def record_rate_limit_and_get_delay(self) -> float:
        self.consecutive_rate_limits += 1
        delay = self.base_delay * (2 ** (self.consecutive_rate_limits - 1))
        jitter = random.uniform(0, 1)
        final_delay = min(delay, self.max_delay) + jitter
        logging.warning(f"服务 {self.service_name} 遭遇速率限制 (第 {self.consecutive_rate_limits} 次)。将在 {final_delay:.2f} 秒后重试。")
        return final_delay

    def record_success(self):
        if self.consecutive_rate_limits > 0:
            logging.info(f"服务 {self.service_name} 的API调用成功，重置速率限制计数器。")
            self.consecutive_rate_limits = 0

def professional_retry(
    initial_delay: float = 1.0,
    on_failure_callback: Callable = None
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            rate_limiter = RateLimitTracker(func.__name__)
            
            for attempt in itertools.count(1):
                try:
                    result = func(*args, **kwargs)
                    rate_limiter.record_success()
                    return result
                except RETRY_EXCEPTIONS as e:
                    if on_failure_callback:
                        try:
                            if on_failure_callback() is False:
                                logging.critical(f"失败回调函数 ({on_failure_callback.__name__}) 已无可用选项，终止重试。")
                                raise e
                        except Exception as cb_exc:
                            logging.error(f"on_failure_callback 执行失败: {cb_exc}")

                    delay = 0.0
                    if rate_limiter.is_rate_limit_error(e):
                        delay = rate_limiter.record_rate_limit_and_get_delay()
                    elif isinstance(e, ValueError):
                        delay = 0.1
                        logging.warning(f"函数 {func.__name__} 遭遇内容格式错误，将立即重试。")
                    else:
                        delay = initial_delay * (2 ** min(attempt, 8)) + random.uniform(0, 1)
                        logging.warning(f"函数 {func.__name__} 遭遇临时错误 (尝试 #{attempt}): {e}")
                        logging.info(f"将在 {delay:.2f} 秒后进行常规重试。")

                    time.sleep(delay)
        return wrapper
    return decorator