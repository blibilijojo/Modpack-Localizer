# utils/session_manager.py

import json
from pathlib import Path
import logging

CACHE_FILE_PATH = Path("session_cache.json")

def save_session(project_tabs: list):
    """将所有活动标签页的状态保存到缓存文件。"""
    session_data = []
    for tab in project_tabs:
        state = tab.get_state()
        if state:
            session_data.append(state)
    
    if not session_data:
        clear_session()
        return

    try:
        with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4)
        logging.info(f"会话状态已成功缓存到 {CACHE_FILE_PATH}")
    except Exception as e:
        logging.error(f"无法将会话缓存到文件: {e}", exc_info=True)

def load_session() -> list | None:
    """从缓存文件加载会话状态。"""
    if not CACHE_FILE_PATH.exists():
        return None
    try:
        with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        logging.info(f"成功从 {CACHE_FILE_PATH} 加载了缓存的会话。")
        return session_data
    except (json.JSONDecodeError, TypeError):
        logging.error("会话缓存文件格式错误或已损坏，将开始新会话。")
        return None

def clear_session():
    """删除缓存文件。"""
    try:
        if CACHE_FILE_PATH.exists():
            CACHE_FILE_PATH.unlink()
            logging.info("会话缓存文件已成功清除。")
    except OSError as e:
        logging.error(f"清除会话缓存文件时出错: {e}")