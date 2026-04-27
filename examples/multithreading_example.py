import logging
import time
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import MultithreadingUtils

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_mod_file(jar_file):
    """
    模拟处理Mod文件的函数
    """
    # 模拟处理时间
    time.sleep(0.1)
    
    # 模拟处理结果
    return {
        'file': jar_file.name,
        'size': jar_file.stat().st_size,
        'processed': True
    }

def get_mod_info_from_api(site):
    """
    模拟从API获取Mod信息的函数
    """
    # 模拟网络请求时间
    time.sleep(0.5)
    
    return {
        'site': site,
        'status': 'success',
        'data': f'从{site}获取的Mod信息'
    }

def main():
    """
    主函数，演示多线程工具的使用
    """
    logging.info("=== 多线程工具使用示例 ===")
    
    # 示例1：使用线程池处理多个Mod文件
    logging.info("\n1. 使用线程池处理多个Mod文件")
    
    # 模拟Mod文件列表
    mods_dir = Path('d:\\py\\我的世界\\Modpack-Localizer')
    jar_files = list(mods_dir.glob('*.jar'))[:10]  # 取前10个文件作为示例
    
    if jar_files:
        # 定义进度回调函数
        def progress_callback(current, total):
            logging.info(f"处理进度: {current}/{total}")
        
        # 使用多线程处理文件
        results = MultithreadingUtils.process_items_with_threads(
            items=jar_files,
            process_func=process_mod_file,
            max_workers=4,
            progress_callback=progress_callback,
            description="处理Mod文件"
        )
        
        # 打印处理结果
        logging.info(f"\n处理完成，共处理 {len(results)} 个文件")
        for result in results:
            if result:
                logging.info(f"处理结果: {result}")
    else:
        logging.info("未找到Mod文件，跳过示例1")
    
    # 示例2：并行运行多个API请求
    logging.info("\n2. 并行运行多个API请求")
    
    # 定义要并行执行的任务
    tasks = [
        lambda: get_mod_info_from_api("CurseForge"),
        lambda: get_mod_info_from_api("Modrinth"),
        lambda: get_mod_info_from_api("GitHub")
    ]
    
    # 使用多线程并行执行任务
    api_results = MultithreadingUtils.run_parallel_tasks(
        tasks=tasks,
        max_workers=3,
        description="获取API数据"
    )
    
    # 打印API请求结果
    logging.info("\nAPI请求结果:")
    for result in api_results:
        if result:
            logging.info(f"API结果: {result}")
    
    logging.info("\n=== 示例完成 ===")

if __name__ == "__main__":
    main()