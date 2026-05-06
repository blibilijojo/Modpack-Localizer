from __future__ import annotations

import logging
import re
from pathlib import Path

_STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

_SKIP_PREFIXES = (
    "net.", "com.", "org.", "io.", "java.", "javax.", "jdk.",
    "minecraft.", "forge.", "neoforge.", "fabric.", "mixin.",
)

_SKIP_PATTERNS = [
    re.compile(r"^[a-z]+/[a-z]"),
    re.compile(r"^[A-Z][A-Z_0-9]{3,}$"),
    re.compile(r"^https?://"),
    re.compile(r"^/"),
    re.compile(r"^\d"),
    re.compile(r"^[a-f0-9\-]{20,}$", re.IGNORECASE),
    re.compile(r"^#[0-9a-fA-F]{6,8}$"),
    re.compile(r"^\{.*\}$"),
    re.compile(r"^%[sdn]|^\$\{|^\[\$"),
    re.compile(r"^[\w.]+:[\w./]+$"),
]

_CONTEXT_KEYWORDS = [
    "sendMessage", "sendStatusMessage", "displayClientMessage",
    "displayText", "addTooltip", "tooltip", "append",
    "translat", "I18n", "Component", "literal", "translatable",
    "ChatComponent", "GuiComponent", "drawString", "drawCenteredString",
    "title", "subtitle", "description", "displayName",
    "displayArmorTitle", "showTitle", "setSubtitle",
    "actionBar", "displayActionBar",
    "addMessage", "showMessage", "setStatusMessage",
    "Screen", "Widget", "Button", "Label",
    "Narrator", "narrate",
    "LOGGER", "log", "info", "warn", "error", "debug",
]

_LOGGER_PATTERN = re.compile(
    r"(?:LOGGER|logger|LOG|log|LOGGER_FACTORY)\s*\.\s*(?:info|warn|error|debug|trace|fatal)\s*\(",
    re.IGNORECASE,
)


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


def _is_translatable(text: str) -> bool:
    if len(text) < 3:
        return False
    if not any(c.isalpha() for c in text):
        return False
    if any(text.startswith(p) for p in _SKIP_PREFIXES):
        return False
    for pat in _SKIP_PATTERNS:
        if pat.match(text):
            return False
    if re.match(r"^[a-z_][a-z0-9_.]*$", text):
        return False
    if re.match(r"^\w+\.\w+\.\w+", text):
        return False
    return True


def _detect_priority(context_line: str) -> str:
    stripped = context_line.strip()
    if _LOGGER_PATTERN.search(stripped):
        return "low"
    for kw in _CONTEXT_KEYWORDS:
        if kw.lower() in stripped.lower():
            return "high"
    return "medium"


def extract_strings_from_java(java_dir: Path) -> list[ExtractedString]:
    results: list[ExtractedString] = []
    seen: set[str] = set()

    java_files = list(java_dir.rglob("*.java"))
    logging.info(f"正在从 {len(java_files)} 个 Java 文件中提取字符串...")

    for java_file in java_files:
        try:
            content = java_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        rel_path = str(java_file.relative_to(java_dir))

        for line_idx, line in enumerate(lines, 1):
            for match in _STRING_LITERAL.finditer(line):
                text = match.group(1)
                if not _is_translatable(text):
                    continue
                if text in seen:
                    continue
                seen.add(text)

                priority = _detect_priority(line)
                results.append(ExtractedString(
                    text=text,
                    file=rel_path,
                    line=line_idx,
                    context_line=line.strip(),
                    priority=priority,
                ))

    high = sum(1 for r in results if r.priority == "high")
    med = sum(1 for r in results if r.priority == "medium")
    low = sum(1 for r in results if r.priority == "low")
    logging.info(f"字符串提取完成: {len(results)} 条 (高优先={high}, 中={med}, 低={low})")

    return results


def extract_strings_from_class_constants(class_dir: Path) -> list[ExtractedString]:
    """从 .class 文件的常量池中直接提取 UTF-8 字符串常量（无需反编译）"""
    import struct

    results: list[ExtractedString] = []
    seen: set[str] = set()

    class_files = list(class_dir.rglob("*.class"))
    logging.info(f"正在从 {len(class_files)} 个 .class 文件常量池中提取字符串...")

    for cls_file in class_files:
        try:
            data = cls_file.read_bytes()
        except Exception:
            continue

        strings = _parse_constant_pool_strings(data)
        rel_path = str(cls_file.relative_to(class_dir))

        for s in strings:
            if not _is_translatable(s):
                continue
            if s in seen:
                continue
            seen.add(s)
            results.append(ExtractedString(
                text=s,
                file=rel_path,
                line=0,
                context_line="[class constant pool]",
                priority="medium",
            ))

    logging.info(f"常量池提取完成: {len(results)} 条唯一字符串")
    return results


def _parse_constant_pool_strings(data: bytes) -> list[str]:
    import struct

    if len(data) < 10 or data[:4] != b'\xca\xfe\xba\xbe':
        return []

    strings: list[str] = []
    try:
        idx = 8
        cp_count = struct.unpack(">H", data[8:10])[0]
        idx = 10

        i = 1
        while i < cp_count and idx < len(data):
            tag = data[idx]
            idx += 1

            if tag == 1:
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
