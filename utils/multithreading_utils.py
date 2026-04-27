from __future__ import annotations
import concurrent.futures
import logging
import threading
from typing import Any, Callable


def process_items_with_threads(
    items: list[Any],
    process_func: Callable[[Any], Any],
    max_workers: int = 32,
    progress_callback: Callable[[int, int], None] | None = None,
    description: str = "处理项目"
) -> list[Any]:
    if not items:
        logging.info(f"{description}: 无项目需要处理")
        return []

    total_items = len(items)
    processed_count = 0
    processed_count_lock = threading.Lock()
    results = []
    results_lock = threading.Lock()

    logging.info(f"{description}: 开始处理 {total_items} 个项目，使用最大线程数: {max_workers}")

    def wrapped_process_func(item):
        nonlocal processed_count
        try:
            result = process_func(item)
            with results_lock:
                results.append(result)
            with processed_count_lock:
                processed_count += 1
                if progress_callback:
                    progress_callback(processed_count, total_items)
                if processed_count % 10 == 0 or processed_count == total_items:
                    logging.info(f"{description}: 已处理 {processed_count}/{total_items} 个项目")
            return result
        except Exception as e:
            logging.error(f"{description}: 处理项目时发生错误: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(wrapped_process_func, item) for item in items]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"{description}: 任务执行失败: {e}")

    logging.info(f"{description}: 处理完成，共处理 {len(results)} 个项目")
    return results


def run_parallel_tasks(
    tasks: list[Callable[[], Any]],
    max_workers: int | None = None,
    description: str = "并行任务"
) -> list[Any]:
    if not tasks:
        logging.info(f"{description}: 无任务需要执行")
        return []

    logging.info(f"{description}: 开始执行 {len(tasks)} 个任务")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(task) for task in tasks]
        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logging.error(f"{description}: 任务执行失败: {e}")
                results.append(None)

    logging.info(f"{description}: 所有任务执行完成")
    return results


class MultithreadingUtils:
    process_items_with_threads = staticmethod(process_items_with_threads)
    run_parallel_tasks = staticmethod(run_parallel_tasks)
