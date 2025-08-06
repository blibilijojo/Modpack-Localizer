# core/decision_engine.py

import logging
from collections import defaultdict

class DecisionEngine:
    # Parameter names are correct from the previous fix
    def run(self, community_dict: dict, master_english_dicts: dict, internal_chinese_dicts: dict, pack_chinese_dict: dict):
        logging.info("开始执行翻译决策逻辑...")
        final_translations_lookup = defaultdict(dict)
        items_for_ai = []

        # --- CORRECTED: The SyntaxError '在' is now fixed to 'in' ---
        for namespace, english_dict in master_english_dicts.items():
            internal_chinese = internal_chinese_dicts.get(namespace, {})
            
            for key, english_value in english_dict.items():
                # The priority order is correct as per the last request.
                
                # 1. Mod's own Chinese translation (Highest priority)
                if key in internal_chinese:
                    final_translations_lookup[namespace][key] = internal_chinese[key]
                
                # 2. Third-party pack translation (from .zip files)
                elif key in pack_chinese_dict:
                    final_translations_lookup[namespace][key] = pack_chinese_dict[key]
                
                # 3. Community Dictionary (from .db file)
                elif key in community_dict:
                    final_translations_lookup[namespace][key] = community_dict[key]
                
                # 4. AI translation or original English text (Lowest priority)
                else:
                    # Only send non-empty strings to AI
                    if english_value and not english_value.isspace():
                        items_for_ai.append((namespace, key, english_value))
                    # Keep the original English as a fallback
                    final_translations_lookup[namespace][key] = english_value
        
        total_final_entries = sum(len(d) for d in final_translations_lookup.values())
        logging.info(f"决策完成。最终条目: {total_final_entries}, 待AI翻译: {len(items_for_ai)}")
        return final_translations_lookup, items_for_ai