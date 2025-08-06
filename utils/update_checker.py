# utils/update_checker.py

import requests
import logging
import os
from pathlib import Path
from packaging.version import parse as parse_version

LATEST_RELEASE_API_URL = "https://api.github.com/repos/blibilijojo/Modpack-Localizer/releases/latest"

def check_for_updates(current_version_str: str) -> dict | None:
    """
    访问 GitHub API 检查最新发布版本，并与当前版本进行比较。
    """
    logging.info(f"正在检查更新... 当前版本: {current_version_str}")
    try:
        response = requests.get(LATEST_RELEASE_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        latest_version_str = data.get("tag_name", "0.0.0").lstrip('v')
        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)
        logging.info(f"从 GitHub 获取到的最新版本: {latest_version}")

        # 寻找 .exe 资产的直接下载链接
        asset_url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").startswith("Modpack-Localizer-Pro") and asset.get("name", "").endswith(".exe"):
                asset_url = asset.get("browser_download_url")
                break
        
        if latest_version > current_version and asset_url:
            logging.info(f"发现新版本: {latest_version}！下载链接: {asset_url}")
            return {
                "version": data.get("tag_name", f"v{latest_version_str}"),
                "notes": data.get("body", "没有提供更新日志。"),
                "asset_url": asset_url
            }
        else:
            if not asset_url and latest_version > current_version:
                logging.warning("发现新版本，但在其发布附件中未找到.exe文件，无法进行自动更新。")
            else:
                logging.info("当前已是最新版本。")
            return None
    except Exception as e:
        logging.error(f"检查更新时发生错误: {e}")
        return None

def download_update(url: str, save_path: Path, progress_callback=None) -> bool:
    """
    下载更新文件，并可选地报告进度。
    """
    try:
        logging.info(f"正在从 {url} 下载更新...")
        with requests.get(url, stream=True, timeout=180) as r: # 增加超时时间以适应大文件
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            bytes_downloaded = 0
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        percentage = (bytes_downloaded / total_size) * 100
                        progress_callback("下载中", percentage)
        logging.info(f"更新下载完成: {save_path}")
        return True
    except Exception as e:
        logging.error(f"下载更新时失败: {e}")
        if save_path.exists():
            try:
                os.remove(save_path)
            except Exception:
                pass
        return False