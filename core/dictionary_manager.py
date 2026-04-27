from __future__ import annotations
import logging
from pathlib import Path
import sqlite3
from collections import defaultdict
from utils import config_manager
from core.models import resolve_origin_name_conflict

class DictionaryManager:

    def __init__(self):
        self.user_dict: dict | None = None
        self.community_dict_by_key: dict[str, str] | None = None
        self.community_dict_by_origin: dict[str, list[dict]] | None = None
        self._cache: dict[str, tuple] = {}
        self._community_origin_cache: dict[str, str | None] = {}
        self._lower_key_index: dict[str, str] = {}
        self._lower_origin_index: dict[str, str] = {}
        self._lower_community_key_index: dict[str, str] = {}
        self._lower_community_origin_index: dict[str, str] = {}
        self._search_index_built = False

    def _build_search_index(self):
        self._lower_key_index = {k.lower(): k for k in self.user_dict.get('by_key', {})} if self.user_dict else {}
        self._lower_origin_index = {k.lower(): k for k in self.user_dict.get('by_origin_name', {})} if self.user_dict else {}
        self._lower_community_key_index = {k.lower(): k for k in (self.community_dict_by_key or {})}
        self._lower_community_origin_index = {}
        if self.community_dict_by_origin:
            for origin in self.community_dict_by_origin:
                self._lower_community_origin_index[origin.lower()] = origin
        self._search_index_built = True

    def _ensure_search_index(self):
        if not self._search_index_built:
            self._build_search_index()

    def load_user_dictionary(self) -> dict:
        try:
            self.user_dict = config_manager.load_user_dict()
            logging.debug("用户词典加载成功")
            return self.user_dict
        except Exception as e:
            logging.error(f"加载用户词典失败: {e}")
            return {'by_key': {}, 'by_origin_name': {}}

    def load_community_dictionary(self, community_dict_dir: str, progress_callback=None) -> tuple[dict[str, str], dict[str, list[dict]]]:
        community_dict_by_key: dict[str, str] = {}
        community_dict_by_origin: dict[str, list[dict]] = defaultdict(list)

        if not community_dict_dir:
            self.community_dict_by_key = community_dict_by_key
            self.community_dict_by_origin = community_dict_by_origin
            self._search_index_built = False
            return community_dict_by_key, community_dict_by_origin

        try:
            dict_file_path = Path(community_dict_dir) / "Dict-Sqlite.db"

            if not dict_file_path.is_file():
                logging.info(f"社区词典文件不存在: {dict_file_path}")
                self.community_dict_by_key = community_dict_by_key
                self.community_dict_by_origin = community_dict_by_origin
                self._search_index_built = False
                return community_dict_by_key, community_dict_by_origin

            with sqlite3.connect(f"file:{dict_file_path}?mode=ro", uri=True) as con:
                cur = con.cursor()

                cur.execute("SELECT COUNT(*) FROM dict")
                total_rows = cur.fetchone()[0]

                cur.execute("SELECT key, origin_name, trans_name, version FROM dict")

                batch_size = 1000
                processed_rows = 0

                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break

                    for key, origin_name, trans_name, version in rows:
                        if key:
                            community_dict_by_key[key] = trans_name
                        if origin_name and trans_name:
                            community_dict_by_origin[origin_name].append({
                                "trans": trans_name,
                                "version": version or "0.0.0"
                            })

                    processed_rows += len(rows)

                    if progress_callback and total_rows > 0:
                        progress = min(int((processed_rows / total_rows) * 100), 100)
                        progress_callback(f"加载社区词典... {progress}%", progress)

            logging.debug(f"社区词典加载成功: {len(community_dict_by_key)}条按键, {len(community_dict_by_origin)}条按原文")
        except Exception as e:
            logging.error(f"读取社区词典数据库时发生错误: {e}")

        self.community_dict_by_key = community_dict_by_key
        self.community_dict_by_origin = community_dict_by_origin
        self._search_index_built = False
        return community_dict_by_key, community_dict_by_origin

    def get_all_dictionaries(self, community_dict_dir: str, progress_callback=None) -> tuple[dict, dict[str, str], dict[str, list[dict]]]:
        cache_key = f"all_dicts_{community_dict_dir or 'none'}"
        if cache_key in self._cache:
            logging.debug("从缓存中获取词典数据")
            if progress_callback:
                progress_callback("加载词典缓存...", 100)
            return self._cache[cache_key]

        user_dict = self.load_user_dictionary()
        community_dict_by_key, community_dict_by_origin = self.load_community_dictionary(community_dict_dir, progress_callback)

        result = (user_dict, community_dict_by_key, community_dict_by_origin)
        self._cache[cache_key] = result

        user_count = len(user_dict.get('by_key', {})) + len(user_dict.get('by_origin_name', {}))
        community_count = len(community_dict_by_key) + len(community_dict_by_origin)
        logging.info(f"词典加载完成: 用户词典{user_count}条, 社区词典{community_count}条")

        return result

    def get_community_origin_translation(self, origin_name: str) -> str | None:
        if origin_name in self._community_origin_cache:
            return self._community_origin_cache[origin_name]

        if not self.community_dict_by_origin or origin_name not in self.community_dict_by_origin:
            return None

        candidates = self.community_dict_by_origin[origin_name]
        if not candidates:
            return None

        translation = resolve_origin_name_conflict(candidates)
        self._community_origin_cache[origin_name] = translation
        return translation

    def clear_cache(self):
        self._cache.clear()
        self._community_origin_cache.clear()
        self._lower_key_index.clear()
        self._lower_origin_index.clear()
        self._lower_community_key_index.clear()
        self._lower_community_origin_index.clear()
        self._search_index_built = False
        logging.debug("词典缓存已清除")

    def search_dictionary(self, query: str, search_type: str = 'both') -> list[dict]:
        results: list[dict] = []

        if not self.user_dict:
            self.load_user_dictionary()

        self._ensure_search_index()

        query_lower = query.lower()

        if search_type in ('key', 'both'):
            for lower_key, orig_key in self._lower_key_index.items():
                if query_lower in lower_key:
                    results.append({'type': 'user_key', 'key': orig_key, 'value': self.user_dict['by_key'][orig_key]})
            for lower_key, orig_key in self._lower_community_key_index.items():
                if query_lower in lower_key:
                    results.append({'type': 'community_key', 'key': orig_key, 'value': self.community_dict_by_key[orig_key]})

        if search_type in ('origin', 'both'):
            for lower_origin, orig_origin in self._lower_origin_index.items():
                if query_lower in lower_origin:
                    results.append({'type': 'user_origin', 'key': orig_origin, 'value': self.user_dict['by_origin_name'][orig_origin]})
            for lower_origin, orig_origin in self._lower_community_origin_index.items():
                if query_lower in lower_origin:
                    for entry in self.community_dict_by_origin[orig_origin]:
                        results.append({'type': 'community_origin', 'key': orig_origin, 'value': entry['trans']})

        return results
