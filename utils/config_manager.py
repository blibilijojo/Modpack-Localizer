import json
import sqlite3
from pathlib import Path
import logging

CONFIG_FILE_PATH = Path("config.json")
USER_DICT_PATH = Path("Dict-User.db")

# 数据库初始化函数
def _init_user_dict_db():
    conn = sqlite3.connect(USER_DICT_PATH)
    cursor = conn.cursor()
    
    # 创建表：by_key表存储以key为索引的翻译
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS by_key (
        key TEXT PRIMARY KEY,
        translation TEXT NOT NULL
    )
    ''')
    
    # 创建表：by_origin_name表存储以原文为索引的翻译
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS by_origin_name (
        origin_name TEXT PRIMARY KEY,
        translation TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

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
    "log_retention_days": 10,
    "max_log_count": 30,
    "theme": "litera",
    # 社区词典导入过滤设置
    "community_dict_filter": {
        "max_word_count": 0,  # 原文最大单词数，0表示不限制
        "require_chinese_translation": True  # 译文必须包含中文
    },
    "github_proxies": [
        "https://gh-proxy.org/",
        "https://hk.gh-proxy.org/",
        "https://cdn.gh-proxy.org/",
        "https://edgeone.gh-proxy.org/"
    ],
    
    # AI翻译批次处理默认值
    "ai_batch_count": 10,       # 批次数默认值
    "ai_batch_items": 200,      # 每批次条目数默认值
    "ai_batch_words": 2000,      # 每批次单词数默认值
    # 配置加密密钥管理
    "saved_encryption_key": ""          # 保存的加密密钥（加密存储）
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
        logging.debug("配置已自动保存")
    except Exception as e:
        logging.error(f"保存配置文件时出错: {e}")

# 添加自动保存功能，包装原有的config_manager.save_config函数
def auto_save_config(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # 自动保存配置
        save_config(args[0])
        return result
    return wrapper

# 为配置更新操作添加自动保存
def update_config(key, value):
    """更新配置项并自动保存"""
    config = load_config()
    config[key] = value
    save_config(config)
    return config

# 批量更新配置项并自动保存
def update_config_batch(updates):
    """批量更新配置项并自动保存"""
    config = load_config()
    config.update(updates)
    save_config(config)
    return config

def load_user_dict() -> dict:
    # 确保数据库和表存在
    _init_user_dict_db()
    
    conn = sqlite3.connect(USER_DICT_PATH)
    cursor = conn.cursor()
    
    # 从by_key表读取数据
    cursor.execute("SELECT key, translation FROM by_key")
    by_key = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 从by_origin_name表读取数据
    cursor.execute("SELECT origin_name, translation FROM by_origin_name")
    by_origin_name = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {"by_key": by_key, "by_origin_name": by_origin_name}

def save_user_dict(dict_data: dict):
    try:
        # 确保数据库和表存在
        _init_user_dict_db()
        
        conn = sqlite3.connect(USER_DICT_PATH)
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute("DELETE FROM by_key")
        cursor.execute("DELETE FROM by_origin_name")
        
        # 插入by_key数据
        for key, translation in dict_data.get("by_key", {}).items():
            cursor.execute("INSERT OR REPLACE INTO by_key (key, translation) VALUES (?, ?)", (key, translation))
        
        # 插入by_origin_name数据
        for origin_name, translation in dict_data.get("by_origin_name", {}).items():
            cursor.execute("INSERT OR REPLACE INTO by_origin_name (origin_name, translation) VALUES (?, ?)", (origin_name, translation))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"保存用户个人词典时出错: {e}")