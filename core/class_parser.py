"""Java .class 文件常量池解析和字符串提取的共享工具。"""

from __future__ import annotations
import struct
import logging
import re
from pathlib import Path


_CAMEL_CASE = re.compile(r"^[a-z]+[A-Z][a-zA-Z]*$")
_SNAKE_CASE = re.compile(r"^[a-z]+(_[a-z0-9]+)+$")
_DOT_IDENT = re.compile(r"^[a-zA-Z_$][a-zA-Z0-9_$]*(\.[a-zA-Z_$][a-zA-Z0-9_$]*)+$")
_PATH_LIKE = re.compile(r"^[a-zA-Z]:\\|^/[a-z]|^[a-z]+/[a-z]+/")
_URL = re.compile(r"^https?://")
_NUMBER = re.compile(r"^[\d.\-+eE]+$")
_HEX = re.compile(r"^(0x)?[0-9a-fA-F\-]{16,}$")
_SINGLE_WORD = re.compile(r"^[a-zA-Z]+$")
_FORMAT_ONLY = re.compile(r"^[%s\$n\d\.\-\+# ,:]+$")
_DESC_OR_SIG = re.compile(r"^\(.*\)[VZBSCIJFD\[]|^L[a-z]+/")
_ENUM_OR_CONST = re.compile(r"^[A-Z][A-Z0-9_]+$")
_RESOURCE_LOC = re.compile(r"^[a-z_]+:[a-z_./]+$")
_VERSION = re.compile(r"^\d+\.\d+")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_CLASS_NAME = re.compile(r"^[a-z]+(\.[a-zA-Z][a-zA-Z0-9]*){2,}$")

_CJK_RANGES = (
    (0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x30000, 0x3134F),
    (0x3000, 0x303F), (0xFF00, 0xFFEF),
)

_COMMON_FALSE_POSITIVES = frozenset({
    "true", "false", "null", "none", "undefined",
    "default", "error", "warning", "info", "debug",
    "enabled", "disabled", "on", "off",
    "name", "value", "type", "key", "id",
    "text", "title", "desc", "description", "label",
    "slot", "item", "block", "entity", "player",
    "server", "client", "world", "chunk",
    "nbt", "tag", "compound", "list",
    "gui", "screen", "button", "menu",
    "config", "option", "setting",
    "pos", "x", "y", "z", "width", "height",
})

_CODE_CHARS = set("(){}[];=<>|~^`\\")
_CONTROL_CHARS = set(chr(i) for i in range(32) if i not in (9, 10, 13))
_WORD_RE = re.compile(r'\b[a-zA-Z0-9_]+\b')


class ExtractedString:
    """从 Java 代码或 class 文件中提取的可翻译字符串。"""
    __slots__ = ("text", "file", "line", "context_line", "priority")

    def __init__(self, text: str, file: str, line: int, context_line: str, priority: str):
        self.text = text
        self.file = file
        self.line = line
        self.context_line = context_line
        self.priority = priority

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "file": self.file,
            "line": self.line,
            "context": self.context_line[:120],
            "priority": self.priority,
        }


def parse_constant_pool_strings(data: bytes) -> list[str]:
    """从 Java .class 文件的常量池中提取所有 UTF-8 字符串常量。"""
    if len(data) < 10 or data[:4] != b'\xca\xfe\xba\xbe':
        return []

    strings: list[str] = []
    try:
        cp_count = struct.unpack(">H", data[8:10])[0]
        idx = 10
        i = 1
        while i < cp_count and idx < len(data):
            tag = data[idx]
            idx += 1

            if tag == 1:  # CONSTANT_Utf8
                if idx + 2 > len(data):
                    break
                length = struct.unpack(">H", data[idx:idx + 2])[0]
                idx += 2
                if idx + length > len(data):
                    break
                try:
                    s = data[idx:idx + length].decode("utf-8", errors="replace")
                    strings.append(s)
                except Exception:
                    pass
                idx += length
            elif tag in (7, 8, 16, 19, 20):  # 2字节条目
                idx += 2
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18):  # 4字节条目
                idx += 4
            elif tag in (5, 6):  # 8字节条目（Long, Double）
                idx += 8
                i += 1
            elif tag == 15:  # MethodHandle
                idx += 3
            else:
                break
            i += 1
    except Exception:
        pass

    return strings


def has_cjk(text: str) -> bool:
    """检查文本是否包含 CJK 字符。"""
    for ch in text:
        cp = ord(ch)
        for start, end in _CJK_RANGES:
            if start <= cp <= end:
                return True
    return False


def is_already_translated(text: str) -> bool:
    """检查文本是否已经包含中文翻译。"""
    cjk_count = sum(1 for c in text if has_cjk(c))
    return cjk_count >= 2


def is_natural_language(text: str) -> bool:
    """判断文本是否为自然语言（非代码标识符）。"""
    if is_already_translated(text):
        return True
    if len(text) < 5:
        return False
    if " " not in text:
        return False
    for ch in text:
        if ch in _CODE_CHARS or ch in _CONTROL_CHARS:
            return False
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count < len(text) * 0.4:
        return False
    stripped = text.strip().lower()
    if stripped in _COMMON_FALSE_POSITIVES:
        return False
    for pat in (_ENUM_OR_CONST, _DESC_OR_SIG, _CLASS_NAME, _RESOURCE_LOC,
                _URL, _PATH_LIKE, _DOT_IDENT, _SNAKE_CASE, _CAMEL_CASE,
                _NUMBER, _HEX, _UUID):
        if pat.match(text.strip()):
            return False
    words = text.split()
    code_word_count = sum(
        1 for w in words
        if _CAMEL_CASE.match(w) or _SNAKE_CASE.match(w) or _DOT_IDENT.match(w)
    )
    if len(words) > 0 and code_word_count / len(words) > 0.6:
        return False
    return True


def extract_strings_from_class_bytes(class_data: bytes) -> list[str]:
    """从 .class 文件的字节数据中提取所有字符串常量。"""
    return parse_constant_pool_strings(class_data)


def patch_class_strings(class_data: bytes, translations: dict[str, str]) -> bytes:
    """替换 .class 文件常量池中的字符串（用于汉化）。"""
    if len(class_data) < 10 or class_data[:4] != b'\xca\xfe\xba\xbe':
        return class_data

    try:
        cp_count = struct.unpack(">H", class_data[8:10])[0]
    except Exception:
        return class_data

    header = class_data[:10]
    idx = 10
    i = 1
    has_patch = False
    new_cp = bytearray()

    try:
        while i < cp_count and idx < len(class_data):
            tag = class_data[idx]
            idx += 1

            if tag == 1:
                if idx + 2 > len(class_data):
                    return class_data
                length = struct.unpack(">H", class_data[idx:idx + 2])[0]
                idx += 2
                if idx + length > len(class_data):
                    return class_data
                raw_bytes = class_data[idx:idx + length]
                try:
                    original = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    original = None

                if original and original in translations:
                    new_bytes = translations[original].encode("utf-8")
                    new_cp.append(1)
                    new_cp.extend(struct.pack(">H", len(new_bytes)))
                    new_cp.extend(new_bytes)
                    has_patch = True
                else:
                    new_cp.append(1)
                    new_cp.extend(struct.pack(">H", length))
                    new_cp.extend(raw_bytes)
                idx += length
            elif tag in (7, 8, 16, 19, 20):
                new_cp.extend(class_data[idx - 1:idx + 2])
                idx += 2
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
                new_cp.extend(class_data[idx - 1:idx + 4])
                idx += 4
            elif tag in (5, 6):
                new_cp.extend(class_data[idx - 1:idx + 8])
                idx += 8
                i += 1
            elif tag == 15:
                new_cp.extend(class_data[idx - 1:idx + 3])
                idx += 3
            else:
                return class_data
            i += 1
    except Exception:
        return class_data

    if not has_patch:
        return class_data

    return bytes(header) + bytes(new_cp) + class_data[idx:]
