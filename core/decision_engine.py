import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version

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

    def run(self, user_dictionary: dict, community_dict_by_key: dict, community_dict_by_origin: dict, 
            master_english_dicts: dict, internal_chinese_dicts: dict, pack_chinese_dict: dict, 
            use_origin_name_lookup: bool, namespace_to_jar: dict):
        
        logging.info("开始执行翻译决策逻辑...")
        
        workbench_data = defaultdict(lambda: {'jar_name': 'Unknown', 'items': []})
        
        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})

        total_entries = 0
        untranslated_count = 0

        for namespace, english_dict in master_english_dicts.items():
            workbench_data[namespace]['jar_name'] = namespace_to_jar.get(namespace, 'Unknown')
            internal_chinese = internal_chinese_dicts.get(namespace, {})
            
            for key, english_value in english_dict.items():
                total_entries += 1
                translation = None
                source = None

                if key in user_dict_by_key:
                    translation = user_dict_by_key[key]
                    source = "个人词典[Key]"
                elif use_origin_name_lookup and english_value in user_dict_by_origin:
                    translation = user_dict_by_origin[english_value]
                    source = "个人词典[原文]"
                elif key in internal_chinese:
                    translation = internal_chinese[key]
                    source = "模组自带"
                elif key in pack_chinese_dict:
                    translation = pack_chinese_dict[key]
                    source = "第三方汉化包"
                elif key in community_dict_by_key:
                    translation = community_dict_by_key[key]
                    source = "社区词典[Key]"
                elif use_origin_name_lookup and english_value in community_dict_by_origin:
                    candidates = community_dict_by_origin[english_value]
                    best_translation = self._resolve_origin_name_conflict(candidates)
                    if best_translation:
                        translation = best_translation
                        source = "社区词典[原文]"

                item_entry = {
                    'key': key,
                    'en': english_value,
                    'zh': translation if translation is not None else '',
                    'source': source if source is not None else '待翻译'
                }
                
                if translation is None:
                    untranslated_count += 1

                workbench_data[namespace]['items'].append(item_entry)

        logging.info(f"决策完成。共处理 {total_entries} 条文本，其中 {untranslated_count} 条需要翻译。")
        
        return dict(workbench_data)