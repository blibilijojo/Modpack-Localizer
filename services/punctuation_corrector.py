import re

class PunctuationCorrector:
    """
    标点修正器，用于自动检测和修正翻译文本中的标点符号
    """
    
    def __init__(self):
        # 中英文标点映射
        self.punctuation_map = {
            '.': '。',
            ',': '，',
            '!': '！',
            '?': '？',
            ':': '：',
            ';': '；',
            '(': '（',
            ')': '）',
            '[': '【',
            ']': '】',
            '{': '｛',
            '}': '｝',
            '<': '＜',
            '>': '＞',
            '"': '"',
            "'": "'"
        }
        
        # 标点对
        self.punctuation_pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '<': '>',
            '"': '"',
            "'": "'"
        }
    
    def detect_punctuation(self, text):
        """
        检测文本中的标点符号
        """
        punctuation_pattern = r'[.!?,;:()\[\]{}<>"\']'
        return re.findall(punctuation_pattern, text)
    
    def get_chinese_punct(self, eng_punct, is_end=False):
        """
        获取对应的中文标点
        """
        return self.punctuation_map.get(eng_punct, eng_punct)
    
    def process_punctuation_pairs(self, zh_text, start_punct, end_punct):
        """
        处理标点对（如括号、引号）
        """
        # 检测中文文本中是否已有对应的标点对
        start_punct_zh = self.get_chinese_punct(start_punct)
        end_punct_zh = self.get_chinese_punct(end_punct)
        
        # 统计开始和结束标点的数量
        start_count = zh_text.count(start_punct_zh)
        end_count = zh_text.count(end_punct_zh)
        
        # 如果开始标点数量大于结束标点数量，添加缺少的结束标点
        if start_count > end_count:
            zh_text += end_punct_zh * (start_count - end_count)
        # 如果结束标点数量大于开始标点数量，添加缺少的开始标点
        elif end_count > start_count:
            zh_text = start_punct_zh * (end_count - start_count) + zh_text
        
        return zh_text
    
    def process_start_punctuation(self, zh_text, en_punct):
        """
        处理开头标点
        """
        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            # 如果英文文本以标点开头，但中文文本没有，添加对应的中文标点
            if en_punct and not zh_text.startswith(zh_punct):
                zh_text = zh_punct + zh_text
        return zh_text
    
    def process_end_punctuation(self, zh_text, en_punct):
        """
        处理结尾标点
        """
        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            # 如果英文文本以标点结尾，但中文文本没有，添加对应的中文标点
            if en_punct and not zh_text.endswith(zh_punct):
                zh_text = zh_text + zh_punct
        return zh_text
    
    def process_single_line(self, en_line, zh_line):
        """
        处理单行文本的标点
        """
        if not en_line or not zh_line:
            return zh_line
        
        # 检测英文文本中的标点
        en_punctuations = self.detect_punctuation(en_line)
        
        if not en_punctuations:
            return zh_line
        
        # 检测并处理连续英文句号（省略号）
        import re
        ellipsis_pattern = r'\.{2,}'
        ellipsis_matches = re.findall(ellipsis_pattern, en_line)
        
        # 处理开头标点
        if en_line[0] in self.punctuation_map:
            # 检查是否是连续英文句号的开始
            if not re.match(ellipsis_pattern, en_line[:2]):
                zh_line = self.process_start_punctuation(zh_line, en_line[0])
        
        # 处理结尾标点
        if en_line[-1] in self.punctuation_map:
            # 检查是否是连续英文句号的结束
            if not re.search(ellipsis_pattern, en_line[-2:]):
                zh_line = self.process_end_punctuation(zh_line, en_line[-1])
        
        # 处理标点对
        for start_punct, end_punct in self.punctuation_pairs.items():
            if start_punct in en_line and end_punct in en_line:
                zh_line = self.process_punctuation_pairs(zh_line, start_punct, end_punct)
        
        # 处理省略号特殊情况 - 保持连续英文句号不变
        for ellipsis in ellipsis_matches:
            if ellipsis not in zh_line:
                # 如果中文文本中没有相同的省略号，保持英文省略号不变
                pass
        
        return zh_line
    
    def correct_punctuation(self, en_text, zh_text):
        """
        修正标点符号的主函数
        """
        if not en_text or not zh_text:
            return zh_text
        
        # 按行处理
        en_lines = en_text.split('\n')
        zh_lines = zh_text.split('\n')
        
        corrected_lines = []
        for i, (en_line, zh_line) in enumerate(zip(en_lines, zh_lines)):
            corrected_line = self.process_single_line(en_line, zh_line)
            corrected_lines.append(corrected_line)
        
        # 处理行数不匹配的情况
        if len(zh_lines) > len(en_lines):
            corrected_lines.extend(zh_lines[len(en_lines):])
        
        return '\n'.join(corrected_lines)

# 创建全局实例
punctuation_corrector = PunctuationCorrector()