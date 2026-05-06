"""Java .class 文件反编译辅助工具，用于提取和替换常量池中的字符串。"""

from __future__ import annotations

import logging
from pathlib import Path

from core.class_parser import (
    ExtractedString,
    extract_strings_from_class_bytes,
    is_natural_language,
    patch_class_strings,
)


def extract_translatable_from_jar(jar_path: Path) -> list[dict]:
    """从 JAR 文件中提取可翻译的自然语言字符串。"""
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
                if not is_natural_language(s):
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


__all__ = [
    'ExtractedString',
    'extract_strings_from_class_bytes',
    'extract_translatable_from_jar',
    'patch_class_strings',
]
