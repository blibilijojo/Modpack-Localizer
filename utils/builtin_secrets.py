"""
内置密钥管理模块
用于在打包时嵌入敏感密钥，并防止其被写入配置文件
"""
import os

# 内置 CurseForge API 密钥（在构建时由 GitHub Secrets 注入）
BUILTIN_CURSEFORGE_API_KEY = os.environ.get('CURSEFORGE_API_KEY', '')

# 标记是否为内置密钥
IS_BUILTIN_CURSEFORGE_KEY = bool(BUILTIN_CURSEFORGE_API_KEY)


def get_builtin_curseforge_key() -> str:
    """获取内置的 CurseForge API 密钥"""
    return BUILTIN_CURSEFORGE_API_KEY


def is_builtin_curseforge_key_set() -> bool:
    """检查是否设置了内置 CurseForge API 密钥"""
    return IS_BUILTIN_CURSEFORGE_KEY


def is_protected_key(key: str, value: str) -> bool:
    """
    检查某个配置项是否为受保护的内置密钥
    
    Args:
        key: 配置项的键
        value: 配置项的值
        
    Returns:
        如果是受保护的内置密钥则返回 True
    """
    if key == 'curseforge_api_key' and IS_BUILTIN_CURSEFORGE_KEY:
        # 如果用户输入的值与内置密钥相同，则认为是受保护的
        if value.strip() == BUILTIN_CURSEFORGE_API_KEY:
            return True
    return False
