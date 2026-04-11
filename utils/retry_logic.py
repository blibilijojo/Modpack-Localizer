import time
import random
import logging
import itertools
import requests
from typing import Callable, Any, Type
from functools import wraps


def api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0):
    """
    针对 requests 的 HTTP 调用重试（超时、连接错误、429 与 5xx）。

    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        backoff_factor: 退避因子
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
                        jitter = random.uniform(0, 0.5)
                        sleep_time = delay + jitter
                        logging.warning(
                            f"API请求超时 ({func.__name__}, 尝试 {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        logging.info(f"将在 {sleep_time:.2f} 秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logging.error(
                            f"API请求超时，已达到最大重试次数 ({max_retries + 1}): {e}"
                        )
                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
                        jitter = random.uniform(0, 0.5)
                        sleep_time = delay + jitter
                        logging.warning(
                            f"API连接错误 ({func.__name__}, 尝试 {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        logging.info(f"将在 {sleep_time:.2f} 秒后重试...")
                        time.sleep(sleep_time)
                    else:
                        logging.error(
                            f"API连接错误，已达到最大重试次数 ({max_retries + 1}): {e}"
                        )
                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    status_code = e.response.status_code if hasattr(e, 'response') and e.response else None

                    if status_code == 429:
                        if attempt < max_retries:
                            delay = min(initial_delay * (backoff_factor ** (attempt + 2)), max_delay)
                            jitter = random.uniform(0, 1)
                            sleep_time = delay + jitter
                            logging.warning(
                                f"API速率限制 (429) ({func.__name__}, 尝试 {attempt + 1}/{max_retries + 1})"
                            )
                            logging.info(f"将在 {sleep_time:.2f} 秒后重试...")
                            time.sleep(sleep_time)
                        else:
                            logging.error(f"API速率限制，已达到最大重试次数 ({max_retries + 1})")
                    elif status_code in [500, 502, 503, 504]:
                        if attempt < max_retries:
                            delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
                            jitter = random.uniform(0, 0.5)
                            sleep_time = delay + jitter
                            logging.warning(
                                f"服务器错误 ({status_code}) ({func.__name__}, 尝试 {attempt + 1}/{max_retries + 1})"
                            )
                            logging.info(f"将在 {sleep_time:.2f} 秒后重试...")
                            time.sleep(sleep_time)
                        else:
                            logging.error(f"服务器错误，已达到最大重试次数 ({max_retries + 1})")
                    else:
                        raise
                except Exception as e:
                    logging.error(f"API请求发生未预期错误 ({func.__name__}): {e}")
                    raise

            if last_exception:
                raise last_exception

        return wrapper
    return decorator


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