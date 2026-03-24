"""
版本管理模块
优先从 Git 标签获取版本号，如果不在 Git 仓库中则使用硬编码版本
"""

import subprocess
from pathlib import Path


def _get_version_from_git() -> str | None:
    """尝试从 Git 标签获取版本号"""
    try:
        # 获取当前目录的 Git 根目录
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return None
        
        # 获取最近的标签
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            # 移除 'v' 前缀
            if tag.startswith('v'):
                return tag[1:]
            return tag
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return None


# 尝试从 Git 获取版本号，如果失败则使用默认版本
__version__ = _get_version_from_git() or "1.0.0"
