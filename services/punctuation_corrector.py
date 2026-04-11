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
        # 不对括号进行任何添加修改，直接返回原文本
        return zh_text
    
    def process_start_punctuation(self, zh_text, en_punct):
        """
        处理开头标点
        """
        # 括号不处理
        if en_punct in '([{<"\'':
            return zh_text
        
        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            # 如果英文文本以标点开头
            if en_punct:
                # 如果中文文本以英文标点开头，替换为中文标点
                if zh_text.startswith(en_punct):
                    zh_text = zh_punct + zh_text[len(en_punct):]
                # 如果中文文本没有对应的标点，添加中文标点
                elif not zh_text.startswith(zh_punct):
                    zh_text = zh_punct + zh_text
        return zh_text
    
    def process_end_punctuation(self, zh_text, en_punct):
        """
        处理结尾标点
        """
        # 括号不处理
        if en_punct in ')]}>"\'':
            return zh_text
        
        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            # 如果英文文本以标点结尾
            if en_punct:
                # 如果中文文本以英文标点结尾，替换为中文标点
                if zh_text.endswith(en_punct):
                    zh_text = zh_text[:-len(en_punct)] + zh_punct
                # 如果中文文本没有对应的标点，添加中文标点
                elif not zh_text.endswith(zh_punct):
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
        
        # 连续句点不参与行首/行尾单点标点对齐（省略号在 _convert_all 中转为 …）
        import re
        ellipsis_pattern = r'\.{2,}'
        
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
        
        # 连续英文句点在 _convert_all_english_punctuation 中统一转为 …
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
            # 最后将译文的所有英文符号转化为对应的中文符号；连续 . 转为 …
            corrected_line = self._convert_all_english_punctuation(corrected_line)
            corrected_lines.append(corrected_line)
        
        # 处理行数不匹配的情况
        if len(zh_lines) > len(en_lines):
            for zh_line in zh_lines[len(en_lines):]:
                # 同样处理额外的行
                zh_line = self._convert_all_english_punctuation(zh_line)
                corrected_lines.append(zh_line)
        
        return '\n'.join(corrected_lines)
    
    def _convert_all_english_punctuation(self, text):
        """
        将文本中的英文标点转化为中文标点；连续三个及以上英文句点合并为省略号「…」；
        方括号 [] 保留不改为【】。
        """
        if not text:
            return text
        
        # 先处理省略号：整段连续 .（≥3）合并为一个占位符，最后再还原为 Unicode …
        import re
        ellipsis_pattern = r'\.{3,}'
        temp_text = re.sub(ellipsis_pattern, '__ELLIPSIS__', text)
        
        # 处理方括号，临时替换为特殊标记
        bracket_pattern = r'(\[|\])'
        bracket_matches = re.findall(bracket_pattern, temp_text)
        # 用特殊标记替换方括号
        temp_text = re.sub(r'\[', '__LEFT_BRACKET__', temp_text)
        temp_text = re.sub(r'\]', '__RIGHT_BRACKET__', temp_text)
        
        # 处理英文引号，将其替换为中文引号
        # 先将所有英文引号替换为特殊标记
        quote_pattern = r'"'
        quote_matches = re.findall(quote_pattern, temp_text)
        temp_text = re.sub(quote_pattern, '__QUOTE__', temp_text)
        
        # 替换其他英文标点
        for eng_punct, zh_punct in self.punctuation_map.items():
            temp_text = temp_text.replace(eng_punct, zh_punct)
        
        # 处理引号，将成对的引号替换为中文引号
        # 统计引号数量
        quote_count = temp_text.count('__QUOTE__')
        if quote_count > 0:
            # 替换引号，第一个为左引号，第二个为右引号，以此类推
            quote_index = 0
            result_text = ''
            i = 0
            while i < len(temp_text):
                if temp_text[i:i+9] == '__QUOTE__':
                    # 替换为中文引号
                    if quote_index % 2 == 0:
                        result_text += '“'
                    else:
                        result_text += '”'
                    quote_index += 1
                    i += 9
                else:
                    result_text += temp_text[i]
                    i += 1
            temp_text = result_text
        
        # 将特殊标记替换回省略号（U+2026）与方括号
        temp_text = temp_text.replace('__ELLIPSIS__', '…')
        temp_text = temp_text.replace('__LEFT_BRACKET__', '[')
        temp_text = temp_text.replace('__RIGHT_BRACKET__', ']')
        
        return temp_text

# 创建全局实例
punctuation_corrector = PunctuationCorrector()