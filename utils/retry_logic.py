from __future__ import annotations
import time
import random
import asyncio
import logging
import requests
from functools import wraps


def _calculate_delay(attempt: int, initial_delay: float, max_delay: float, backoff_factor: float, extra_shift: int = 0) -> float:
    delay = min(initial_delay * (backoff_factor ** (attempt + extra_shift)), max_delay)
    jitter = random.uniform(0, 0.5)
    return delay + jitter


def _should_retry_status(status_code: int) -> bool:
    return status_code == 429 or status_code in (500, 502, 503, 504)


def _handle_retryable_exception(
    exception: Exception,
    func_name: str,
    attempt: int,
    max_retries: int,
    initial_delay: float,
    max_delay: float,
    backoff_factor: float,
    extra_shift: int = 0,
    label: str = "",
) -> float | None:
    if attempt >= max_retries:
        logging.error(f"{label}，已达到最大重试次数 ({max_retries + 1}): {exception}")
        return None

    delay = _calculate_delay(attempt, initial_delay, max_delay, backoff_factor, extra_shift=extra_shift)
    logging.warning(f"{label} ({func_name}, 尝试 {attempt + 1}/{max_retries + 1}): {exception}")
    logging.info(f"将在 {delay:.2f} 秒后重试...")
    return delay


def api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    delay = _handle_retryable_exception(
                        e, func.__name__, attempt, max_retries,
                        initial_delay, max_delay, backoff_factor,
                        label="API请求超时",
                    )
                    if delay is None:
                        break
                    time.sleep(delay)

                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    delay = _handle_retryable_exception(
                        e, func.__name__, attempt, max_retries,
                        initial_delay, max_delay, backoff_factor,
                        label="API连接错误",
                    )
                    if delay is None:
                        break
                    time.sleep(delay)

                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    status_code = e.response.status_code if hasattr(e, 'response') and e.response else None

                    if status_code == 429:
                        delay = _handle_retryable_exception(
                            e, func.__name__, attempt, max_retries,
                            initial_delay, max_delay, backoff_factor,
                            extra_shift=2, label="API速率限制 (429)",
                        )
                        if delay is None:
                            break
                        time.sleep(delay)
                    elif status_code in (500, 502, 503, 504):
                        delay = _handle_retryable_exception(
                            e, func.__name__, attempt, max_retries,
                            initial_delay, max_delay, backoff_factor,
                            label=f"服务器错误 ({status_code})",
                        )
                        if delay is None:
                            break
                        time.sleep(delay)
                    else:
                        raise

                except Exception as e:
                    logging.error(f"API请求发生未预期错误 ({func.__name__}): {e}")
                    raise

            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def async_api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    delay = _handle_retryable_exception(
                        e, func.__name__, attempt, max_retries,
                        initial_delay, max_delay, backoff_factor,
                        label="API请求超时",
                    )
                    if delay is None:
                        break
                    await asyncio.sleep(delay)

                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    delay = _handle_retryable_exception(
                        e, func.__name__, attempt, max_retries,
                        initial_delay, max_delay, backoff_factor,
                        label="API连接错误",
                    )
                    if delay is None:
                        break
                    await asyncio.sleep(delay)

                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    status_code = e.response.status_code if hasattr(e, 'response') and e.response else None

                    if status_code == 429:
                        delay = _handle_retryable_exception(
                            e, func.__name__, attempt, max_retries,
                            initial_delay, max_delay, backoff_factor,
                            extra_shift=2, label="API速率限制 (429)",
                        )
                        if delay is None:
                            break
                        await asyncio.sleep(delay)
                    elif status_code in (500, 502, 503, 504):
                        delay = _handle_retryable_exception(
                            e, func.__name__, attempt, max_retries,
                            initial_delay, max_delay, backoff_factor,
                            label=f"服务器错误 ({status_code})",
                        )
                        if delay is None:
                            break
                        await asyncio.sleep(delay)
                    else:
                        raise

                except Exception as e:
                    logging.error(f"API请求发生未预期错误 ({func.__name__}): {e}")
                    raise

            if last_exception:
                raise last_exception

        return wrapper
    return decorator
