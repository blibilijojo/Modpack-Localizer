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
你是 Minecraft（我的世界）本地化专家，只输出 JSON。
任务：将输入 JSON 对象中每个数字键对应的英文文本翻译为简体中文。

核心规范（必须严格遵守）：
1. 仅翻译文本，不改动 JSON 结构；输出键必须与输入数字键完全一致。
1.1 输入值可能是字符串，或对象 {"text":"原文","key":"资源键"}；若是对象，仅翻译 text 字段，并将 key 作为语义上下文参考。
2. 严格保留格式与控制符：%s、%d、{0}、%1$s、\\n、\\t、§样式码、HTML/颜色标签、命令参数等。
3. 严格保留占位符顺序、数量与拼写，不得新增/删除/重排占位符。
4. 严格保留 Minecraft 资源标识符与命名空间 ID（如 minecraft:zombie、item.minecraft.apple），不翻译 ID 本体。
5. 采用 Minecraft 语境与通用译名，避免生硬直译；同一术语前后保持一致。
6. 针对游戏文本按场景翻译：
   - 刷怪蛋/实体相关：体现“X 刷怪蛋”等游戏内叫法，避免误译为现实词义。
   - 玩家死亡消息：保持“被……”“因……而死”等死亡播报语气与句式。
   - 隐藏式字幕/音效字幕（Subtitles）：必须像“字幕标签”而不是一句话——短、名词化、无句号；若文本内含方向符号/箭头（如 <、>）必须保留；不要擅自添加/移除任何颜色或样式代码（§e 等），只在原文已有时保留。
   - 进度/提示/系统消息：保持简洁、可读、符合原版提示风格。
7. 标点与大小写风格尽量贴近原文功能：专有名词、按键名、指令片段不要误改。
8. 若文本已是中文、为空、或仅符号/ID/占位符，返回原文。

输出要求：
- 你的回复必须是且只能是一个 JSON 对象，例如 {"0":"译文1","1":"译文2"}。
- 禁止输出任何额外说明、代码块标记或前后缀文本。

输入：{input_data_json}
"""

DEFAULT_CONFIG = {
    "api_services": [], "model": "gpt-3.5-turbo", "model_list": [],
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
    "use_community_dict_key": True,
    "use_community_dict_origin": True,
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
        
        # 检查并清理可能泄露的内置密钥
        try:
            from utils.builtin_secrets import get_builtin_curseforge_key
            builtin_key = get_builtin_curseforge_key()
            if builtin_key:
                # 如果配置文件中错误地包含了内置密钥，立即清除它
                if config.get('curseforge_api_key', '').strip() == builtin_key:
                    config['curseforge_api_key'] = ''
                    logging.warning("检测到配置文件中包含内置密钥，已自动清除以防止泄露")
                    save_config(config)  # 立即保存清理后的配置
        except ImportError:
            pass
        
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
        
        if "prompt" in config:
            logging.info("检测到旧版 prompt 配置，已迁移为仅使用代码内置提示词。")
            del config["prompt"]
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
        # prompt 已弃用：始终使用代码内置提示词，禁止写入配置文件
        config_to_save.pop("prompt", None)
        try:
            from utils.builtin_secrets import get_builtin_curseforge_key
            builtin_key = get_builtin_curseforge_key()
            current_key = config_to_save.get('curseforge_api_key', '').strip()
            
            # 只要有内置密钥，并且当前配置中的密钥非空，就清空它
            # 这样可以确保内置密钥永远不会被写入配置文件
            if builtin_key and current_key:
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
