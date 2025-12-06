import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version
import re
import json
from typing import List, Dict, Any, Tuple
from core.term_database import TermDatabase
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

class DecisionEngine:
    def __init__(self):
        self.term_db = TermDatabase()
    def _resolve_origin_name_conflict(self, candidates: list[dict]) -> str | None:
        if not candidates: return None
        if len(candidates) == 1: return candidates[0]["trans"]
        trans_counts = Counter(c["trans"] for c in candidates)
        max_freq = max(trans_counts.values())
        top_candidates = [c for c in candidates if trans_counts[c["trans"]] == max_freq]
        if len(top_candidates) == 1: return top_candidates[0]["trans"]
        
        # 优化版本解析，处理无效版本号
        def get_version_key(candidate):
            try:
                return parse_version(candidate["version"])
            except Exception:
                # 对于无效版本号，返回一个最低优先级的版本对象
                return parse_version("0.0.0")
                
        try:
            sorted_by_version = sorted(top_candidates, key=get_version_key, reverse=True)
            return sorted_by_version[0]["trans"]
        except Exception:
            return top_candidates[0]["trans"]

    def _is_valid_translation(self, text: str | List[str] | None) -> bool:
        if not text:
            return False
        # 如果是列表，取第一个元素
        if isinstance(text, list):
            text = text[0] if text else ""
        if not text.strip():
            return False
        if re.search('[一-鿿]', text):
            return True
        if re.search(r'[a-zA-Z]', text):
            return False
        return True

    def _get_ordered_keys(self, content: str, file_format: str) -> list[str]:
        keys = []
        if file_format == 'json':
            try:
                data = json.loads(content)
                return list(data.keys())
            except json.JSONDecodeError:
                logging.warning(f"为决策引擎解析JSON以获取有序键时失败。此文件的顺序可能不被保留。")
                return []
        elif file_format == 'lang':
            lang_kv_pattern = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
            for match in lang_kv_pattern.finditer(content):
                keys.append(match.group(1))
        return keys

    def _process_namespace(self, namespace: str, english_dict: dict, user_dict_by_key: dict, user_dict_by_origin: dict, 
                          community_dict_by_key: dict, community_dict_by_origin: dict, internal_chinese: dict, 
                          pack_chinese_dict: dict, use_origin_name_lookup: bool, jar_name: str, 
                          raw_content: str, file_format: str) -> tuple[dict, Counter]:
        """
        处理单个命名空间的翻译决策
        Args:
            namespace: 命名空间
            english_dict: 英文词典
            user_dict_by_key: 按Key查找的用户词典
            user_dict_by_origin: 按原文查找的用户词典
            community_dict_by_key: 按Key查找的社区词典
            community_dict_by_origin: 按原文查找的社区词典
            internal_chinese: 模组内部中文词典
            pack_chinese_dict: 第三方汉化包词典
            use_origin_name_lookup: 是否使用原文查找
            jar_name: 模组名称
            raw_content: 原始文件内容
            file_format: 文件格式
        Returns:
            命名空间的工作台数据和来源统计
        """
        ns_data = {
            'jar_name': jar_name,
            'display_name': f"{namespace} ({jar_name})",
            'items': []
        }
        ns_source_counts = Counter()
        
        # 获取有序键
        if raw_content and file_format:
            ordered_keys = self._get_ordered_keys(raw_content, file_format)
        else:
            ordered_keys = list(english_dict.keys())
        
        for key in ordered_keys:
            english_value = english_dict.get(key)
            if english_value is None:
                continue

            translation = None
            source = None
            potential_translation = None
            potential_source = None
            
            if key == '_comment':
                if key in internal_chinese:
                    potential_translation = internal_chinese[key]
                    potential_source = "模组自带"
            else:
                # 按照优先级顺序：模组自带 → 个人词典 → 社区词典key → 社区词典原文
                # 移除术语库在初始翻译决策中的参与
                
                # 1. 模组自带中文
                if key in internal_chinese:
                    potential_translation = internal_chinese[key]
                    potential_source = "模组自带"
                # 2. 个人词典（Key优先）
                elif key in user_dict_by_key:
                    potential_translation = user_dict_by_key[key]
                    potential_source = "个人词典[Key]"
                elif use_origin_name_lookup and english_value in user_dict_by_origin:
                    potential_translation = user_dict_by_origin[english_value]
                    potential_source = "个人词典[原文]"
                # 3. 非英文内容直接保留
                elif not re.search(r'[a-zA-Z]', english_value):
                    potential_translation = english_value
                    potential_source = "原文复制"
                # 4. 第三方汉化包
                elif key in pack_chinese_dict:
                    potential_translation = pack_chinese_dict[key]
                    potential_source = "第三方汉化包"
                # 5. 社区词典[Key]
                elif key in community_dict_by_key:
                    potential_translation = community_dict_by_key[key]
                    potential_source = "社区词典[Key]"
                # 6. 社区词典[原文]
                elif use_origin_name_lookup and english_value in community_dict_by_origin:
                    candidates = community_dict_by_origin[english_value]
                    best_translation = self._resolve_origin_name_conflict(candidates)
                    if best_translation:
                        potential_translation = best_translation
                        potential_source = "社区词典[原文]"

            if self._is_valid_translation(potential_translation):
                translation = potential_translation
                source = potential_source
            
            item_entry = {
                'key': key,
                'en': english_value,
                'zh': translation if translation is not None else '',
                'source': source if source is not None else '待翻译'
            }
            
            ns_source_counts[item_entry['source']] += 1
            ns_data['items'].append(item_entry)
        
        return ns_data, ns_source_counts

    def run(self, user_dictionary: dict, community_dict_by_key: dict, community_dict_by_origin: dict, 
            master_english_dicts: dict, internal_chinese_dicts: dict, pack_chinese_dict: dict, 
            use_origin_name_lookup: bool, namespace_to_jar: dict,
            raw_english_files: dict, namespace_formats: dict):
        logging.info("--- 阶段 2: 执行翻译决策逻辑 ---")
        workbench_data = {}
        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})
        total_entries = 0
        source_counts = Counter()
        
        # 对于CPU密集型任务，串行处理可能比并行更高效（避免GIL开销）
        # 直接使用串行处理，提高稳定性和性能
        logging.info(f"使用串行方式处理 {len(master_english_dicts)} 个命名空间")
        
        for namespace, english_dict in master_english_dicts.items():
            jar_name = namespace_to_jar.get(namespace, 'Unknown')
            internal_chinese = internal_chinese_dicts.get(namespace, {})
            raw_content = raw_english_files.get(namespace)
            file_format = namespace_formats.get(namespace)
            
            # 直接调用处理方法
            ns_data, ns_source_counts = self._process_namespace(
                namespace, english_dict, user_dict_by_key, user_dict_by_origin,
                community_dict_by_key, community_dict_by_origin, internal_chinese,
                pack_chinese_dict, use_origin_name_lookup, jar_name,
                raw_content, file_format
            )
            
            workbench_data[namespace] = ns_data
            source_counts.update(ns_source_counts)
            total_entries += len(ns_data['items'])
            logging.debug(f"命名空间 '{namespace}' 处理完成，共 {len(ns_data['items'])} 条")
        
        logging.info("--- 翻译决策贡献分析 ---")
        logging.info(f"总条目数: {total_entries}")
        for source, count in sorted(source_counts.items()):
            percentage = (count / total_entries) * 100 if total_entries > 0 else 0
            logging.info(f"  ▷ {source}: {count} 条 ({percentage:.2f}%)")
        logging.info("--------------------------")
        
        logging.info("决策引擎运行完毕。")
        return workbench_data