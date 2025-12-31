# utils/update_checker.py

import requests
import logging
import os
import time
from pathlib import Path
from packaging.version import parse as parse_version

STABLE_PROXY_URL = "https://lucky-moth-20.deno.dev/"
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
            proxied_asset_url = f"{STABLE_PROXY_URL}{asset_url_original}"
            logging.info(f"发现新程序版本: {latest_version}！")
            return {
                "version": data.get("tag_name", f"v{latest_version_str}"),
                "notes": data.get("body", "没有提供更新日志。"),
                "asset_url": proxied_asset_url
            }
        else:
            logging.warning(f"发现新程序版本 {latest_version}, 但在其发布附件中未找到.exe文件。")
            return None
            
    except Exception as e:
        logging.error(f"直接连接GitHub API进行程序版本检测失败: {e}")
        return None

def download_update(url: str, save_path: Path, progress_callback=None) -> bool:
    logging.info(f"开始下载文件... URL: {url}")
    
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
        
        logging.info(f"成功下载文件: {save_path}")
        return True
        
    except Exception as e:
        logging.error(f"下载文件时失败: {e}")
        if save_path.exists():
            try:
                os.remove(save_path)
            except Exception:
                pass
        return False
