from __future__ import annotations
import tkinter as tk
import ttkbootstrap as ttk
from gui import ui_utils, custom_widgets
import threading
import re
import logging
import requests
from pathlib import Path
from utils import config_manager
from utils.api_urls import GITHUB_API_BASE, DICT_RELEASE_API_URL
GITHUB_REPO_URL_PATTERN = re.compile(r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$')
OWNER_REPO_PATTERN = re.compile(r'^([^/]+)/([^/]+)$')

MODE_OPTIONS = [
    ("命名空间（文件名称）", "namespace_jar"),
    ("文件名称（命名空间）", "jar_namespace"),
    ("命名空间", "namespace"),
    ("文件名称", "jar"),
]


def create_path_entry(parent, label_text, var, browse_type, tooltip, save_callback=None):
    row_frame = ttk.Frame(parent)
    row_frame.pack(fill="x", pady=5)
    label = ttk.Label(row_frame, text=label_text, width=15)
    label.pack(side="left")
    custom_widgets.ToolTip(label, tooltip)
    entry = ttk.Entry(row_frame, textvariable=var, takefocus=False)
    entry.pack(side="left", fill="x", expand=True, padx=5)
    if save_callback:
        var.trace_add("write", lambda *args: save_callback())
    browse_cmd = lambda: ui_utils.browse_directory(var) if browse_type == "directory" else ui_utils.browse_file(var)
    ttk.Button(row_frame, text="浏览...", command=browse_cmd, bootstyle="primary-outline").pack(side="left")
    entry.after_idle(entry.selection_clear)


def create_mode_combobox(parent, var, save_callback):
    mode_combobox = ttk.Combobox(parent, state="readonly")
    mode_combobox['values'] = [option[0] for option in MODE_OPTIONS]
    current_value = var.get()
    for i, (option_text, option_value) in enumerate(MODE_OPTIONS):
        if option_value == current_value:
            mode_combobox.current(i)
            break
    mode_combobox.pack(side="left", fill="x", expand=True, padx=5, pady=5)

    def on_mode_change(event):
        selected_index = mode_combobox.current()
        if selected_index != -1:
            selected_value = MODE_OPTIONS[selected_index][1]
            var.set(selected_value)
            save_callback()
            mode_combobox.selection_clear()

    mode_combobox.bind("<<ComboboxSelected>>", on_mode_change)


def parse_github_repo_url(repo_url: str) -> str:
    match = GITHUB_REPO_URL_PATTERN.match(repo_url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    match = OWNER_REPO_PATTERN.match(repo_url)
    if match:
        return repo_url
    return repo_url


def test_github_authentication(repo: str, token: str) -> tuple[bool, str]:
    if not repo or not token:
        return False, "请先填写仓库地址和访问令牌"

    parsed_repo = parse_github_repo_url(repo)
    api_url = f"{GITHUB_API_BASE}/repos/{parsed_repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            repo_data = response.json()
            return True, f"认证成功！仓库: {repo_data['name']}"
        else:
            return False, f"认证失败: {response.status_code} - {response.json().get('message', '未知错误')}"
    except Exception as e:
        return False, f"测试错误: {str(e)}"


def apply_github_acceleration(url: str) -> str:
    if "github.com" not in url:
        return url
    config = config_manager.load_config()
    github_proxies = config.get("github_proxies", [])
    if github_proxies and url.startswith("https://github.com/"):
        proxy = github_proxies[0]
        return proxy + url[8:]
    return url


def get_remote_dict_info() -> dict | None:
    try:
        response = requests.get(DICT_RELEASE_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        version = data.get("tag_name", "")
        if version.startswith("v"):
            version = version[1:]
        url = next(
            (asset.get("browser_download_url") for asset in data.get("assets", [])
             if asset.get("name") == "Dict-Sqlite.db"),
            None,
        )
        if version and url:
            return {"version": version, "url": url}
    except Exception as e:
        logging.error(f"获取远程词典信息失败: {e}")
    return None


def download_dict_file(remote_info: dict, local_path: Path, progress_callback=None) -> tuple[bool, str]:
    url = remote_info.get("url")
    if not url:
        return False, "无法获取远程词典下载链接"

    accelerated_url = apply_github_acceleration(url)
    if accelerated_url != url:
        logging.info(f"应用GitHub加速，使用链接: {accelerated_url}")

    try:
        response = requests.get(accelerated_url, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))

        bytes_downloaded = 0
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=16384):
                if chunk:
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if progress_callback:
                        progress = (bytes_downloaded / total_size) * 100 if total_size > 0 else 0
                        progress_callback(progress, bytes_downloaded, total_size)

        config_manager.update_config("last_dict_version", remote_info.get("version"))
        return True, f"社区词典已成功更新到版本 {remote_info.get('version')}"

    except Exception as e:
        logging.error(f"下载词典失败: {e}")
        return False, f"下载词典时发生错误: {e}"
