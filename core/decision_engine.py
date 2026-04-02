import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version
import re
import json
from typing import List, Dict, Any, Tuple

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

class DecisionEngine:
    def __init__(self):
        pass
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
            # 使用正则表达式解析JSON文件，保持原始顺序
            JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
            for match in JSON_KEY_VALUE_PATTERN.finditer(content):
                key = match.group(1)
                keys.append(key)
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
            'display_name': namespace,  # 只使用命名空间，不包含jar_name
            'git_name': "",  # 默认设置为空字符串
            'items': []
        }
        ns_source_counts = Counter()
        
        # 获取有序键
        if raw_content and file_format:
            # 从原始文件中提取有序键
            original_ordered_keys = self._get_ordered_keys(raw_content, file_format)
            
            # 处理带有计数器后缀的 _comment 条目
            ordered_keys = []
            comment_counter = 0
            for key in original_ordered_keys:
                if key == '_comment':
                    comment_counter += 1
                    # 查找对应的带有计数器后缀的键
                    for entry_key in english_dict.keys():
                        if entry_key == f'_comment_{comment_counter}':
                            ordered_keys.append(entry_key)
                            break
                else:
                    # 对于非 _comment 键，直接添加
                    ordered_keys.append(key)
        else:
            ordered_keys = list(english_dict.keys())
        
        # 确保所有英文词典中的键都被包含
        all_keys = set(english_dict.keys())
        ordered_keys_set = set(ordered_keys)
        missing_keys = all_keys - ordered_keys_set
        
        # 将缺失的键添加到有序键列表末尾
        ordered_keys.extend(list(missing_keys))
        
        for key in ordered_keys:
            english_value = english_dict.get(key)
            if english_value is None:
                continue

            translation = None
            source = None
            potential_translation = None
            potential_source = None
            
            if key.startswith('_comment'):
                # 处理带序号的 _comment 键
                if key in internal_chinese:
                    potential_translation = internal_chinese[key]
                    potential_source = "模组自带"
                else:
                    # 如果没有对应的中文，保持为空
                    potential_translation = ''
                    potential_source = '待翻译'
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
                # 3. 非英文内容直接保留，或者只有符号和字母s的内容（如%s）
                elif not re.search(r'[a-zA-Z]', english_value) or re.match(r'^[\W\s]*s*[\W\s]*$', english_value):
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
        """
        兼容旧版 DecisionEngine 的接口（薄封装）。

        统一委托给 `core/translator.py`，避免决策逻辑出现多套实现。
        """
        logging.info("翻译决策开始（委托实现）")

        from .translator import Translator
        from .models import ExtractionResult, LanguageEntry, NamespaceInfo

        extraction_result = ExtractionResult()
        extraction_result.raw_english_files = raw_english_files or {}
        extraction_result.pack_chinese = pack_chinese_dict or {}

        # 收集所有 namespace（避免某些来源只存在其一）
        all_namespaces = set(master_english_dicts.keys()) | set(internal_chinese_dicts.keys())

        for ns in all_namespaces:
            extraction_result.namespace_info[ns] = NamespaceInfo(
                name=ns,
                jar_name=namespace_to_jar.get(ns, "Unknown"),
                file_format=namespace_formats.get(ns, "json"),
                raw_content=(raw_english_files or {}).get(ns, ""),
            )

        # master_english：key -> en
        for ns, english_dict in (master_english_dicts or {}).items():
            extraction_result.master_english[ns] = {
                key: LanguageEntry(key=key, en=en_value, namespace=ns)
                for key, en_value in (english_dict or {}).items()
            }

        # internal_chinese：key -> zh
        for ns, zh_dict in (internal_chinese_dicts or {}).items():
            extraction_result.internal_chinese[ns] = {
                key: LanguageEntry(key=key, en="", zh=zh_value, namespace=ns)
                for key, zh_value in (zh_dict or {}).items()
            }

        # 调用统一的翻译决策引擎
        translator = Translator()
        translation_result = translator.run(
            extraction_result=extraction_result,
            user_dictionary=user_dictionary,
            community_dict_by_key=community_dict_by_key,
            community_dict_by_origin=community_dict_by_origin,
            use_origin_name_lookup=use_origin_name_lookup,
            dictionary_manager=None,
        )

        # 转回旧版 workbench_data 结构
        workbench_data = {}
        for ns, entries in (translation_result.workbench_data or {}).items():
            items = []
            for key, entry in entries.items():
                items.append({
                    "key": key,
                    "en": entry.en,
                    "zh": entry.zh or "",
                    "source": entry.source or "待翻译",
                })

            workbench_data[ns] = {
                "jar_name": namespace_to_jar.get(ns, "Unknown"),
                "display_name": ns,
                "git_name": "",
                "items": items,
            }

        return workbench_data