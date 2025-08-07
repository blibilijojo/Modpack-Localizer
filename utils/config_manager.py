import json
from pathlib import Path
import logging

CONFIG_FILE_PATH = Path("config.json")

DEFAULT_PROMPT = """
你是一名精通《我的世界》(Minecraft) 游戏模组的专业汉化者，并且是一个严格遵循指令的JSON格式化工具。
你的任务是：将输入的JSON数组中的每一个英文短语或句子精确地翻译成简体中文。

**绝对核心规则 (必须严格遵守):**
1.  **数量严格相等**: 输出的JSON数组中的元素数量，必须与输入的JSON数组严格相等。不允许增加或减少任何一个元素。
2.  **格式完全保留**: 必须完整保留原文中的所有格式化代码（例如 `%s`, `%d`, `§a`, `\n` 等）。这些是程序代码，绝对不能翻译或修改。
3.  **精确翻译**: 在保证以上规则的前提下，对游戏术语进行精准翻译。

**输出格式要求 (这是最重要的规则):**
-   你的回复**必须且只能是**一个符合JSON规范的数组，例如 `["翻译1", "翻译2", ...]`。
-   **绝对禁止**在回复的JSON数组前后添加任何解释性文字、注释、代码块标记 (```json ... ```) 或任何其他字符。你的回复必须以 `[` 开始，以 `]` 结束。

**示例:**
-   **输入:** `["Hello, %s!", "Lava Bucket"]`
-   **你的输出:** `["你好, %s!", "熔岩桶"]`

**输入:** {input_texts}
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
    "last_dict_version": "0.0.0",
    "use_origin_name_lookup": True
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