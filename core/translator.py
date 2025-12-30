import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version
import re
import json
from typing import Dict, List, Any, Optional

from .models import (
    LanguageEntry, TranslationResult, NamespaceInfo,
    ExtractionResult
)

class Translator:
    """翻译决策引擎"""
    
    def __init__(self):
        pass
    
    def _resolve_origin_name_conflict(self, candidates: List[Dict]) -> Optional[str]:
        """解决原文翻译冲突"""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]["trans"]
        
        trans_counts = Counter(c["trans"] for c in candidates)
        max_freq = max(trans_counts.values())
        top_candidates = [c for c in candidates if trans_counts[c["trans"]] == max_freq]
        
        if len(top_candidates) == 1:
            return top_candidates[0]["trans"]
        
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
    
    def _is_valid_translation(self, text: Optional[str]) -> bool:
        """验证翻译是否有效"""
        if not text:
            return False
        if not text.strip():
            return False
        if re.search('[一-鿿]', text):
            return True
        if re.search(r'[a-zA-Z]', text):
            return False
        return True
    
    def _get_ordered_keys(self, content: str, file_format: str) -> List[str]:
        """获取有序键列表"""
        keys = []
        if file_format == 'json':
            try:
                data = json.loads(content)
                return list(data.keys())
            except json.JSONDecodeError:
                return []
        elif file_format == 'lang':
            lang_kv_pattern = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
            for match in lang_kv_pattern.finditer(content):
                keys.append(match.group(1))
        return keys
    
    def _process_namespace(
        self, 
        namespace: str, 
        english_entries: Dict[str, LanguageEntry],
        user_dict_by_key: Dict[str, str],
        user_dict_by_origin: Dict[str, str],
        community_dict_by_key: Dict[str, str],
        community_dict_by_origin: Dict[str, List[Dict]],
        internal_chinese: Dict[str, LanguageEntry],
        pack_chinese_dict: Dict[str, str],
        use_origin_name_lookup: bool,
        namespace_info: NamespaceInfo
    ) -> Dict[str, LanguageEntry]:
        """处理单个命名空间的翻译"""
        ns_result = {}
        
        # 获取有序键
        ordered_keys = []
        if namespace_info.raw_content and namespace_info.file_format:
            ordered_keys = self._get_ordered_keys(namespace_info.raw_content, namespace_info.file_format)
        
        if not ordered_keys:
            ordered_keys = list(english_entries.keys())
        
        # 确保所有英文词典中的键都被包含
        all_keys = set(english_entries.keys())
        ordered_keys_set = set(ordered_keys)
        missing_keys = all_keys - ordered_keys_set
        ordered_keys.extend(list(missing_keys))
        
        for key in ordered_keys:
            english_entry = english_entries.get(key)
            if not english_entry:
                continue
            
            english_value = english_entry.en
            translation = None
            source = None
            
            if key == '_comment':
                if key in internal_chinese:
                    translation = internal_chinese[key].zh
                    source = "模组自带"
            else:
                # 按照优先级顺序：模组自带 → 个人词典 → 社区词典key → 社区词典原文
                
                # 1. 模组自带中文
                if key in internal_chinese:
                    translation = internal_chinese[key].zh
                    source = "模组自带"
                # 2. 个人词典（Key优先）
                elif key in user_dict_by_key:
                    translation = user_dict_by_key[key]
                    source = "个人词典[Key]"
                elif use_origin_name_lookup and english_value in user_dict_by_origin:
                    translation = user_dict_by_origin[english_value]
                    source = "个人词典[原文]"
                # 3. 非英文内容直接保留
                elif not re.search(r'[a-zA-Z]', english_value):
                    translation = english_value
                    source = "原文复制"
                # 4. 第三方汉化包
                elif key in pack_chinese_dict:
                    translation = pack_chinese_dict[key]
                    source = "第三方汉化包"
                # 5. 社区词典[Key]
                elif key in community_dict_by_key:
                    translation = community_dict_by_key[key]
                    source = "社区词典[Key]"
                # 6. 社区词典[原文]
                elif use_origin_name_lookup and english_value in community_dict_by_origin:
                    candidates = community_dict_by_origin[english_value]
                    best_translation = self._resolve_origin_name_conflict(candidates)
                    if best_translation:
                        translation = best_translation
                        source = "社区词典[原文]"
            
            # 验证翻译有效性
            if not self._is_valid_translation(translation):
                translation = ""
                source = "待翻译"
            
            # 创建翻译结果
            result_entry = LanguageEntry(
                key=key,
                en=english_value,
                zh=translation,
                source=source,
                namespace=namespace
            )
            
            ns_result[key] = result_entry
        
        return ns_result
    
    def run(
        self, 
        extraction_result: ExtractionResult,
        user_dictionary: Dict,
        community_dict_by_key: Dict[str, str],
        community_dict_by_origin: Dict[str, List[Dict]],
        use_origin_name_lookup: bool
    ) -> TranslationResult:
        """执行翻译决策流程"""
        logging.info("--- 阶段 2: 执行翻译决策逻辑 ---")
        
        result = TranslationResult()
        workbench_data = result.workbench_data
        source_counts = result.source_counts
        
        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})
        
        logging.info(f"使用串行方式处理 {len(extraction_result.master_english)} 个命名空间")
        
        for namespace, english_entries in extraction_result.master_english.items():
            namespace_info = extraction_result.namespace_info.get(namespace, NamespaceInfo(name=namespace))
            internal_chinese = extraction_result.internal_chinese.get(namespace, {})
            
            # 处理命名空间翻译
            ns_result = self._process_namespace(
                namespace=namespace,
                english_entries=english_entries,
                user_dict_by_key=user_dict_by_key,
                user_dict_by_origin=user_dict_by_origin,
                community_dict_by_key=community_dict_by_key,
                community_dict_by_origin=community_dict_by_origin,
                internal_chinese=internal_chinese,
                pack_chinese_dict=extraction_result.pack_chinese,
                use_origin_name_lookup=use_origin_name_lookup,
                namespace_info=namespace_info
            )
            
            workbench_data[namespace] = ns_result
            
            # 更新来源统计
            for entry in ns_result.values():
                source = entry.source or "待翻译"
                source_counts[source] = source_counts.get(source, 0) + 1
        
        # 计算总条目数
        result.total_entries = sum(len(entries) for entries in workbench_data.values())
        
        # 输出统计信息
        logging.info("--- 翻译决策贡献分析 ---")
        logging.info(f"总条目数: {result.total_entries}")
        for source, count in sorted(source_counts.items()):
            percentage = (count / result.total_entries) * 100 if result.total_entries > 0 else 0
            logging.info(f"  ▷ {source}: {count} 条 ({percentage:.2f}%)")
        logging.info("--------------------------")
        
        logging.info("翻译决策引擎运行完毕。")
        return result
