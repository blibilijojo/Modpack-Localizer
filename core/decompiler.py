from __future__ import annotations

import logging
import re
import struct
from pathlib import Path


_CODE_CHARS = set("(){}[];=<>|~^`\\")
_CONTROL_CHARS = set(chr(i) for i in range(32) if i not in (9, 10, 13))

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
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x30000, 0x3134F),
    (0x3000, 0x303F),
    (0xFF00, 0xFFEF),
)


def _has_cjk(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        for start, end in _CJK_RANGES:
            if start <= cp <= end:
                return True
    return False


def _is_already_translated(text: str) -> bool:
    cjk_count = sum(1 for c in text if _has_cjk(c))
    return cjk_count >= 2


_COMMON_FALSE_POSITIVES = {
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
}


def _is_natural_language(text: str) -> bool:
    if _is_already_translated(text):
        return True

    if len(text) < 5:
        return False

    has_space = " " in text
    if not has_space:
        return False

    for ch in text:
        if ch in _CODE_CHARS:
            return False
        if ch in _CONTROL_CHARS:
            return False

    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count < len(text) * 0.4:
        return False

    stripped = text.strip().lower()
    if stripped in _COMMON_FALSE_POSITIVES:
        return False

    if _ENUM_OR_CONST.match(text.strip()):
        return False

    if _DESC_OR_SIG.match(text.strip()):
        return False

    if _CLASS_NAME.match(text.strip()):
        return False

    if _RESOURCE_LOC.match(text.strip()):
        return False

    if _URL.match(text.strip()):
        return False

    if _PATH_LIKE.match(text.strip()):
        return False

    if _DOT_IDENT.match(text.strip()):
        return False

    if _SNAKE_CASE.match(text.strip()):
        return False

    if _CAMEL_CASE.match(text.strip()):
        return False

    if _NUMBER.match(text.strip()):
        return False

    if _HEX.match(text.strip()):
        return False

    if _UUID.match(text.strip()):
        return False

    words = text.split()
    code_word_count = sum(
        1 for w in words
        if _CAMEL_CASE.match(w) or _SNAKE_CASE.match(w) or _DOT_IDENT.match(w)
    )
    if len(words) > 0 and code_word_count / len(words) > 0.6:
        return False

    return True


class ExtractedString:
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


def extract_strings_from_class_bytes(class_data: bytes) -> list[str]:
    if len(class_data) < 10 or class_data[:4] != b'\xca\xfe\xba\xbe':
        return []

    strings: list[str] = []
    try:
        cp_count = struct.unpack(">H", class_data[8:10])[0]
        idx = 10
        i = 1
        while i < cp_count and idx < len(class_data):
            tag = class_data[idx]
            idx += 1

            if tag == 1:
                if idx + 2 > len(class_data):
                    break
                length = struct.unpack(">H", class_data[idx:idx + 2])[0]
                idx += 2
                if idx + length > len(class_data):
                    break
                try:
                    s = class_data[idx:idx + length].decode("utf-8", errors="replace")
                    strings.append(s)
                except Exception:
                    pass
                idx += length
            elif tag in (7, 8, 16, 19, 20):
                idx += 2
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
                idx += 4
            elif tag in (5, 6):
                idx += 8
                i += 1
            elif tag == 15:
                idx += 3
            else:
                break
            i += 1
    except Exception:
        pass

    return strings


def extract_translatable_from_jar(jar_path: Path) -> list[dict]:
    import zipfile

    results: list[dict] = []
    seen: set[str] = set()

    with zipfile.ZipFile(jar_path, "r") as zf:
        for entry in zf.infolist():
            if not entry.filename.endswith(".class"):
                continue
            try:
                class_data = zf.read(entry)
            except Exception:
                continue

            raw_strings = extract_strings_from_class_bytes(class_data)
            for s in raw_strings:
                if not _is_natural_language(s):
                    continue
                if s in seen:
                    continue
                seen.add(s)
                results.append({
                    "text": s,
                    "file": entry.filename,
                    "line": 0,
                    "context": "[class constant pool]",
                    "priority": "medium",
                })

    logging.info(f"常量池提取完成: {len(results)} 条可翻译自然语言文本")
    return results


def patch_class_strings(class_data: bytes, translations: dict[str, str]) -> bytes:
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
