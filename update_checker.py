import requests
import logging
import os
import time
import concurrent.futures
from pathlib import Path
from packaging.version import parse as parse_version

# 加速代理列表
GH_PROXY_URLS = [
    "https://gh-proxy.org/",
    "https://hk.gh-proxy.org/",
    "https://cdn.gh-proxy.org/",
    "https://edgeone.gh-proxy.org/"
]

LATEST_RELEASE_API_URL = "https://api.github.com/repos/blibilijojo/Modpack-Localizer/releases/latest"

def _format_speed(speed_bps: float) -> str:
    if speed_bps > 1024 * 1024:
        return f"{speed_bps / (1024 * 1024):.2f} MB/s"
    return f"{speed_bps / 1024:.1f} KB/s"

def check_for_updates(current_version_str: str) -> dict | None:
    logging.info(f"开始程序版本更新检查... 当前版本: {current_version_str}")
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
            return None
        asset_url_original = None
        for asset in data.get("assets", []):
            if asset.get("name", "").startswith("Modpack-Localizer-Pro") and asset.get("name", "").endswith(".exe"):
                asset_url_original = asset.get("browser_download_url")
                break
        if asset_url_original:
            logging.info(f"发现新程序版本: {latest_version}！")
            return {
                "version": data.get("tag_name", f"v{latest_version_str}"),
                "notes": data.get("body", "没有提供更新日志。"),
                "asset_url": asset_url_original,
                "proxy_urls": GH_PROXY_URLS
            }
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

def download_update(url: str, save_path: Path, progress_callback=None) -> bool:
    logging.info(f"开始下载文件... 原始URL: {url}")
    
    # 尝试所有代理URL
    for proxy_url in GH_PROXY_URLS:
        proxied_url = f"{proxy_url}{url}"
        logging.info(f"尝试使用代理: {proxy_url}")
        try:
            # 首先获取文件大小
            with requests.head(proxied_url, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
            
            if total_size == 0:
                logging.warning(f"代理 {proxy_url} 返回文件大小为0，尝试下一个代理")
                continue
            
            # 创建文件并预分配空间
            with open(save_path, 'wb') as f:
                f.truncate(total_size)
            
            # 配置多线程下载
            num_threads = min(8, max(2, total_size // (1024 * 1024 * 50)))
            chunk_size = total_size // num_threads
            chunks = []
            
            for i in range(num_threads):
                start = i * chunk_size
                end = start + chunk_size - 1 if i < num_threads - 1 else total_size - 1
                chunks.append((start, end))
            
            # 开始多线程下载
            logging.info(f"开始多线程下载，线程数: {num_threads}")
            start_time = time.time()
            bytes_downloaded = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                session = requests.Session()
                future_to_chunk = {
                    executor.submit(_download_chunk, proxied_url, start, end, session, save_path, i, chunk_size): (start, end) 
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
                            speed_bps = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
                            speed_text = _format_speed(speed_bps)
                            progress_callback("下载中", percentage, speed_text)
                    except Exception as e:
                        logging.error(f"下载块失败: {e}")
                        raise
            
            # 验证文件大小
            if os.path.getsize(save_path) != total_size:
                logging.error(f"下载完成但文件大小不匹配: {os.path.getsize(save_path)} != {total_size}")
                os.remove(save_path)
                continue
            
            logging.info(f"成功下载文件: {save_path}，使用代理: {proxy_url}")
            return True
        except Exception as e:
            logging.error(f"使用代理 {proxy_url} 下载失败: {e}")
            if save_path.exists():
                try:
                    os.remove(save_path)
                except Exception:
                    pass
            continue
    
    # 所有代理都失败，尝试直接下载
    logging.info("所有代理都失败，尝试直接下载")
    try:
        with requests.get(url, stream=True, timeout=180) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            bytes_downloaded = 0
            start_time = time.time()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if progress_callback:
                        percentage = (bytes_downloaded / total_size) * 100 if total_size > 0 else 0
                        elapsed_time = time.time() - start_time
                        speed_bps = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
                        speed_text = _format_speed(speed_bps)
                        progress_callback("下载中", percentage, speed_text)
        logging.info(f"成功直接下载文件: {save_path}")
        return True
    except Exception as e:
        logging.error(f"直接下载失败: {e}")
        if save_path.exists():
            try:
                os.remove(save_path)
            except Exception:
                pass
        return False