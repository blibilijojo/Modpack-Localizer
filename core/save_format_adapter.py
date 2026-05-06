"""存档格式双向转换适配器，用于桌面版和手机版之间的存档互通。"""

from __future__ import annotations

import json
import logging
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def detect_format(save_data: dict) -> str:
    """检测存档格式类型。
    
    Returns:
        'desktop' - 桌面版格式
        'mobile'  - 手机版格式
        'unknown' - 无法识别
    """
    if "save_data" in save_data and "translation_state" in save_data.get("save_data", {}):
        return "desktop"
    if save_data.get("platform") == "mobile" and "data" in save_data:
        return "mobile"
    if "data" in save_data and "projects" in save_data.get("data", {}):
        return "mobile"
    return "unknown"


def desktop_to_mobile(desktop_save: dict) -> dict:
    """将桌面版存档转换为手机版格式。"""
    save_data = desktop_save.get("save_data", {})
    project_name = save_data.get("project_name", "未知项目")
    mc_version = save_data.get("target_minecraft_version", "")

    translation_state = save_data.get("translation_state", {})
    namespaces = {}
    total = 0
    for ns, entries in translation_state.items():
        ns_list = []
        if isinstance(entries, dict):
            for key, entry in entries.items():
                if isinstance(entry, dict):
                    ns_list.append({
                        "key": entry.get("key", key),
                        "en": entry.get("origin", ""),
                        "zh": entry.get("zh", ""),
                        "source": entry.get("source", "unknown"),
                        "modName": entry.get("mod", ""),
                    })
                    total += 1
        namespaces[ns] = ns_list

    mod_files = save_data.get("mod_files", [])
    mod_names = [m.get("name", "") if isinstance(m, dict) else str(m) for m in mod_files]
    mod_loader = "unknown"
    if mod_names:
        for name in mod_names:
            lower = name.lower()
            if "forge" in lower:
                mod_loader = "forge"
                break
            if "fabric" in lower:
                mod_loader = "fabric"
                break

    return {
        "version": "1.0.0",
        "platform": "mobile",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {
            "config": {},
            "projects": [
                {
                    "id": f"lan_{int(time.time())}",
                    "name": project_name,
                    "status": "active",
                    "namespaces": namespaces,
                    "mcVersion": mc_version,
                    "modLoader": mod_loader,
                }
            ],
        },
    }


def mobile_to_desktop(mobile_save: dict) -> dict:
    """将手机版存档转换为桌面版格式。"""
    data = mobile_save.get("data", {})
    projects = data.get("projects", [])
    if not projects:
        raise ValueError("手机版存档中没有项目数据")

    project = projects[0]
    project_name = project.get("name", "未知项目")
    mc_version = project.get("mcVersion", "")

    namespaces = project.get("namespaces", {})
    translation_state = {}
    for ns, entries in namespaces.items():
        ns_dict = {}
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    key = entry.get("key", "")
                    ns_dict[key] = {
                        "key": key,
                        "origin": entry.get("en", ""),
                        "zh": entry.get("zh", ""),
                        "source": entry.get("source", "unknown"),
                        "mod": entry.get("modName", ""),
                    }
        elif isinstance(entries, dict):
            for key, entry in entries.items():
                if isinstance(entry, dict):
                    ns_dict[key] = {
                        "key": entry.get("key", key),
                        "origin": entry.get("en", entry.get("origin", "")),
                        "zh": entry.get("zh", ""),
                        "source": entry.get("source", "unknown"),
                        "mod": entry.get("modName", entry.get("mod", "")),
                    }
        translation_state[ns] = ns_dict

    return {
        "version": "0.2.2",
        "save_data": {
            "project_name": project_name,
            "target_minecraft_version": mc_version,
            "translation_state": translation_state,
            "mod_files": [],
            "modrinth_mods": [],
            "curseforge_mods": [],
        },
    }


def convert_for_desktop(save_data: dict) -> dict:
    """自动检测格式并转换为桌面版格式。如果是桌面版则直接返回。"""
    fmt = detect_format(save_data)
    if fmt == "desktop":
        return save_data
    elif fmt == "mobile":
        return mobile_to_desktop(save_data)
    else:
        raise ValueError(f"无法识别的存档格式: {json.dumps(save_data, ensure_ascii=False)[:200]}")


def convert_for_mobile(save_data: dict) -> dict:
    """自动检测格式并转换为手机版格式。如果是手机版则直接返回。"""
    fmt = detect_format(save_data)
    if fmt == "mobile":
        return save_data
    elif fmt == "desktop":
        return desktop_to_mobile(save_data)
    else:
        raise ValueError(f"无法识别的存档格式: {json.dumps(save_data, ensure_ascii=False)[:200]}")


def get_device_name() -> str:
    """获取当前设备名称。"""
    try:
        return platform.node() or "Desktop-PC"
    except Exception:
        return "Desktop-PC"


def read_save_file(file_path: str) -> dict:
    """读取 .sav 存档文件。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    content = path.read_text(encoding="utf-8")
    return json.loads(content)


def write_save_file(file_path: str, save_data: dict) -> None:
    """写入 .sav 存档文件。"""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(save_data, indent=4, ensure_ascii=False)
    path.write_text(content, encoding="utf-8")
