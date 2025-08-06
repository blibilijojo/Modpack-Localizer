# core/decision_engine.py

import logging
from collections import defaultdict, Counter
from packaging.version import parse as parse_version

class DecisionEngine:

    def _resolve_origin_name_conflict(self, candidates: list[dict]) -> str | None:
        """
        智能仲裁机制，用于解决 ORIGIN_NAME 匹配到的多个翻译冲突。
        """
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]["trans"]

        trans_counts = Counter(c["trans"] for c in candidates)
        max_freq = max(trans_counts.values())
        
        top_candidates = [
            c for c in candidates if trans_counts[c["trans"]] == max_freq
        ]

        if len(top_candidates) == 1:
            return top_candidates[0]["trans"]
        
        try:
            sorted_by_version = sorted(
                top_candidates, 
                key=lambda c: parse_version(c["version"]),
                reverse=True
            )
            return sorted_by_version[0]["trans"]
        except Exception:
            return top_candidates[0]["trans"]

    def run(self, community_dict_by_key: dict, community_dict_by_origin: dict, 
            master_english_dicts: dict, internal_chinese_dicts: dict, pack_chinese_dict: dict, 
            use_origin_name_lookup: bool):
        
        logging.info("开始执行翻译决策逻辑...")
        final_translations_lookup = defaultdict(dict)
        items_for_ai = []
        
        key_contribution_count = 0
        origin_name_contribution_count = 0

        for namespace, english_dict in master_english_dicts.items():
            internal_chinese = internal_chinese_dicts.get(namespace, {})
            
            for key, english_value in english_dict.items():
                if key in internal_chinese:
                    final_translations_lookup[namespace][key] = internal_chinese[key]
                
                elif key in pack_chinese_dict:
                    final_translations_lookup[namespace][key] = pack_chinese_dict[key]
                
                elif key in community_dict_by_key:
                    final_translations_lookup[namespace][key] = community_dict_by_key[key]
                    key_contribution_count += 1
                
                elif use_origin_name_lookup and english_value in community_dict_by_origin:
                    candidates = community_dict_by_origin[english_value]
                    best_translation = self._resolve_origin_name_conflict(candidates)
                    if best_translation:
                        final_translations_lookup[namespace][key] = best_translation
                        origin_name_contribution_count += 1
                    else:
                        if english_value and not english_value.isspace():
                            items_for_ai.append((namespace, key, english_value))
                        final_translations_lookup[namespace][key] = english_value
                
                else:
                    if english_value and not english_value.isspace():
                        items_for_ai.append((namespace, key, english_value))
                    final_translations_lookup[namespace][key] = english_value
        
        total_final_entries = sum(len(d) for d in final_translations_lookup.values())
        logging.info(f"决策完成。最终条目: {total_final_entries}, 待AI翻译: {len(items_for_ai)}")
        
        return final_translations_lookup, items_for_ai, key_contribution_count, origin_name_contribution_count