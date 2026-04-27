from __future__ import annotations
import re

_ELLIPSIS_PATTERN = re.compile(r'\.{2,}')
_ELLIPSIS_REPLACE_PATTERN = re.compile(r'\.{3,}')
_BRACKET_PATTERN = re.compile(r'(\[|\])')
_QUOTE_PATTERN = re.compile(r'"')
_PUNCTUATION_DETECT_PATTERN = re.compile(r'[.!?,;:()\[\]{}<>"\']')

_PUNCTUATION_MAP = {
    '.': '。', ',': '，', '!': '！', '?': '？',
    ':': '：', ';': '；', '(': '（', ')': '）',
    '[': '【', ']': '】', '{': '｛', '}': '｝',
    '<': '＜', '>': '＞', '"': '"', "'": "'"
}

_PUNCTUATION_PAIRS = {
    '(': ')', '[': ']', '{': '}', '<': '>', '"': '"', "'": "'"
}

_TRANSLATE_MAP = str.maketrans({k: v for k, v in _PUNCTUATION_MAP.items() if k not in ('[', ']', '"', "'")})

_START_PUNCTS = frozenset('([{<"\'')
_END_PUNCTS = frozenset(')]}>"\'')


class PunctuationCorrector:

    PUNCTUATION_MAP = _PUNCTUATION_MAP
    PUNCTUATION_PAIRS = _PUNCTUATION_PAIRS

    def detect_punctuation(self, text: str) -> list[str]:
        return _PUNCTUATION_DETECT_PATTERN.findall(text)

    def get_chinese_punct(self, eng_punct: str, is_end: bool = False) -> str:
        return _PUNCTUATION_MAP.get(eng_punct, eng_punct)

    def process_punctuation_pairs(self, zh_text: str, start_punct: str, end_punct: str) -> str:
        return zh_text

    def process_start_punctuation(self, zh_text: str, en_punct: str) -> str:
        if en_punct in _START_PUNCTS:
            return zh_text

        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            if zh_text.startswith(en_punct):
                zh_text = zh_punct + zh_text[len(en_punct):]
            elif not zh_text.startswith(zh_punct):
                zh_text = zh_punct + zh_text
        return zh_text

    def process_end_punctuation(self, zh_text: str, en_punct: str) -> str:
        if en_punct in _END_PUNCTS:
            return zh_text

        if en_punct and zh_text:
            zh_punct = self.get_chinese_punct(en_punct)
            if zh_text.endswith(en_punct):
                zh_text = zh_text[:-len(en_punct)] + zh_punct
            elif not zh_text.endswith(zh_punct):
                zh_text = zh_text + zh_punct
        return zh_text

    def process_single_line(self, en_line: str, zh_line: str) -> str:
        if not en_line or not zh_line:
            return zh_line

        en_punctuations = self.detect_punctuation(en_line)

        if not en_punctuations:
            return zh_line

        if en_line[0] in _PUNCTUATION_MAP:
            if not _ELLIPSIS_PATTERN.match(en_line[:2]):
                zh_line = self.process_start_punctuation(zh_line, en_line[0])

        if en_line[-1] in _PUNCTUATION_MAP:
            if not _ELLIPSIS_PATTERN.search(en_line[-2:]):
                zh_line = self.process_end_punctuation(zh_line, en_line[-1])

        for start_punct, end_punct in _PUNCTUATION_PAIRS.items():
            if start_punct in en_line and end_punct in en_line:
                zh_line = self.process_punctuation_pairs(zh_line, start_punct, end_punct)

        return zh_line

    def correct_punctuation(self, en_text: str, zh_text: str) -> str:
        if not en_text or not zh_text:
            return zh_text

        en_lines = en_text.split('\n')
        zh_lines = zh_text.split('\n')

        corrected_lines = []
        for en_line, zh_line in zip(en_lines, zh_lines):
            corrected_line = self.process_single_line(en_line, zh_line)
            corrected_line = self._convert_all_english_punctuation(corrected_line)
            corrected_lines.append(corrected_line)

        if len(zh_lines) > len(en_lines):
            for zh_line in zh_lines[len(en_lines):]:
                zh_line = self._convert_all_english_punctuation(zh_line)
                corrected_lines.append(zh_line)

        return '\n'.join(corrected_lines)

    def _convert_all_english_punctuation(self, text: str) -> str:
        if not text:
            return text

        temp_text = _ELLIPSIS_REPLACE_PATTERN.sub('__ELLIPSIS__', text)

        temp_text = _BRACKET_PATTERN.sub(
            lambda m: '__LEFT_BRACKET__' if m.group(1) == '[' else '__RIGHT_BRACKET__',
            temp_text
        )

        temp_text = _QUOTE_PATTERN.sub('__QUOTE__', temp_text)

        temp_text = temp_text.translate(_TRANSLATE_MAP)

        quote_count = temp_text.count('__QUOTE__')
        if quote_count > 0:
            parts = temp_text.split('__QUOTE__')
            result_parts = []
            for i, part in enumerate(parts[:-1]):
                result_parts.append(part)
                result_parts.append('\u201c' if i % 2 == 0 else '\u201d')
            result_parts.append(parts[-1])
            temp_text = ''.join(result_parts)

        temp_text = temp_text.replace('__ELLIPSIS__', '…')
        temp_text = temp_text.replace('__LEFT_BRACKET__', '[')
        temp_text = temp_text.replace('__RIGHT_BRACKET__', ']')

        return temp_text


punctuation_corrector = PunctuationCorrector()
