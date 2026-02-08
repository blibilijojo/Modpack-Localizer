class ModpackLocalizerError(Exception):
    """Modpack Localizer 基础异常类"""
    def __init__(self, message, error_code=None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class ConfigurationError(ModpackLocalizerError):
    """配置错误异常"""
    pass

class ExtractionError(ModpackLocalizerError):
    """提取错误异常"""
    pass

class TranslationError(ModpackLocalizerError):
    """翻译错误异常"""
    pass

class BuildError(ModpackLocalizerError):
    """构建错误异常"""
    pass

class AIError(ModpackLocalizerError):
    """AI服务错误异常"""
    pass

class FileError(ModpackLocalizerError):
    """文件操作错误异常"""
    pass
