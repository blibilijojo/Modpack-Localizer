import logging
import time
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.extractor import Extractor

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_extractor_performance():
    """
    测试提取器性能
    """
    logging.info("=== 测试提取器性能 ===")
    
    # 创建提取器实例
    extractor = Extractor()
    
    # 设置Mods目录
    mods_dir = Path('d:\\py\\我的世界\\Modpack-Localizer')
    
    # 测试从Mods中提取数据
    logging.info("\n1. 测试从Mods中提取数据")
    start_time = time.time()
    
    def progress_callback(current, total):
        logging.info(f"进度: {current}/{total}")
    
    result = extractor.extract_from_mods(mods_dir, progress_callback)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    logging.info(f"\n提取完成，耗时: {elapsed_time:.2f} 秒")
    logging.info(f"发现 {len(result.master_english)} 个命名空间")
    
    # 测试提取Mod信息
    logging.info("\n2. 测试提取Mod信息")
    start_time = time.time()
    
    # 模拟run方法中的Mod信息提取部分
    module_names = []
    curseforge_names = []
    modrinth_names = []
    
    mod_info_by_jar = {}
    curseforge_hashes = []
    modrinth_hashes = []
    hash_to_jar = {}
    
    # 获取含语言文件的JAR文件列表
    jars_with_language_files = set()
    for ns_info in result.namespace_info.values():
        # 从namespace_info中提取JAR文件名
        jar_name = ns_info.jar_name
        # 移除可能的格式后缀
        if " (both formats)" in jar_name:
            jar_name = jar_name.replace(" (both formats)", "")
        jars_with_language_files.add(jar_name)
    
    logging.info(f"发现 {len(jars_with_language_files)} 个含语言文件的模组")
    
    if mods_dir.exists():
        jar_files = []
        for jar_file in Path(mods_dir).glob('*.jar'):
            if jar_file.name in jars_with_language_files:
                jar_files.append(jar_file)
        
        total_jars = len(jar_files)
        processed_count = 0
        
        logging.info(f"处理 {total_jars} 个JAR文件")
        
        for jar_file in jar_files:
            # 提取模组信息
            mod_name, curseforge_hash, modrinth_hash, game_version = extractor._extract_mod_info(jar_file)
            
            # 存储初步信息
            mod_info_by_jar[jar_file.name] = {
                'name': mod_name,
                'curseforge_hash': curseforge_hash,
                'modrinth_hash': modrinth_hash,
                'game_version': game_version
            }
            
            # 收集哈希值用于API查询
            if curseforge_hash:
                curseforge_hashes.append(curseforge_hash)
                hash_to_jar[curseforge_hash] = jar_file.name
            if modrinth_hash:
                modrinth_hashes.append(modrinth_hash)
                hash_to_jar[modrinth_hash] = jar_file.name
            
            processed_count += 1
            logging.info(f"已处理 {processed_count}/{total_jars} 个文件")
        
        # 测试并行API请求
        logging.info("\n3. 测试并行API请求")
        start_api_time = time.time()
        
        # 并行从CurseForge和Modrinth获取信息
        import concurrent.futures
        
        # 定义获取CurseForge信息的函数
        def get_curseforge_info():
            return extractor._get_mod_info_from_curseforge(curseforge_hashes)
        
        # 定义获取Modrinth信息的函数
        def get_modrinth_info():
            # 收集所有Modrinth哈希
            all_modrinth_hashes = []
            for jar_name, info in mod_info_by_jar.items():
                if info['modrinth_hash']:
                    all_modrinth_hashes.append(info['modrinth_hash'])
            return extractor._get_mod_info_from_modrinth(all_modrinth_hashes)
        
        # 并行执行两个API请求
        curseforge_info = {}
        modrinth_info = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # 提交任务
            cf_future = executor.submit(get_curseforge_info)
            mr_future = executor.submit(get_modrinth_info)
            
            # 等待任务完成
            try:
                curseforge_info = cf_future.result()
            except Exception as e:
                logging.error(f"获取CurseForge信息失败: {e}")
            
            try:
                modrinth_info = mr_future.result()
            except Exception as e:
                logging.error(f"获取Modrinth信息失败: {e}")
        
        end_api_time = time.time()
        api_elapsed_time = end_api_time - start_api_time
        logging.info(f"API请求完成，耗时: {api_elapsed_time:.2f} 秒")
        logging.info(f"从CurseForge获取到 {len(curseforge_info)} 个模组信息")
        logging.info(f"从Modrinth获取到 {len(modrinth_info)} 个模组信息")
    
    end_time = time.time()
    total_elapsed_time = end_time - start_time
    logging.info(f"\n总耗时: {total_elapsed_time:.2f} 秒")
    
    logging.info("\n=== 性能测试完成 ===")

if __name__ == "__main__":
    test_extractor_performance()