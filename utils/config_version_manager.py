import logging
from typing import Dict, Any, Callable, List


class ConfigMigration:
    """配置迁移基类"""
    
    def __init__(self, from_version: str, to_version: str, migration_func: Callable):
        self.from_version = from_version
        self.to_version = to_version
        self.migration_func = migration_func
    
    def apply(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """应用迁移"""
        return self.migration_func(config)


class ConfigVersionManager:
    """配置版本管理器"""
    
    CURRENT_VERSION = "2.0.0"
    
    def __init__(self):
        self.migrations: List[ConfigMigration] = []
        self._register_migrations()
    
    def _register_migrations(self):
        """注册所有迁移"""
        pass
    
    def get_config_version(self, config: Dict[str, Any]) -> str:
        """获取配置版本"""
        return config.get("_config_version", "1.0.0")
    
    def set_config_version(self, config: Dict[str, Any], version: str) -> Dict[str, Any]:
        """设置配置版本"""
        config["_config_version"] = version
        return config
    
    def needs_migration(self, config: Dict[str, Any]) -> bool:
        """检查是否需要迁移"""
        current_version = self.get_config_version(config)
        return current_version != self.CURRENT_VERSION
    
    def migrate(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行配置迁移"""
        from_version = self.get_config_version(config)
        
        if from_version == self.CURRENT_VERSION:
            return config
        
        logging.info(f"配置需要从版本 {from_version} 迁移到 {self.CURRENT_VERSION}")
        
        for migration in self.migrations:
            if migration.from_version == from_version:
                config = migration.apply(config)
                from_version = migration.to_version
                logging.info(f"已迁移到版本 {from_version}")
                if from_version == self.CURRENT_VERSION:
                    break
        
        config = self.set_config_version(config, self.CURRENT_VERSION)
        logging.info(f"配置迁移完成，当前版本: {self.CURRENT_VERSION}")
        return config


# 实例化配置版本管理器
config_version_manager = ConfigVersionManager()
