import concurrent.futures
import logging
import threading
from typing import List, Callable, Any, Optional

class MultithreadingUtils:
    """多线程工具类"""
    
    @staticmethod
    def process_items_with_threads(
        items: List[Any],
        process_func: Callable[[Any], Any],
        max_workers: int = 32,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        description: str = "处理项目"
    ) -> List[Any]:
        """
        使用线程池处理多个项目
        
        Args:
            items: 要处理的项目列表
            process_func: 处理单个项目的函数
            max_workers: 最大线程数
            progress_callback: 进度更新回调函数
            description: 任务描述
        
        Returns:
            处理结果列表
        """
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
            """包装处理函数，添加进度更新和结果收集"""
            nonlocal processed_count
            
            try:
                # 执行实际处理
                result = process_func(item)
                
                # 线程安全地收集结果
                with results_lock:
                    results.append(result)
                
                # 更新处理计数
                with processed_count_lock:
                    processed_count += 1
                    if progress_callback:
                        progress_callback(processed_count, total_items)
                    
                    # 每处理10个项目记录一次日志
                    if processed_count % 10 == 0 or processed_count == total_items:
                        logging.info(f"{description}: 已处理 {processed_count}/{total_items} 个项目")
                
                return result
            except Exception as e:
                logging.error(f"{description}: 处理项目时发生错误: {e}")
                return None
        
        # 使用线程池处理项目
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务到线程池
            futures = [executor.submit(wrapped_process_func, item) for item in items]
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"{description}: 任务执行失败: {e}")
        
        logging.info(f"{description}: 处理完成，共处理 {len(results)} 个项目")
        return results
    
    @staticmethod
    def run_parallel_tasks(
        tasks: List[Callable[[], Any]],
        max_workers: int = None,
        description: str = "并行任务"
    ) -> List[Any]:
        """
        并行运行多个任务
        
        Args:
            tasks: 要执行的任务列表
            max_workers: 最大线程数，None表示使用默认值
            description: 任务描述
        
        Returns:
            任务执行结果列表
        """
        if not tasks:
            logging.info(f"{description}: 无任务需要执行")
            return []
        
        logging.info(f"{description}: 开始执行 {len(tasks)} 个任务")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务到线程池
            futures = [executor.submit(task) for task in tasks]
            
            # 收集结果
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