# utils/session_manager.py

import json
import uuid
from pathlib import Path
import logging

# 缓存根目录
CACHE_ROOT = Path(".session_cache")
# 索引文件路径
INDEX_FILE = CACHE_ROOT / "session_index.json"

# 确保缓存目录存在
def _ensure_cache_dir_exists():
    if not CACHE_ROOT.exists():
        try:
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            logging.info(f"创建缓存目录: {CACHE_ROOT}")
        except OSError as e:
            logging.error(f"创建缓存目录时出错: {e}")

# 加载索引文件
def _load_index() -> dict:
    _ensure_cache_dir_exists()
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            logging.error("索引文件格式错误或已损坏，将创建新索引。")
            return {"tabs": {}}
    return {"tabs": {}}

# 保存索引文件
def _save_index(index_data: dict):
    _ensure_cache_dir_exists()
    try:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=4)
    except Exception as e:
        logging.error(f"保存索引文件时出错: {e}")

def save_session(project_tabs: list):
    """将所有活动标签页的状态保存到缓存文件。"""
    _ensure_cache_dir_exists()
    session_data = []
    index_data = _load_index()
    
    # 清理索引中不存在的标签页
    existing_uuids = set()
    
    for tab in project_tabs:
        state = tab.get_state()
        if state:
            # 生成或获取标签页的UUID
            tab_uuid = state.get('tab_uuid')
            if not tab_uuid:
                tab_uuid = str(uuid.uuid4())
                state['tab_uuid'] = tab_uuid
            
            # 保存标签页状态到独立文件
            tab_file = CACHE_ROOT / f"{tab_uuid}.json"
            try:
                with open(tab_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=4)
                existing_uuids.add(tab_uuid)
                
                # 更新索引
                tab_name = state.get('project_name', f"标签页 {tab_uuid[:8]}")
                index_data["tabs"][tab_uuid] = tab_name
                
                session_data.append(state)
            except Exception as e:
                logging.error(f"保存标签页缓存时出错: {e}")
    
    # 清理不存在的标签页文件和索引项
    for tab_uuid in list(index_data["tabs"].keys()):
        if tab_uuid not in existing_uuids:
            # 删除标签页文件
            tab_file = CACHE_ROOT / f"{tab_uuid}.json"
            if tab_file.exists():
                try:
                    tab_file.unlink()
                except OSError as e:
                    logging.error(f"删除标签页缓存文件时出错: {e}")
            # 从索引中删除
            del index_data["tabs"][tab_uuid]
    
    # 保存索引
    if existing_uuids:
        _save_index(index_data)
        logging.info(f"会话状态已成功缓存到 {CACHE_ROOT}")
    else:
        # 没有活动标签页，清除缓存
        clear_session()

def load_session() -> list | None:
    """从缓存文件加载会话状态。"""
    _ensure_cache_dir_exists()
    index_data = _load_index()
    
    if not index_data["tabs"]:
        return None
    
    session_data = []
    for tab_uuid in index_data["tabs"]:
        tab_file = CACHE_ROOT / f"{tab_uuid}.json"
        if tab_file.exists():
            try:
                with open(tab_file, 'r', encoding='utf-8') as f:
                    tab_state = json.load(f)
                session_data.append(tab_state)
            except (json.JSONDecodeError, TypeError):
                logging.error(f"标签页缓存文件 {tab_file} 格式错误或已损坏，跳过。")
    
    if session_data:
        logging.info(f"成功从 {CACHE_ROOT} 加载了缓存的会话。")
        return session_data
    else:
        return None

def clear_session():
    """删除缓存文件。"""
    try:
        # 删除所有标签页文件
        if CACHE_ROOT.exists():
            for tab_file in CACHE_ROOT.glob("*.json"):
                if tab_file != INDEX_FILE:
                    try:
                        tab_file.unlink()
                    except OSError as e:
                        logging.error(f"删除标签页缓存文件时出错: {e}")
            # 删除索引文件
            if INDEX_FILE.exists():
                INDEX_FILE.unlink()
            logging.info("会话缓存文件已成功清除。")
    except OSError as e:
        logging.error(f"清除会话缓存文件时出错: {e}")