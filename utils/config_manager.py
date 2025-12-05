import json
from pathlib import Path
import logging

CONFIG_FILE_PATH = Path("config.json")
USER_DICT_PATH = Path("user_dict.json")

DEFAULT_PROMPT = """
你是一个只输出JSON的翻译AI。
任务：将输入JSON对象中，每个数字键对应的字符串值翻译为简体中文。
核心指令:
1. 保持所有格式代码 (如 %s, §a, \n) 不变。
2. 返回的JSON对象的键必须与输入的数字键完全一致。
最终要求:
你的回复必须是、且只能是一个JSON对象, 例如 `{"0": "译文1", "1": "译文2"}`。
禁止在 `[` 和 `]` 或 `{` 和 `}` 的前后添加任何多余的文字或代码标记。
输入: {input_data_json}
"""

DEFAULT_CONFIG = {
    "api_keys": [], "api_keys_raw": "", "model": "gpt-3.5-turbo", "model_list": [],
    "prompt": DEFAULT_PROMPT.strip(),
    "api_endpoint": "", "use_grounding": False, "ai_batch_size": 50, "ai_max_threads": 4,
    "ai_stream_timeout": 30,
    "ai_max_retries": 3,
    "ai_retry_initial_delay": 2.0,
    "ai_retry_max_delay": 120.0,
    "ai_retry_backoff_factor": 2.0,
    "ai_retry_rate_limit_cooldown": 60.0,
    "mods_dir": "", "output_dir": "",
    "community_dict_path": "",
    "community_pack_paths": [],
    "pack_settings_presets": {
        "默认预案": {
            "pack_format_key": "1.20 - 1.20.1 (Format 15)",
            "pack_format": 15,
            "pack_description": "",
            "pack_icon_path": "",
        }
    },
    "last_pack_settings": {
        "pack_format_key": "1.20 - 1.20.1 (Format 15)",
        "pack_format": 15,
        "pack_description": "",
        "pack_icon_path": "",
    },
    "find_replace_settings": {
        "find_text": "",
        "replace_text": "",
        "match_case": False,
        "wrap": True,
        "scope": "current",
        "direction": "down",
        "search_column": "all"
    },
    "use_github_proxy": True,
    "pack_as_zip": False,
    "last_dict_version": "0.0.0",
    "use_origin_name_lookup": True,
    "translation_mode": "ai",
    "log_level": "INFO",
    "theme": "litera"
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
        if "api_keys_raw" not in config and "api_keys" in config:
            logging.warning("检测到旧版配置，正在迁移API密钥以在UI中保留格式...")
            config["api_keys_raw"] = "\n".join(config["api_keys"])
            config_updated = True
        presets = config.get("pack_settings_presets", {})
        if "默认预案" in presets and presets["默认预案"].get("pack_description", "") != "":
             logging.warning("检测到旧的'默认预案'简介，将自动清空以启用动态生成功能。")
             config["pack_settings_presets"]["默认预案"]["pack_description"] = ""
             config_updated = True
        last_settings = config.get("last_pack_settings", {})
        old_desc = "一个由Modpack Localizer生成的汉化包"
        if last_settings.get("pack_description", "") == old_desc:
             logging.warning("检测到旧的'最后使用的设置'简介，将自动清空。")
             config["last_pack_settings"]["pack_description"] = ""
             config_updated = True
        if "global_dict_path" in config and "community_dict_path" not in config:
            config["community_dict_path"] = config.pop("global_dict_path")
            config_updated = True
        if "ai_retry_interval" in config:
            del config["ai_retry_interval"]
            config_updated = True
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                logging.warning(f"配置文件中缺少 '{key}' 项目，将使用默认值进行补充。")
                config[key] = value
                config_updated = True
        if "github_proxies" in config:
            del config["github_proxies"]
            config_updated = True
        if '数字键' not in config.get("prompt", ""):
            logging.warning("检测到旧版AI提示词，已自动更新为最稳健的键值对模式。")
            config["prompt"] = DEFAULT_PROMPT.strip()
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

def load_user_dict() -> dict:
    if not USER_DICT_PATH.exists():
        return {"by_key": {}, "by_origin_name": {}}
    try:
        with open(USER_DICT_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "by_key" not in data: data["by_key"] = {}
            if "by_origin_name" not in data: data["by_origin_name"] = {}
            return data
    except (json.JSONDecodeError, TypeError):
        logging.error(f"用户个人词典 ({USER_DICT_PATH}) 格式错误或损坏，已创建新的空词典。")
        return {"by_key": {}, "by_origin_name": {}}

def save_user_dict(dict_data: dict):
    try:
        with open(USER_DICT_PATH, 'w', encoding='utf-8') as f:
            json.dump(dict_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存用户个人词典时出错: {e}")