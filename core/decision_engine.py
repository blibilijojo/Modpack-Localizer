import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version
import re
import json

class DecisionEngine:
    def _resolve_origin_name_conflict(self, candidates: list[dict]) -> str | None:
        if not candidates: return None
        if len(candidates) == 1: return candidates[0]["trans"]
        trans_counts = Counter(c["trans"] for c in candidates)
        max_freq = max(trans_counts.values())
        top_candidates = [c for c in candidates if trans_counts[c["trans"]] == max_freq]
        if len(top_candidates) == 1: return top_candidates[0]["trans"]
        try:
            sorted_by_version = sorted(top_candidates, key=lambda c: parse_version(c["version"]), reverse=True)
            return sorted_by_version[0]["trans"]
        except Exception:
            return top_candidates[0]["trans"]

    def _is_valid_translation(self, text: str | None) -> bool:
        if not text or not text.strip():
            return False
        if re.search('[\u4e00-\u9fff]', text):
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

    def run(self, user_dictionary: dict, community_dict_by_key: dict, community_dict_by_origin: dict, 
            master_english_dicts: dict, internal_chinese_dicts: dict, pack_chinese_dict: dict, 
            use_origin_name_lookup: bool, namespace_to_jar: dict,
            raw_english_files: dict, namespace_formats: dict):
        logging.info("--- 阶段 2: 执行翻译决策逻辑 ---")
        workbench_data = defaultdict(lambda: {'jar_name': 'Unknown', 'items': []})
        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})
        total_entries = 0
        source_counts = Counter()

        for namespace, english_dict in master_english_dicts.items():
            jar_name = namespace_to_jar.get(namespace, 'Unknown')
            workbench_data[namespace]['jar_name'] = jar_name
            workbench_data[namespace]['display_name'] = f"{namespace} ({jar_name})"
            internal_chinese = internal_chinese_dicts.get(namespace, {})
            raw_content = raw_english_files.get(namespace)
            file_format = namespace_formats.get(namespace)
            if raw_content and file_format:
                ordered_keys = self._get_ordered_keys(raw_content, file_format)
            else:
                logging.warning(f"命名空间 '{namespace}' 缺少原始文件内容或格式信息，将使用无序字典进行回退。")
                ordered_keys = list(english_dict.keys())
            
            for key in ordered_keys:
                english_value = english_dict.get(key)
                if english_value is None:
                    continue

                total_entries += 1
                translation = None
                source = None
                potential_translation = None
                potential_source = None
                
                if key == '_comment':
                    if key in internal_chinese:
                        potential_translation = internal_chinese[key]
                        potential_source = "模组自带"
                else:
                    if key in user_dict_by_key:
                        potential_translation = user_dict_by_key[key]
                        potential_source = "个人词典[Key]"
                    elif use_origin_name_lookup and english_value in user_dict_by_origin:
                        potential_translation = user_dict_by_origin[english_value]
                        potential_source = "个人词典[原文]"
                    elif key in internal_chinese:
                        potential_translation = internal_chinese[key]
                        potential_source = "模组自带"
                    elif not re.search(r'[a-zA-Z]', english_value):
                        potential_translation = english_value
                        potential_source = "原文复制"
                    elif key in pack_chinese_dict:
                        potential_translation = pack_chinese_dict[key]
                        potential_source = "第三方汉化包"
                    elif key in community_dict_by_key:
                        potential_translation = community_dict_by_key[key]
                        potential_source = "社区词典[Key]"
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
                
                source_counts[item_entry['source']] += 1
                workbench_data[namespace]['items'].append(item_entry)
        
        logging.info("--- 翻译决策贡献分析 ---")
        logging.info(f"总条目数: {total_entries}")
        for source, count in sorted(source_counts.items()):
            percentage = (count / total_entries) * 100 if total_entries > 0 else 0
            logging.info(f"  ▷ {source}: {count} 条 ({percentage:.2f}%)")
        logging.info("--------------------------")
        
        logging.info("决策引擎运行完毕。")
        return dict(workbench_data)