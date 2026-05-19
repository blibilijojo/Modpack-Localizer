"""
批量替换 Python 文件中的英文注释为中文翻译。
基于 extract_comments.py 提取的结果进行精确替换。
"""

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 翻译映射表：(文件相对路径, 行号, 原文, 译文)
# ============================================================
REPLACEMENTS = [
    # --- 行内注释 (inline) ---
    ("core/__init__.py", 1,
     "# Core module exports",
     "# 核心模块导出"),

    ("core/class_parser.py", 100,
     "# 2-byte entries",
     "# 2字节条目"),

    ("core/class_parser.py", 102,
     "# 4-byte entries",
     "# 4字节条目"),

    ("core/class_parser.py", 104,
     "# 8-byte entries (Long, Double)",
     "# 8字节条目（Long, Double）"),

    ("gui/quest_workflow_manager.py", 197,
     "# BQM usually has one file",
     "# BQM 通常只有一个文件"),

    ("utils/update_checker.py", 1,
     "# utils/update_checker.py",
     "# 工具模块/更新检查器"),

    # --- error_logger.py 中 f-string 生成的日志格式文本 ---
    ("utils/error_logger.py", 55,
     '# Timestamp: {datetime.now().isoformat()}',
     '# 时间戳: {datetime.now().isoformat()}'),

    ("utils/error_logger.py", 56,
     '# Error Type: {error_type}',
     '# 错误类型: {error_type}'),

    ("utils/error_logger.py", 82,
     'f"# General Error Log"',
     'f"# 通用错误日志"'),

    ("utils/error_logger.py", 83,
     'f"# Timestamp: {datetime.now().isoformat()}"',
     'f"# 时间戳: {datetime.now().isoformat()}"'),

    ("utils/error_logger.py", 84,
     'f"# Error Level: {error_level}"',
     'f"# 错误级别: {error_level}"'),

    ("utils/error_logger.py", 85,
     'f"# Error Title: {error_title}"',
     'f"# 错误标题: {error_title}"'),

    ("utils/error_logger.py", 87,
     'f"### ERROR MESSAGE ###"',
     'f"### 错误信息 ###"'),

    ("utils/error_logger.py", 97,
     'f"### EXCEPTION DETAILS ###"',
     'f"### 异常详情 ###"'),

    ("utils/error_logger.py", 102,
     'f"### TRACEBACK ###"',
     'f"### 调用栈 ###"'),

    ("utils/error_logger.py", 110,
     'f"### CONTEXT INFORMATION ###"',
     'f"### 上下文信息 ###"'),
]

# --- 文档字符串替换 ---
# 这些需要特殊处理，因为是多行的
DOCSTRING_REPLACEMENTS = [
    ("gui/workbench_ai_mixin.py", 14,
     '"""AI translation, terms, import/export functionality mixin for TranslationWorkbench."""',
     '"""TranslationWorkbench 的 AI 翻译、术语、导入导出功能混入类。"""'),

    ("gui/workbench_find_replace_mixin.py", 8,
     '"""Find/replace functionality mixin for TranslationWorkbench."""',
     '"""TranslationWorkbench 的查找/替换功能混入类。"""'),

    ("utils/hybrid_context_index.py", 1,
     '"""Hybrid-mode translation context: keyword overlap via inverted index."""',
     '"""混合模式翻译上下文：通过倒排索引实现关键词重叠匹配。"""'),

    ("utils/hybrid_context_index.py", 102,
     '"""Content-word -> translated English keys, for O(batch + hits) context lookup."""',
     '"""内容词 -> 已翻译的英文键，用于 O(batch + hits) 复杂度的上下文查找。"""'),
]


def apply_replacements():
    success_count = 0
    fail_count = 0

    all_replacements = REPLACEMENTS + DOCSTRING_REPLACEMENTS

    for rel_path, line_no, old_text, new_text in all_replacements:
        full_path = os.path.join(PROJECT_ROOT, rel_path)

        if not os.path.exists(full_path):
            print(f"  [FAIL] 文件不存在: {rel_path}")
            fail_count += 1
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"  [FAIL] 读取失败 {rel_path}: {e}")
            fail_count += 1
            continue

        # 行号从1开始，索引从0开始
        idx = line_no - 1
        if idx < 0 or idx >= len(lines):
            print(f"  [FAIL] 行号越界 {rel_path}:{line_no}")
            fail_count += 1
            continue

        current_line = lines[idx]

        if old_text in current_line:
            lines[idx] = current_line.replace(old_text, new_text)
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print(f"  [OK] {rel_path}:{line_no}")
                success_count += 1
            except Exception as e:
                print(f"  [FAIL] 写入失败 {rel_path}: {e}")
                fail_count += 1
        else:
            # 尝试在文件中全局搜索替换
            full_content = "".join(lines)
            if old_text in full_content:
                full_content = full_content.replace(old_text, new_text, 1)
                try:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(full_content)
                    print(f"  [OK] {rel_path} (全局匹配，非精确行号)")
                    success_count += 1
                except Exception as e:
                    print(f"  [FAIL] 写入失败 {rel_path}: {e}")
                    fail_count += 1
            else:
                print(f"  [SKIP] 未匹配: {rel_path}:{line_no}")
                print(f"         查找: {old_text[:60]}...")
                fail_count += 1

    print(f"\n替换完成: 成功 {success_count}, 失败/跳过 {fail_count}")


if __name__ == "__main__":
    apply_replacements()
