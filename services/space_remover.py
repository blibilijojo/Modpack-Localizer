import re


class SpaceRemover:
    """
    空格移除器，用于移除翻译文本中多余的空格
    """
    
    def __init__(self):
        # 中文标点符号（前后不应有空格）
        self.chinese_punctuation = "，。！？；：""''（）【】《》、·～—…—·"
        
    def remove_extra_spaces(self, text):
        """
        移除文本中所有空格
        
        规则：直接删除译文中的全部空格
        
        Args:
            text: 输入文本
            
        Returns:
            处理后的文本
        """
        if not text:
            return text
        
        # 直接删除所有空格
        return text.replace(' ', '')
    
    def process_text(self, en_text, zh_text):
        """
        处理翻译文本，移除多余空格
        
        Args:
            en_text: 英文原文（用于参考）
            zh_text: 中文译文
            
        Returns:
            处理后的中文译文
        """
        if not zh_text:
            return zh_text
        
        return self.remove_extra_spaces(zh_text)


# 创建全局实例
space_remover = SpaceRemover()
