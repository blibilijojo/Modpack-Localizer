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
        移除文本中多余的空格
        
        规则：
        1. 移除行首和行尾的空格
        2. 移除中文标点符号前后的空格
        3. 移除连续的空格
        4. 保留中英文混合文本中必要的空格
        
        Args:
            text: 输入文本
            
        Returns:
            处理后的文本
        """
        if not text:
            return text
        
        # 按行处理
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            # 1. 移除行首和行尾的空格
            line = line.strip()
            
            # 2. 移除中文标点符号前的空格
            for punct in self.chinese_punctuation:
                line = line.replace(f' {punct}', punct)
            
            # 3. 移除中文标点符号后的空格（除了某些特殊情况）
            for punct in self.chinese_punctuation:
                # 避免移除引号后的必要空格
                if punct not in ['"', "'", ')', '）', ']', '】', '>', '》']:
                    line = line.replace(f'{punct} ', punct)
            
            # 4. 移除连续的空格，替换为单个空格
            line = re.sub(r' {2,}', ' ', line)
            
            processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
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
