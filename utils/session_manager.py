from __future__ import annotations
import json
import uuid
import hashlib
from pathlib import Path
import logging

CACHE_ROOT = Path(".session_cache")
INDEX_FILE = CACHE_ROOT / "session_index.json"

_EXCLUDED_HASH_KEYS = frozenset({'tab_uuid', 'last_save_time', 'content_hash', 'current_project_path'})
_EXCLUDED_WB_KEYS = frozenset({'last_modified', 'timestamp', 'modified_time'})


def _ensure_cache_dir_exists():
    if not CACHE_ROOT.exists():
        try:
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            logging.info(f"创建缓存目录: {CACHE_ROOT}")
        except OSError as e:
            logging.error(f"创建缓存目录时出错: {e}")


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


def _save_index(index_data: dict):
    _ensure_cache_dir_exists()
    try:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=4)
    except Exception as e:
        logging.error(f"保存索引文件时出错：{e}")


def _calculate_content_hash(state: dict) -> str:
    state_copy = {k: v for k, v in state.items() if k not in _EXCLUDED_HASH_KEYS}

    if 'workbench_data' in state_copy:
        workbench_data = state_copy['workbench_data']
        if isinstance(workbench_data, dict):
            state_copy['workbench_data'] = {
                k: v for k, v in workbench_data.items()
                if not k.startswith('_') and k not in _EXCLUDED_WB_KEYS
            }

    content_str = json.dumps(state_copy, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.md5(content_str.encode('utf-8')).hexdigest()


def _load_cached_tab(tab_uuid: str) -> dict | None:
    tab_file = CACHE_ROOT / f"{tab_uuid}.json"
    if tab_file.exists():
        try:
            with open(tab_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            logging.error(f"标签页缓存文件 {tab_file} 格式错误或已损坏。")
    return None


def _get_tab_name(state: dict, tab_uuid: str) -> str:
    return state.get('project_name', f"标签页 {tab_uuid[:8]}")


def save_session(project_tabs: list):
    _ensure_cache_dir_exists()
    index_data = _load_index()
    saved_count = 0
    skipped_count = 0
    index_changed = False

    existing_uuids: set[str] = set()

    for tab in project_tabs:
        state = tab.get_state()
        if not state:
            continue

        tab_uuid = state.get('tab_uuid')
        if not tab_uuid:
            tab_uuid = str(uuid.uuid4())
            state['tab_uuid'] = tab_uuid
            if hasattr(tab, 'tab_uuid'):
                tab.tab_uuid = tab_uuid

        existing_uuids.add(tab_uuid)
        tab_name = _get_tab_name(state, tab_uuid)

        try:
            cached_tab = _load_cached_tab(tab_uuid)
            current_hash = _calculate_content_hash(state)

            need_save = True

            if cached_tab:
                cached_hash = cached_tab.get('content_hash')
                if cached_hash == current_hash:
                    old_name = index_data["tabs"].get(tab_uuid)
                    if old_name != tab_name:
                        index_data["tabs"][tab_uuid] = tab_name
                        index_changed = True

                    skipped_count += 1
                    need_save = False
                else:
                    pass
            else:
                pass

            if need_save:
                logging.info(f"保存标签页 '{tab_name}'")

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

    existing_uuids = {tab.tab_uuid for tab in project_tabs if hasattr(tab, 'tab_uuid')}
    for tab_uuid in list(index_data["tabs"].keys()):
        if tab_uuid not in existing_uuids:
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
    _ensure_cache_dir_exists()
    return _load_index()


def load_session() -> list | None:
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
    tab_file = CACHE_ROOT / f"{tab_uuid}.json"
    if tab_file.exists():
        try:
            with open(tab_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            logging.error(f"标签页缓存文件 {tab_file} 格式错误或已损坏。")
    return None


def clear_session():
    try:
        if CACHE_ROOT.exists():
            for tab_file in CACHE_ROOT.glob("*.json"):
                if tab_file != INDEX_FILE:
                    try:
                        tab_file.unlink()
                    except OSError as e:
                        logging.error(f"删除标签页缓存文件时出错: {e}")
            if INDEX_FILE.exists():
                INDEX_FILE.unlink()
            logging.info("会话缓存文件已成功清除。")
    except OSError as e:
        logging.error(f"清除会话缓存文件时出错: {e}")
