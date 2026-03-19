# utils/session_manager.py

import json
import uuid
import hashlib
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
        logging.error(f"保存索引文件时出错：{e}")

def _calculate_content_hash(state: dict) -> str:
    """计算内容的哈希值，用于检测内容是否变化。"""
    import copy
    
    state_copy = copy.deepcopy(state)
    
    state_copy.pop('tab_uuid', None)
    state_copy.pop('last_save_time', None)
    state_copy.pop('content_hash', None)
    state_copy.pop('current_project_path', None)
    
    if 'workbench_data' in state_copy:
        workbench_data = state_copy['workbench_data']
        if isinstance(workbench_data, dict):
            for key in list(workbench_data.keys()):
                if key.startswith('_') or key in ('last_modified', 'timestamp', 'modified_time'):
                    del workbench_data[key]
    
    content_str = json.dumps(state_copy, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.md5(content_str.encode('utf-8')).hexdigest()

def _load_cached_tab(tab_uuid: str) -> dict | None:
    """加载已缓存的标签页数据。"""
    tab_file = CACHE_ROOT / f"{tab_uuid}.json"
    if tab_file.exists():
        try:
            with open(tab_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            logging.error(f"标签页缓存文件 {tab_file} 格式错误或已损坏。")
    return None

def save_session(project_tabs: list):
    """增量保存会话状态，只在内容真正变化时才写入文件。"""
    _ensure_cache_dir_exists()
    index_data = _load_index()
    saved_count = 0
    skipped_count = 0
    index_changed = False
    
    existing_uuids = set()
    
    for tab in project_tabs:
        state = tab.get_state()
        if not state:
            # 跳过空标签页（没有加载内容的标签页）
            continue
        
        tab_uuid = state.get('tab_uuid')
        if not tab_uuid:
            tab_uuid = str(uuid.uuid4())
            state['tab_uuid'] = tab_uuid
            if hasattr(tab, 'tab_uuid'):
                tab.tab_uuid = tab_uuid
        
        existing_uuids.add(tab_uuid)
        
        try:
            cached_tab = _load_cached_tab(tab_uuid)
            
            current_hash = _calculate_content_hash(state)
            
            need_save = True
            reason = "首次保存"
            
            if cached_tab:
                cached_hash = cached_tab.get('content_hash')
                if cached_hash == current_hash:
                    tab_name = state.get('project_name', f"标签页 {tab_uuid[:8]}")
                    
                    old_name = index_data["tabs"].get(tab_uuid)
                    if old_name != tab_name:
                        index_data["tabs"][tab_uuid] = tab_name
                        index_changed = True
                    
                    skipped_count += 1
                    need_save = False
                    reason = "内容未变化"
                else:
                    tab_name = state.get('project_name', f"标签页 {tab_uuid[:8]}")
                    reason = "内容已变化"
            else:
                tab_name = state.get('project_name', f"标签页 {tab_uuid[:8]}")
                reason = "无缓存文件"
            
            if need_save:
                logging.info(f"保存标签页 '{tab_name}' ({reason})")
                
                tab_file = CACHE_ROOT / f"{tab_uuid}.json"
                state['content_hash'] = current_hash
                
                with open(tab_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=4, ensure_ascii=False)
                
                old_name = index_data["tabs"].get(tab_uuid)
                if old_name != tab_name:
                    index_changed = True
                index_data["tabs"][tab_uuid] = tab_name
                saved_count += 1
            
        except Exception as e:
            logging.error(f"保存标签页缓存时出错：{e}")
    
    # 处理已关闭的标签页
    # 遍历索引文件中的所有标签页
    for tab_uuid in list(index_data["tabs"].keys()):
        # 检查该标签页是否在当前标签页列表中
        is_tab_exists = False
        for tab in project_tabs:
            if hasattr(tab, 'tab_uuid') and tab.tab_uuid == tab_uuid:
                is_tab_exists = True
                break
        
        # 如果标签页不存在于当前列表中，删除它
        if not is_tab_exists:
            tab_file = CACHE_ROOT / f"{tab_uuid}.json"
            if tab_file.exists():
                try:
                    tab_file.unlink()
                except OSError as e:
                    logging.error(f"删除标签页缓存文件时出错：{e}")
            del index_data["tabs"][tab_uuid]
            index_changed = True
    
    if index_data["tabs"]:
        if index_changed:
            _save_index(index_data)
            logging.info(f"会话缓存已更新：{saved_count} 个标签页已保存，{skipped_count} 个未变化")
        else:
            logging.debug(f"会话缓存检查完成：{skipped_count} 个标签页均未变化，索引也未变化")
    else:
        clear_session()

def load_index_only() -> dict:
    """只加载索引文件，不加载标签页内容。"""
    _ensure_cache_dir_exists()
    index_data = _load_index()
    return index_data

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

def load_tab_state(tab_uuid: str) -> dict | None:
    """加载指定标签页的状态。"""
    tab_file = CACHE_ROOT / f"{tab_uuid}.json"
    if tab_file.exists():
        try:
            with open(tab_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            logging.error(f"标签页缓存文件 {tab_file} 格式错误或已损坏。")
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