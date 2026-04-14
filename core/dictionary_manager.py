import logging
from pathlib import Path
import sqlite3
from collections import defaultdict, OrderedDict
from typing import Any
from utils import config_manager


class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._cache = OrderedDict()
        self._lock = None
    
    def get(self, key: Any) -> Any:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]
    
    def put(self, key: Any, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
        self._cache[key] = value
    
    def clear(self) -> None:
        self._cache.clear()
    
    def __len__(self) -> int:
        return len(self._cache)


class DictionaryManager:
    """词典管理模块，集中处理词典加载和管理功能"""
    
    def __init__(self, max_cache_size: int = 10000):
        self.user_dict = None
        self.community_dict_by_key = None
        self.community_dict_by_origin = None
        self._cache = {}  # 存储词典加载结果的缓存
        self._community_origin_cache = LRUCache(max_cache_size)
        self._user_dict_cache = LRUCache(max_cache_size)
    
    def load_user_dictionary(self):
        """加载用户词典"""
        try:
            self.user_dict = config_manager.load_user_dict()
            logging.debug("用户词典加载成功")
            return self.user_dict
        except Exception as e:
            logging.error(f"加载用户词典失败: {e}")
            return {'by_key': {}, 'by_origin_name': {}}
    
    def load_community_dictionary(self, community_dict_dir, progress_callback=None):
        """加载社区词典"""
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        
        if community_dict_dir:
            try:
                # 构建完整的文件路径
                dict_file_path = Path(community_dict_dir) / "Dict-Sqlite.db"
                
                if dict_file_path.is_file():
                    with sqlite3.connect(f"file:{dict_file_path}?mode=ro", uri=True) as con:
                        cur = con.cursor()
                        
                        # 先获取总记录数，用于计算进度
                        cur.execute("SELECT COUNT(*) FROM dict")
                        total_rows = cur.fetchone()[0]
                        
                        # 优化：只查询需要的字段，避免不必要的数据传输
                        cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
                        
                        # 使用分批获取数据，减少内存占用
                        batch_size = 1000
                        processed_rows = 0
                        
                        while True:
                            rows = cur.fetchmany(batch_size)
                            if not rows:
                                break
                            
                            for key, origin_name, trans_name, version in rows:
                                if key:
                                    # 键值对直接存储，保持O(1)查询效率
                                    community_dict_by_key[key] = trans_name
                                if origin_name and trans_name:
                                    # 原文条目存储为列表，便于后续冲突解决
                                    community_dict_by_origin[origin_name].append({"trans": trans_name, "version": version or "0.0.0"})
                            
                            processed_rows += len(rows)
                            
                            # 每处理一批数据，更新进度
                            if progress_callback and total_rows > 0:
                                progress = min(int((processed_rows / total_rows) * 100), 100)
                                progress_callback(f"加载社区词典... {progress}%", progress)
                    
                    logging.debug(f"社区词典加载成功: {len(community_dict_by_key)}条按键, {len(community_dict_by_origin)}条按原文")
                else:
                    logging.info(f"社区词典文件不存在: {dict_file_path}")
            except Exception as e:
                logging.error(f"读取社区词典数据库时发生错误: {e}")
        
        self.community_dict_by_key = community_dict_by_key
        self.community_dict_by_origin = community_dict_by_origin
        return community_dict_by_key, community_dict_by_origin
    
    def get_all_dictionaries(self, community_dict_dir, progress_callback=None):
        """获取所有词典数据"""
        # 检查缓存
        cache_key = f"all_dicts_{community_dict_dir or 'none'}"
        if cache_key in self._cache:
            logging.debug("从缓存中获取词典数据")
            if progress_callback:
                progress_callback("加载词典缓存...", 100)
            return self._cache[cache_key]
        
        # 加载词典
        user_dict = self.load_user_dictionary()
        community_dict_by_key, community_dict_by_origin = self.load_community_dictionary(community_dict_dir, progress_callback)
        
        # 缓存结果
        result = (user_dict, community_dict_by_key, community_dict_by_origin)
        self._cache[cache_key] = result
        
        logging.info(f"词典加载完成: 用户词典{len(user_dict.get('by_key', {}))+len(user_dict.get('by_origin_name', {}))}条, 社区词典{len(community_dict_by_key)+len(community_dict_by_origin)}条")
        
        return result
    
    def get_community_origin_translation(self, origin_name):
        """获取社区词典原文翻译，使用缓存避免重复计算"""
        cached = self._community_origin_cache.get(origin_name)
        if cached is not None:
            return cached
        
        if not self.community_dict_by_origin or origin_name not in self.community_dict_by_origin:
            return None
        
        candidates = self.community_dict_by_origin[origin_name]
        if not candidates:
            return None
        
        # 解决冲突
        if len(candidates) == 1:
            translation = candidates[0]["trans"]
        else:
            from collections import Counter
            from packaging.version import parse as parse_version
            
            trans_counts = Counter(c["trans"] for c in candidates)
            max_freq = max(trans_counts.values())
            top_candidates = [c for c in candidates if trans_counts[c["trans"]] == max_freq]
            
            if len(top_candidates) == 1:
                translation = top_candidates[0]["trans"]
            else:
                # 按版本号排序
                def get_version_key(candidate):
                    try:
                        return parse_version(candidate["version"])
                    except Exception:
                        return parse_version("0.0.0")
                
                try:
                    sorted_by_version = sorted(top_candidates, key=get_version_key, reverse=True)
                    translation = sorted_by_version[0]["trans"]
                except Exception:
                    translation = top_candidates[0]["trans"]
        
        self._community_origin_cache.put(origin_name, translation)
        return translation
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._community_origin_cache.clear()
        self._user_dict_cache.clear()
        logging.debug("词典缓存已清除")
    
    def search_dictionary(self, query, search_type='both'):
        """搜索词典
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型 ('key', 'origin', 'both')
            
        Returns:
            搜索结果列表
        """
        results = []
        
        if not self.user_dict:
            self.load_user_dictionary()
        
        # 搜索用户词典
        if self.user_dict:
            # 搜索按键词典
            if search_type in ('key', 'both'):
                for key, value in self.user_dict.get('by_key', {}).items():
                    if query.lower() in key.lower():
                        results.append({'type': 'user_key', 'key': key, 'value': value})
            
            # 搜索按原文词典
            if search_type in ('origin', 'both'):
                for origin, value in self.user_dict.get('by_origin_name', {}).items():
                    if query.lower() in origin.lower():
                        results.append({'type': 'user_origin', 'key': origin, 'value': value})
        
        # 搜索社区词典
        if self.community_dict_by_key and search_type in ('key', 'both'):
            for key, value in self.community_dict_by_key.items():
                if query.lower() in key.lower():
                    results.append({'type': 'community_key', 'key': key, 'value': value})
        
        if self.community_dict_by_origin and search_type in ('origin', 'both'):
            for origin, entries in self.community_dict_by_origin.items():
                if query.lower() in origin.lower():
                    for entry in entries:
                        results.append({'type': 'community_origin', 'key': origin, 'value': entry['trans']})
        
        return results
