# utils/config_manager.py

import json
from pathlib import Path
import logging

CONFIG_FILE_PATH = Path("config.json")

DEFAULT_PROMPT = """
你是一名精通《我的世界》(Minecraft) 游戏模组的专业汉化者。
请将输入JSON数组中的每一个英文短语或句子精确地翻译成简体中文。

核心翻译规则：
- **精准翻译**: 必须保持原文的技术术语、游戏机制和语气。
- **格式保留**: 必须完整保留原文中的所有格式化代码（例如 %s, %d, §a, \n 等）。
- **数量一致**: 返回的JSON数组中的元素数量必须与输入数组严格相等。

输出格式要求：
- 你的回复**必须且只能是**一个符合JSON规范的数组，例如 ["翻译1", "翻译2", ...]。
- **绝对不要**在回复中包含任何JSON格式之外的解释性文字、注释或代码块标记 (```json ... ```)。

输入: {input_texts}
"""

DEFAULT_CONFIG = {
    "api_keys": [], "model": "gemini-1.5-flash-latest", "model_list": [],
    "prompt": DEFAULT_PROMPT.strip(),
    "api_endpoint": "", "use_grounding": False, "ai_batch_size": 50, "ai_max_threads": 4,
    "ai_max_retries": 3, "ai_retry_interval": 2, "mods_dir": "", "output_dir": "",
    "community_dict_path": "",
    "community_pack_paths": [], 
    "pack_settings_presets": {
        "默认预案": {"pack_format_key": "1.20 - 1.20.1 (Format 15)", "pack_format": 15, "pack_description": "一个由Modpack Localizer生成的汉化包", "pack_icon_path": ""}
    },
    "last_pack_settings": {
        "pack_format_key": "1.20 - 1.20.1 (Format 15)", "pack_format": 15, "pack_description": "一个由Modpack Localizer生成的汉化包", "pack_icon_path": ""},
    "use_github_proxy": True,
    "last_dict_version": "" # --- 关键修改：默认值改为空字符串 ---
}

def load_config() -> dict:
    if not CONFIG_FILE_PATH.exists():
        logging.info("未找到配置文件，正在创建默认的 config.json...")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        config_updated = False

        if "global_dict_path" in config and "community_dict_path" not in config:
            config["community_dict_path"] = config.pop("global_dict_path")
            config_updated = True
            
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                logging.warning(f"配置文件中缺少 '{key}' 项目，将使用默认值进行补充。")
                config[key] = value
                config_updated = True
        
        if "github_proxies" in config:
            del config["github_proxies"]
            config_updated = True

        if config_updated:
            logging.info("配置文件已自动更新和补充，正在保存...")
            save_config(config)

        return config

    except (json.JSONDecodeError, TypeError):
        logging.error("配置文件格式错误或损坏，将加载默认配置并覆盖旧文件。")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config_data: dict):
    try:
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存配置文件时出错: {e}")