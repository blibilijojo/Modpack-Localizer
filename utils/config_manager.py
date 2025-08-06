# utils/config_manager.py

import json
from pathlib import Path
import logging

CONFIG_FILE_PATH = Path("config.json")

# --- MODIFICATION: Restored the explicit JSON instruction in the prompt ---
# This is crucial when not using a strict response_schema.
DEFAULT_PROMPT = """
你是一名精通《我的世界》(Minecraft) 游戏模组的专业汉化者。
请将输入JSON数组中的每一个英文短语或句子精确地翻译成简体中文。

核心翻译规则：
- **精准翻译**: 必须保持原文的技术术语、游戏机制和语气。
- **格式保留**: 必须完整保留原文中的所有格式化代码（例如 %s, %d, §a, \n 等）。

你的回复必须只包含一个JSON数组，数组元素为翻译后的字符串。

输入: {input_texts}
"""

DEFAULT_CONFIG = {
    "api_keys": [], "model": "gemini-1.5-flash-latest", "model_list": [],
    "prompt": DEFAULT_PROMPT.strip(),
    "api_endpoint": "", "use_grounding": False, "ai_batch_size": 50, "ai_max_threads": 4,
    "ai_max_retries": 3, "ai_retry_interval": 2, "mods_dir": "", "output_dir": "",
    "community_pack_paths": [], 
    "pack_settings_presets": {
        "默认预案": {"pack_format_key": "1.20 - 1.20.1 (Format 15)", "pack_format": 15, "pack_description": "一个由Modpack Localizer生成的汉化包", "pack_icon_path": ""}
    },
    "last_pack_settings": {
        "pack_format_key": "1.20 - 1.20.1 (Format 15)", "pack_format": 15, "pack_description": "一个由Modpack Localizer生成的汉化包", "pack_icon_path": ""}
}

# ... [load_config and save_config methods remain unchanged] ...
def load_config() -> dict:
    if not CONFIG_FILE_PATH.exists():
        logging.info("未找到配置文件，正在创建默认的 config.json...")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                config.setdefault(key, value)
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