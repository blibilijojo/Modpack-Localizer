import logging
from collections import defaultdict, Counter
from functools import lru_cache
from packaging.version import parse as parse_version
import re
import json
from typing import Dict, List, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import (
    LanguageEntry, TranslationResult, NamespaceInfo,
    ExtractionResult
)

class Translator:
    """翻译决策引擎"""
    
    # 预编译正则表达式，避免重复编译
    PLACEHOLDER_PERCENT = re.compile(r'%\d*\$?[a-zA-Z]+')
    PLACEHOLDER_BRACE = re.compile(r'\$\{[^}]+\}')
    PLACEHOLDER_DOLLAR = re.compile(r'\$\d+')
    CHINESE_CHAR = re.compile('[一-鿿]')
    ENGLISH_LETTER = re.compile(r'[a-zA-Z]')
    JSON_KEY_VALUE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
    LANG_KEY_VALUE = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
    
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
    
    @staticmethod
    @lru_cache(maxsize=131072)
    def _is_valid_translation_cached(text: str) -> bool:
        """验证翻译是否有效（有界缓存，重复英文/译文可共用结果）"""
        if not text or not text.strip():
            return False
        cleaned = Translator.PLACEHOLDER_PERCENT.sub('', text)
        cleaned = Translator.PLACEHOLDER_BRACE.sub('', cleaned)
        cleaned = Translator.PLACEHOLDER_DOLLAR.sub('', cleaned)
        cleaned = cleaned.replace('%', '')
        if Translator.CHINESE_CHAR.search(cleaned):
            return True
        return not Translator.ENGLISH_LETTER.search(cleaned)

    def _is_valid_translation(self, text: Optional[str]) -> bool:
        """验证翻译是否有效"""
        if text is None:
            return False
        return self._is_valid_translation_cached(text)
    
    def _get_ordered_keys(self, content: str, file_format: str) -> List[str]:
        """获取有序键列表"""
        if file_format == 'json':
            return [m.group(1) for m in self.JSON_KEY_VALUE.finditer(content)]
        elif file_format == 'lang':
            return [m.group(1) for m in self.LANG_KEY_VALUE.finditer(content)]
        return []
    
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
        settings: Dict,
        namespace_info: NamespaceInfo,
        dictionary_manager=None
    ) -> Dict[str, LanguageEntry]:
        """处理单个命名空间的翻译"""
        ns_result = {}
        
        # 优化：直接使用 english_entries 的键，避免复杂的排序逻辑
        ordered_keys = list(english_entries.keys())
        
        # 预计算设置值，避免在循环中重复获取
        use_community_dict_key = settings.get('use_community_dict_key', True)
        use_community_dict_origin = settings.get('use_community_dict_origin', True)
        
        # 预计算常用词典的存在性，避免在循环中重复检查
        has_user_dict_key = bool(user_dict_by_key)
        has_user_dict_origin = bool(user_dict_by_origin)
        has_community_dict_key = bool(community_dict_by_key)
        has_community_dict_origin = bool(community_dict_by_origin)
        has_pack_chinese_dict = bool(pack_chinese_dict)
        
        for key in ordered_keys:
            english_entry = english_entries.get(key)
            if not english_entry:
                continue
            
            english_value = english_entry.en
            translation = None
            source = None
            
            if key.startswith('_comment'):
                # 处理带序号的 _comment 键
                if key in internal_chinese:
                    translation = internal_chinese[key].zh
                    source = "模组自带"
                else:
                    # 如果没有对应的中文，保持为空
                    translation = ""
                    source = "待翻译"
            else:
                # 按照优先级顺序：原文复制 → 模组自带 → 个人词典 → 第三方汉化包 → 社区词典
                
                # 1. 非英文内容直接保留（原文复制）
                if self._is_valid_translation(english_value):
                    translation = english_value
                    source = "原文复制"
                # 2. 模组自带中文
                elif key in internal_chinese:
                    translation = internal_chinese[key].zh
                    source = "模组自带"
                # 3. 个人词典（Key 优先）
                elif has_user_dict_key and key in user_dict_by_key:
                    translation = user_dict_by_key[key]
                    source = "个人词典 [Key]"
                elif has_user_dict_origin and english_value in user_dict_by_origin:
                    translation = user_dict_by_origin[english_value]
                    source = "个人词典 [原文]"
                # 4. 第三方汉化包
                elif has_pack_chinese_dict and key in pack_chinese_dict:
                    translation = pack_chinese_dict[key]
                    source = "第三方汉化包"
                # 5. 社区词典 [Key]
                elif use_community_dict_key and has_community_dict_key and key in community_dict_by_key:
                    translation = community_dict_by_key[key]
                    source = "社区词典 [Key]"
                # 6. 社区词典 [原文]（使用全局缓存避免重复计算）
                elif use_community_dict_origin and has_community_dict_origin and english_value in community_dict_by_origin:
                    if dictionary_manager:
                        # 使用词典管理器的全局缓存机制
                        best_translation = dictionary_manager.get_community_origin_translation(english_value)
                        if best_translation:
                            translation = best_translation
                            source = "社区词典 [原文]"
                    else:
                        candidates = community_dict_by_origin[english_value]
                        best_translation = self._resolve_origin_name_conflict(candidates)
                        if best_translation:
                            translation = best_translation
                            source = "社区词典 [原文]"
            
            # 验证翻译有效性（原文复制已在上方用同一判定，避免重复正则）
            if source != "原文复制" and not self._is_valid_translation(translation):
                translation = ""
                source = "待翻译"
            
            ns_result[key] = LanguageEntry(
                key=key,
                en=english_value,
                zh=translation,
                source=source,
                namespace=namespace
            )
        
        return ns_result
    
    def _get_entries_to_translate(self, namespace: str, english_entries: Dict[str, LanguageEntry], existing_translations: Dict[str, LanguageEntry], update_existing: bool) -> Dict[str, LanguageEntry]:
        """获取需要翻译的条目"""
        entries_to_translate = {}
        
        for key, entry in english_entries.items():
            if key.startswith('_comment'):
                continue
            
            # 检查是否需要翻译
            if update_existing:
                # 更新模式：所有条目都需要检查
                entries_to_translate[key] = entry
            else:
                # 新增模式：只翻译不存在的条目
                if key not in existing_translations:
                    entries_to_translate[key] = entry
        
        return entries_to_translate
    
    def _batch_translate(self, entries: Dict[str, LanguageEntry], batch_size: int = 20) -> Dict[str, str]:
        """批量翻译条目"""
        # 这里需要集成 AI 翻译服务
        # 暂时返回空结果，实际实现需要调用翻译 API
        return {}
    
    def _process_namespace_with_incremental(
        self, 
        namespace: str, 
        english_entries: Dict[str, LanguageEntry],
        existing_translations: Dict[str, LanguageEntry],
        user_dict_by_key: Dict[str, str],
        user_dict_by_origin: Dict[str, str],
        community_dict_by_key: Dict[str, str],
        community_dict_by_origin: Dict[str, List[Dict]],
        internal_chinese: Dict[str, LanguageEntry],
        pack_chinese_dict: Dict[str, str],
        settings: Dict,
        namespace_info: NamespaceInfo,
        update_existing: bool,
        dictionary_manager=None
    ) -> Dict[str, LanguageEntry]:
        """处理单个命名空间的翻译（支持增量更新）"""
        # 获取需要翻译的条目
        entries_to_translate = self._get_entries_to_translate(
            namespace, english_entries, existing_translations, update_existing
        )
        
        # 如果有需要翻译的条目，进行批量翻译
        if entries_to_translate:
            logging.info(f"命名空间 {namespace} 有 {len(entries_to_translate)} 个条目需要翻译")
            # 这里可以调用批量翻译方法
            # translated_entries = self._batch_translate(entries_to_translate)
        
        # 处理所有条目
        ns_result = {}
        ordered_keys = list(english_entries.keys())
        
        # 预计算设置值
        use_community_dict_key = settings.get('use_community_dict_key', True)
        use_community_dict_origin = settings.get('use_community_dict_origin', True)
        
        # 预计算常用词典的存在性
        has_user_dict_key = bool(user_dict_by_key)
        has_user_dict_origin = bool(user_dict_by_origin)
        has_community_dict_key = bool(community_dict_by_key)
        has_community_dict_origin = bool(community_dict_by_origin)
        has_pack_chinese_dict = bool(pack_chinese_dict)
        
        for key in ordered_keys:
            english_entry = english_entries.get(key)
            if not english_entry:
                continue
            
            english_value = english_entry.en
            translation = None
            source = None
            
            # 检查是否已有翻译
            if key in existing_translations and not update_existing:
                existing_entry = existing_translations[key]
                translation = existing_entry.zh
                source = existing_entry.source
            else:
                if key.startswith('_comment'):
                    # 处理带序号的 _comment 键
                    if key in internal_chinese:
                        translation = internal_chinese[key].zh
                        source = "模组自带"
                    else:
                        # 如果没有对应的中文，保持为空
                        translation = ""
                        source = "待翻译"
                else:
                    # 按照优先级顺序：原文复制 → 模组自带 → 个人词典 → 第三方汉化包 → 社区词典
                    
                    # 1. 非英文内容直接保留（原文复制）
                    if self._is_valid_translation(english_value):
                        translation = english_value
                        source = "原文复制"
                    # 2. 模组自带中文
                    elif key in internal_chinese:
                        translation = internal_chinese[key].zh
                        source = "模组自带"
                    # 3. 个人词典（Key 优先）
                    elif has_user_dict_key and key in user_dict_by_key:
                        translation = user_dict_by_key[key]
                        source = "个人词典 [Key]"
                    elif has_user_dict_origin and english_value in user_dict_by_origin:
                        translation = user_dict_by_origin[english_value]
                        source = "个人词典 [原文]"
                    # 4. 第三方汉化包
                    elif has_pack_chinese_dict and key in pack_chinese_dict:
                        translation = pack_chinese_dict[key]
                        source = "第三方汉化包"
                    # 5. 社区词典 [Key]
                    elif use_community_dict_key and has_community_dict_key and key in community_dict_by_key:
                        translation = community_dict_by_key[key]
                        source = "社区词典 [Key]"
                    # 6. 社区词典 [原文]
                    elif use_community_dict_origin and has_community_dict_origin and english_value in community_dict_by_origin:
                        if dictionary_manager:
                            # 使用词典管理器的全局缓存机制
                            best_translation = dictionary_manager.get_community_origin_translation(english_value)
                            if best_translation:
                                translation = best_translation
                                source = "社区词典 [原文]"
                        else:
                            candidates = community_dict_by_origin[english_value]
                            best_translation = self._resolve_origin_name_conflict(candidates)
                            if best_translation:
                                translation = best_translation
                                source = "社区词典 [原文]"
            
            # 验证翻译有效性
            if source != "原文复制" and not self._is_valid_translation(translation):
                translation = ""
                source = "待翻译"
            
            ns_result[key] = LanguageEntry(
                key=key,
                en=english_value,
                zh=translation,
                source=source,
                namespace=namespace
            )
        
        return ns_result
    
    def run(
        self, 
        extraction_result: ExtractionResult,
        user_dictionary: Dict,
        community_dict_by_key: Dict[str, str],
        community_dict_by_origin: Dict[str, List[Dict]],
        settings: Dict,
        dictionary_manager=None,
        existing_translations: Optional[Dict[str, Dict[str, LanguageEntry]]] = None,
        update_existing: bool = False
    ) -> TranslationResult:
        """执行翻译决策流程"""
        logging.info("--- 阶段 2: 执行翻译决策逻辑 ---")
        
        result = TranslationResult()
        workbench_data = result.workbench_data
        source_counts = result.source_counts
        
        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})
        
        namespaces = list(extraction_result.master_english.items())
        namespace_count = len(namespaces)
        
        if namespace_count <= 3:
            # 命名空间数量较少时使用串行处理
            logging.info(f"使用串行方式处理 {namespace_count} 个命名空间")
            for namespace, english_entries in namespaces:
                namespace_info = extraction_result.namespace_info.get(namespace, NamespaceInfo(name=namespace))
                internal_chinese = extraction_result.internal_chinese.get(namespace, {})
                existing_ns_translations = existing_translations.get(namespace, {}) if existing_translations else {}
                
                # 处理命名空间翻译
                if update_existing or not existing_ns_translations:
                    ns_result = self._process_namespace_with_incremental(
                        namespace=namespace,
                        english_entries=english_entries,
                        existing_translations=existing_ns_translations,
                        user_dict_by_key=user_dict_by_key,
                        user_dict_by_origin=user_dict_by_origin,
                        community_dict_by_key=community_dict_by_key,
                        community_dict_by_origin=community_dict_by_origin,
                        internal_chinese=internal_chinese,
                        pack_chinese_dict=extraction_result.pack_chinese,
                        settings=settings,
                        namespace_info=namespace_info,
                        update_existing=update_existing,
                        dictionary_manager=dictionary_manager
                    )
                else:
                    # 不需要更新，直接使用现有翻译
                    ns_result = existing_ns_translations
                
                workbench_data[namespace] = ns_result
                
                # 更新来源统计
                for entry in ns_result.values():
                    source = entry.source or "待翻译"
                    source_counts[source] = source_counts.get(source, 0) + 1
        else:
            # 命名空间数量较多时使用并行处理
            logging.info(f"使用并行方式处理 {namespace_count} 个命名空间")
            
            # 计算最佳线程数
            max_workers = min(8, namespace_count)  # 限制最大线程数为8
            
            def process_namespace_task(namespace, english_entries):
                namespace_info = extraction_result.namespace_info.get(namespace, NamespaceInfo(name=namespace))
                internal_chinese = extraction_result.internal_chinese.get(namespace, {})
                existing_ns_translations = existing_translations.get(namespace, {}) if existing_translations else {}
                
                if update_existing or not existing_ns_translations:
                    return namespace, self._process_namespace_with_incremental(
                        namespace=namespace,
                        english_entries=english_entries,
                        existing_translations=existing_ns_translations,
                        user_dict_by_key=user_dict_by_key,
                        user_dict_by_origin=user_dict_by_origin,
                        community_dict_by_key=community_dict_by_key,
                        community_dict_by_origin=community_dict_by_origin,
                        internal_chinese=internal_chinese,
                        pack_chinese_dict=extraction_result.pack_chinese,
                        settings=settings,
                        namespace_info=namespace_info,
                        update_existing=update_existing,
                        dictionary_manager=dictionary_manager
                    )
                else:
                    # 不需要更新，直接使用现有翻译
                    return namespace, existing_ns_translations
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                futures = [executor.submit(process_namespace_task, namespace, english_entries) for namespace, english_entries in namespaces]
                
                # 处理完成的任务
                for future in as_completed(futures):
                    namespace, ns_result = future.result()
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
