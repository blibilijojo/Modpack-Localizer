import logging
from pathlib import Path
import sqlite3
from collections import defaultdict
from utils import config_manager

class DictionaryManager:
    """词典管理模块，集中处理词典加载和管理功能"""
    
    def __init__(self):
        self.user_dict = None
        self.community_dict_by_key = None
        self.community_dict_by_origin = None
        self._cache = {}
    
    def load_user_dictionary(self):
        """加载用户词典"""
        try:
            self.user_dict = config_manager.load_user_dict()
            logging.info("用户词典加载成功")
            return self.user_dict
        except Exception as e:
            logging.error(f"加载用户词典失败: {e}")
            return {'by_key': {}, 'by_origin_name': {}}
    
    def load_community_dictionary(self, community_dict_path):
        """加载社区词典"""
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        
        if community_dict_path and Path(community_dict_path).is_file():
            try:
                with sqlite3.connect(f"file:{community_dict_path}?mode=ro", uri=True) as con:
                    cur = con.cursor()
                    cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
                    for key, origin_name, trans_name, version in cur.fetchall():
                        if key:
                            community_dict_by_key[key] = trans_name
                        if origin_name and trans_name:
                            community_dict_by_origin[origin_name].append({"trans": trans_name, "version": version or "0.0.0"})
                logging.info(f"社区词典加载成功，包含 {len(community_dict_by_key)} 个按键条目和 {len(community_dict_by_origin)} 个按原文条目")
            except sqlite3.Error as e:
                logging.error(f"读取社区词典数据库时发生错误: {e}")
        
        self.community_dict_by_key = community_dict_by_key
        self.community_dict_by_origin = community_dict_by_origin
        return community_dict_by_key, community_dict_by_origin
    
    def get_all_dictionaries(self, community_dict_path):
        """获取所有词典数据"""
        # 检查缓存
        cache_key = f"all_dicts_{community_dict_path or 'none'}"
        if cache_key in self._cache:
            logging.debug("从缓存中获取词典数据")
            return self._cache[cache_key]
        
        # 加载词典
        user_dict = self.load_user_dictionary()
        community_dict_by_key, community_dict_by_origin = self.load_community_dictionary(community_dict_path)
        
        # 缓存结果
        result = (user_dict, community_dict_by_key, community_dict_by_origin)
        self._cache[cache_key] = result
        
        return result
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
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
