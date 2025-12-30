import requests
import logging
import os
import time
import concurrent.futures
from pathlib import Path
from packaging.version import parse as parse_version
from utils import config_manager

LATEST_RELEASE_API_URL = "https://api.github.com/repos/blibilijojo/Modpack-Localizer/releases/latest"

# 默认GitHub代理列表
DEFAULT_GH_PROXY_URLS = [
    "https://gh-proxy.org/",
    "https://hk.gh-proxy.org/",
    "https://cdn.gh-proxy.org/",
    "https://edgeone.gh-proxy.org/"
]

def _format_speed(speed_bps: float) -> str:
    if speed_bps > 1024 * 1024:
        return f"{speed_bps / (1024 * 1024):.2f} MB/s"
    return f"{speed_bps / 1024:.1f} KB/s"

def check_for_updates(current_version_str: str) -> dict | None:
    """检查是否有可用更新，添加了版本缓存机制"""
    logging.info(f"开始程序版本更新检查... 当前版本: {current_version_str}")
    
    # 尝试从缓存加载最新版本信息
    cache_file = Path("update_cache.json")
    cache_data = None
    if cache_file.exists():
        try:
            import json
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            # 检查缓存是否在24小时内有效
            if time.time() - cache_data.get("timestamp", 0) < 86400:
                latest_version_str = cache_data.get("tag_name", "0.0.0").lstrip('v')
                current_version = parse_version(current_version_str)
                latest_version = parse_version(latest_version_str)
                logging.info(f"从缓存获取到最新程序版本: {latest_version}")
                if latest_version <= current_version:
                    logging.info("当前程序已是最新版本。")
                    return None
                return cache_data
        except Exception as e:
            logging.warning(f"读取更新缓存失败: {e}")
    
    # 缓存无效或不存在，请求GitHub API
    logging.info(f"正在直接请求GitHub API: {LATEST_RELEASE_API_URL}")
    try:
        response = requests.get(LATEST_RELEASE_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        latest_version_str = data.get("tag_name", "0.0.0").lstrip('v')
        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)
        logging.info(f"成功获取到最新程序版本: {latest_version}")
        if latest_version <= current_version:
            logging.info("当前程序已是最新版本。")
            # 更新缓存，即使是最新版本
            try:
                import json
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "tag_name": data.get("tag_name"),
                        "body": data.get("body"),
                        "asset_url": None,
                        "proxy_urls": DEFAULT_GH_PROXY_URLS,
                        "timestamp": time.time()
                    }, f, indent=4)
            except Exception as e:
                logging.warning(f"写入更新缓存失败: {e}")
            return None
        
        asset_url_original = None
        asset_sha256 = None
        for asset in data.get("assets", []):
            if asset.get("name", "").startswith("Modpack-Localizer-Pro") and asset.get("name", "").endswith(".exe"):
                asset_url_original = asset.get("browser_download_url")
            elif asset.get("name", "").endswith(".sha256"):
                # 尝试获取SHA256校验文件
                asset_sha256 = asset.get("browser_download_url")
        
        if asset_url_original:
            logging.info(f"发现新程序版本: {latest_version}！")
            update_info = {
                "version": data.get("tag_name", f"v{latest_version_str}"),
                "notes": data.get("body", "没有提供更新日志。"),
                "asset_url": asset_url_original,
                "proxy_urls": DEFAULT_GH_PROXY_URLS,
                "sha256_url": asset_sha256,
                "timestamp": time.time()
            }
            
            # 保存到缓存
            try:
                import json
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(update_info, f, indent=4)
            except Exception as e:
                logging.warning(f"写入更新缓存失败: {e}")
            
            return update_info
        else:
            logging.warning(f"发现新程序版本 {latest_version}, 但在其发布附件中未找到.exe文件。")
            return None
    except Exception as e:
        logging.error(f"直接连接GitHub API进行程序版本检测失败: {e}")
        return None

def _download_chunk(url, start, end, session, save_path, chunk_index, chunk_size):
    headers = {'Range': f'bytes={start}-{end}'}
    with session.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(save_path, 'r+b') as f:
            f.seek(start)
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return True

def download_update(url: str, save_path: Path, progress_callback=None, sha256_url: str = None) -> bool:
    """下载更新文件，添加了重试机制、完整性校验和断点续传"""
    logging.info(f"开始下载文件... 原始URL: {url}")
    
    # 从配置中获取代理列表
    config = config_manager.load_config()
    proxy_urls = config.get("github_proxies", [])
    
    # 如果配置中没有代理，使用默认代理
    if not proxy_urls:
        proxy_urls = DEFAULT_GH_PROXY_URLS
    
    # 添加直接连接作为最后选项
    download_options = [("direct", url)] + [(proxy, f"{proxy}{url}") for proxy in proxy_urls]
    
    # 下载重试次数
    max_retries = 3
    
    for option_name, download_url in download_options:
        logging.info(f"尝试 {option_name}: {download_url}")
        
        for retry in range(max_retries):
            try:
                # 检查是否支持断点续传
                existing_size = 0
                if save_path.exists():
                    existing_size = os.path.getsize(save_path)
                
                # 首先获取文件大小
                headers = {}
                if existing_size > 0:
                    headers['Range'] = f'bytes={existing_size}-'
                
                with requests.head(download_url, headers=headers, timeout=30) as r:
                    r.raise_for_status()
                    
                    # 处理Content-Range头，获取总大小
                    if 'Content-Range' in r.headers:
                        # 服务器支持断点续传
                        total_size = int(r.headers['Content-Range'].split('/')[-1])
                        logging.info(f"支持断点续传，已下载 {existing_size} / {total_size} 字节")
                    else:
                        # 服务器不支持断点续传，重新下载
                        total_size = int(r.headers.get('content-length', 0))
                        existing_size = 0
                
                if total_size == 0:
                    logging.warning(f"{option_name} 返回文件大小为0，尝试下一个选项")
                    break
                
                # 创建文件或打开现有文件进行追加
                if existing_size == 0:
                    # 新文件，预分配空间
                    with open(save_path, 'wb') as f:
                        f.truncate(total_size)
                else:
                    # 断点续传，打开文件进行追加
                    if existing_size >= total_size:
                        logging.info(f"文件已完整下载，大小: {existing_size}")
                        break
                
                # 配置多线程下载
                num_threads = min(8, max(2, total_size // (1024 * 1024 * 50)))
                chunk_size = total_size // num_threads
                chunks = []
                
                for i in range(num_threads):
                    start = i * chunk_size
                    end = start + chunk_size - 1 if i < num_threads - 1 else total_size - 1
                    
                    # 跳过已下载的块
                    if existing_size > end:
                        continue
                    if existing_size > start:
                        start = existing_size
                    
                    chunks.append((start, end))
                
                # 如果所有块都已下载，跳过
                if not chunks:
                    break
                
                # 开始多线程下载
                logging.info(f"开始多线程下载，线程数: {num_threads}，重试次数: {retry+1}/{max_retries}")
                start_time = time.time()
                bytes_downloaded = existing_size
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                    session = requests.Session()
                    future_to_chunk = {
                        executor.submit(_download_chunk, download_url, start, end, session, save_path, i, chunk_size): (start, end) 
                        for i, (start, end) in enumerate(chunks)
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_chunk):
                        chunk_start, chunk_end = future_to_chunk[future]
                        try:
                            future.result()
                            chunk_downloaded = chunk_end - chunk_start + 1
                            bytes_downloaded += chunk_downloaded
                            
                            if progress_callback:
                                percentage = (bytes_downloaded / total_size) * 100
                                elapsed_time = time.time() - start_time
                                speed_bps = (bytes_downloaded - existing_size) / elapsed_time if elapsed_time > 0 else 0
                                speed_text = _format_speed(speed_bps)
                                progress_callback("下载中", percentage, speed_text)
                        except Exception as e:
                            logging.error(f"下载块失败: {e}")
                            raise
                
                break  # 下载成功，跳出重试循环
            except Exception as e:
                logging.error(f"{option_name} 下载失败 (重试 {retry+1}/{max_retries}): {e}")
                if retry < max_retries - 1:
                    logging.info(f"等待 2 秒后重试...")
                    time.sleep(2)
                else:
                    # 最后一次重试失败，清理文件
                    if save_path.exists():
                        try:
                            os.remove(save_path)
                        except Exception:
                            pass
        
        # 验证文件大小
        if save_path.exists() and os.path.getsize(save_path) == total_size:
            logging.info(f"成功下载文件: {save_path}，使用 {option_name}")
            
            # 验证文件完整性（如果有SHA256校验文件）
            if sha256_url:
                logging.info(f"开始验证文件完整性...")
                if _verify_file_integrity(save_path, sha256_url, download_options):
                    logging.info(f"文件完整性验证成功！")
                    return True
                else:
                    logging.error(f"文件完整性验证失败，尝试下一个选项")
                    os.remove(save_path)
                    continue
            else:
                # 没有SHA256校验文件，只验证大小
                return True
    
    logging.error(f"所有下载选项都失败，无法下载文件: {url}")
    return False

def _verify_file_integrity(file_path: Path, sha256_url: str, download_options: list) -> bool:
    """验证文件完整性"""
    import hashlib
    
    # 下载SHA256校验文件
    expected_sha256 = None
    for option_name, download_url in download_options:
        try:
            sha256_download_url = f"{download_url}" if option_name == "direct" else f"{download_url}{sha256_url}"
            with requests.get(sha256_download_url, timeout=30) as r:
                r.raise_for_status()
                sha256_content = r.text.strip()
                # 解析SHA256校验值
                expected_sha256 = sha256_content.split()[0] if sha256_content else None
                break
        except Exception as e:
            logging.error(f"下载SHA256文件失败 ({option_name}): {e}")
            continue
    
    if not expected_sha256:
        logging.warning(f"无法获取SHA256校验值，跳过完整性验证")
        return True
    
    # 计算本地文件的SHA256值
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b" "):
                sha256_hash.update(chunk)
        actual_sha256 = sha256_hash.hexdigest()
        logging.info(f"期望SHA256: {expected_sha256}")
        logging.info(f"实际SHA256: {actual_sha256}")
        return actual_sha256.lower() == expected_sha256.lower()
    except Exception as e:
        logging.error(f"计算文件SHA256值失败: {e}")
        return False