import json
import sqlite3
from pathlib import Path
import logging
import os
import sys

# 处理 PyInstaller 和 Nuitka 单文件打包时的路径问题
def get_app_data_path():
    # 检测是否为打包环境（支持 PyInstaller 和 Nuitka）
    is_frozen = getattr(sys, 'frozen', False) or getattr(sys, 'nuitka', False)
    if is_frozen:
        return Path(sys.executable).parent
    else:
        return Path.cwd()

APP_DATA_PATH = get_app_data_path()
CONFIG_FILE_PATH = APP_DATA_PATH / "config.json"
USER_DICT_PATH = APP_DATA_PATH / "Dict-User.db"

# 数据库初始化函数
def _init_user_dict_db():
    conn = sqlite3.connect(USER_DICT_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS by_key (
        key TEXT PRIMARY KEY,
        translation TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS by_origin_name (
        origin_name TEXT PRIMARY KEY,
        translation TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

DEFAULT_PROMPT = """
你是一个只输出 JSON 的翻译 AI。
任务：将输入 JSON 对象中，每个数字键对应的字符串值翻译为简体中文。
核心指令:
1. 保持所有格式代码 (如 %s, §a, \n) 不变。
2. 返回的 JSON 对象的键必须与输入的数字键完全一致。
最终要求:
你的回复必须是、且只能是一个 JSON 对象，例如 `{"0": "译文 1", "1": "译文 2"}`。
禁止在 `[` 和 `]` 或 `{` 和 `}` 的前后添加任何多余的文字或代码标记。
输入：{input_data_json}
"""

DEFAULT_CONFIG = {
    "api_services": [], "model": "gpt-3.5-turbo", "model_list": [],
    "prompt": DEFAULT_PROMPT.strip(),
    "use_grounding": False, "ai_batch_size": 50, "ai_max_threads": 4,
    "ai_max_retries": 3,
    "ai_retry_initial_delay": 2.0,
    "ai_retry_max_delay": 120.0,
    "ai_retry_backoff_factor": 2.0,
    "ai_retry_rate_limit_cooldown": 60.0,
    "mods_dir": "", "output_dir": "",
    "community_dict_dir": "",
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
    "pack_as_zip": False,
    "last_dict_version": "0.0.0",
    "use_origin_name_lookup": True,
    "translation_mode": "ai",
    "log_level": "INFO",
    "log_retention_days": 10,
    "max_log_count": 30,
    "theme": "litera",
    "community_dict_filter": {
        "max_word_count": 0,
        "require_chinese_translation": True
    },
    "github_proxies": [
        "https://edgeone.gh-proxy.org/",
        "https://hk.gh-proxy.org/",
        "https://cdn.gh-proxy.org/",
        "https://gh-proxy.org/"
    ],
    "github_repo": "",
    "github_token": "",
    "ai_batch_count": 10,
    "ai_batch_items": 200,
    "ai_batch_words": 2000,
    "curseforge_api_key": "",
}

def load_config() -> dict:
    if not CONFIG_FILE_PATH.exists():
        logging.info("未找到配置文件，正在创建默认的 config.json...")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 注入内置 CurseForge API 密钥（如果存在且用户未自定义）
        try:
            from utils.builtin_secrets import get_builtin_curseforge_key
            builtin_key = get_builtin_curseforge_key()
            if builtin_key:
                # 只有当配置文件中没有设置密钥时，才使用内置密钥
                if not config.get('curseforge_api_key', '').strip():
                    config['curseforge_api_key'] = builtin_key
                    logging.debug("已加载内置 CurseForge API 密钥")
                else:
                    logging.debug("检测到用户自定义 CurseForge API 密钥，将优先使用用户设置")
        except ImportError:
            pass
        config_updated = False
        
        if "api_keys_raw" not in config and "api_keys" in config:
            logging.warning("检测到旧版配置，正在迁移 API 密钥以在 UI 中保留格式...")
            config["api_keys_raw"] = "\n".join(config["api_keys"])
            config_updated = True
        
        presets = config.get("pack_settings_presets", {})
        if "默认预案" in presets and presets["默认预案"].get("pack_description", "") != "":
             logging.warning("检测到旧的'默认预案'简介，将自动清空以启用动态生成功能。")
             config["pack_settings_presets"]["默认预案"]["pack_description"] = ""
             config_updated = True
        
        last_settings = config.get("last_pack_settings", {})
        old_desc = "一个由 Modpack Localizer 生成的汉化包"
        if last_settings.get("pack_description", "") == old_desc:
             logging.warning("检测到旧的'最后使用的设置'简介，将自动清空。")
             config["last_pack_settings"]["pack_description"] = ""
             config_updated = True
        
        if "global_dict_path" in config and "community_dict_path" not in config:
            config["community_dict_path"] = config.pop("global_dict_path")
            config_updated = True
        
        if "community_dict_path" in config and "community_dict_dir" not in config:
            import os
            old_path = config["community_dict_path"]
            if old_path:
                config["community_dict_dir"] = os.path.dirname(old_path)
            else:
                config["community_dict_dir"] = ""
            del config["community_dict_path"]
            config_updated = True
        
        if not config.get("community_dict_dir"):
            config["community_dict_dir"] = str(APP_DATA_PATH)
            config_updated = True
        
        if "ai_retry_interval" in config:
            del config["ai_retry_interval"]
            config_updated = True
        
        if "api_keys" in config and "api_services" not in config:
            logging.warning("检测到旧版 API 密钥配置，将自动转换为新版服务配置格式。")
            api_keys = config.get("api_keys", [])
            api_endpoint = config.get("api_endpoint", "")
            api_keys_raw = config.get("api_keys_raw", "")
            
            if api_keys:
                config["api_services"] = [{
                    "endpoint": api_endpoint,
                    "keys": api_keys,
                    "keys_raw": api_keys_raw
                }]
            else:
                config["api_services"] = []
            
            config_updated = True
        
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                logging.warning(f"配置文件中缺少 '{key}' 项目，将使用默认值进行补充。")
                config[key] = value
                config_updated = True
        
        if '数字键' not in config.get("prompt", ""):
            logging.warning("检测到旧版 AI 提示词，已自动更新为最稳健的键值对模式。")
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
        # 防止内置密钥被写入配置文件
        config_to_save = config_data.copy()
        try:
            from utils.builtin_secrets import is_protected_key, get_builtin_curseforge_key
            if get_builtin_curseforge_key():
                # 如果设置了内置密钥，则从保存的配置中移除
                if config_to_save.get('curseforge_api_key', '').strip() == get_builtin_curseforge_key():
                    config_to_save['curseforge_api_key'] = ''
                    logging.debug("已阻止内置 CurseForge API 密钥写入配置文件")
        except ImportError:
            pass
        
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4, ensure_ascii=False)
        logging.debug("配置已自动保存")
    except Exception as e:
        logging.error(f"保存配置文件时出错：{e}")

def auto_save_config(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        save_config(args[0])
        return result
    return wrapper

def update_config(key, value):
    config = load_config()
    config[key] = value
    save_config(config)
    return config

def update_config_batch(updates):
    config = load_config()
    config.update(updates)
    save_config(config)
    return config

def load_user_dict() -> dict:
    _init_user_dict_db()
    
    conn = sqlite3.connect(USER_DICT_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT key, translation FROM by_key")
    by_key = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.execute("SELECT origin_name, translation FROM by_origin_name")
    by_origin_name = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {"by_key": by_key, "by_origin_name": by_origin_name}

def save_user_dict(dict_data: dict):
    try:
        _init_user_dict_db()
        
        conn = sqlite3.connect(USER_DICT_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT key FROM by_key")
        existing_keys = set(row[0] for row in cursor.fetchall())
        
        cursor.execute("SELECT origin_name FROM by_origin_name")
        existing_origins = set(row[0] for row in cursor.fetchall())
        
        new_keys = set(dict_data.get("by_key", {}).keys())
        
        for key in existing_keys - new_keys:
            cursor.execute("DELETE FROM by_key WHERE key = ?", (key,))
        
        for key, translation in dict_data.get("by_key", {}).items():
            cursor.execute("INSERT OR REPLACE INTO by_key (key, translation) VALUES (?, ?)", (key, translation))
        
        new_origins = set(dict_data.get("by_origin_name", {}).keys())
        
        for origin_name in existing_origins - new_origins:
            cursor.execute("DELETE FROM by_origin_name WHERE origin_name = ?", (origin_name,))
        
        for origin_name, translation in dict_data.get("by_origin_name", {}).items():
            cursor.execute("INSERT OR REPLACE INTO by_origin_name (origin_name, translation) VALUES (?, ?)", (origin_name, translation))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"保存用户个人词典时出错：{e}")
