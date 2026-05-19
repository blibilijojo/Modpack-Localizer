"""
提取项目中所有 Python 文件的注释和文档字符串，生成结构化 txt 文件。
输出格式：
  FILE: <文件路径>
  LINE: <行号> | TYPE: <inline|docstring> | LANG: <en|zh|mixed>
  <注释内容（可能多行）>
  END
  ---
"""

import os
import re
import ast
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "comments_extracted.txt")

# 跳过的目录
SKIP_DIRS = {"__pycache__", ".git", ".idea", "venv", "env", "node_modules"}


def has_chinese(text: str) -> bool:
    return bool(re.search(r'[一-鿿]', text))


def has_english_letter(text: str) -> bool:
    return bool(re.search(r'[a-zA-Z]{2,}', text))


def classify_lang(text: str) -> str:
    """判断文本语言：en / zh / mixed"""
    zh = has_chinese(text)
    en = has_english_letter(text)
    if zh and en:
        return "mixed"
    if zh:
        return "zh"
    if en:
        return "en"
    return "other"


def extract_comments_from_file(filepath: str) -> list[dict]:
    """从单个 Python 文件中提取行内注释和文档字符串。"""
    results = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"  [SKIP] {filepath}: {e}", file=sys.stderr)
        return results

    lines = source.splitlines(keepends=True)
    rel_path = os.path.relpath(filepath, PROJECT_ROOT)

    # --- 1. 提取行内注释 (# ...) ---
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # 跳过 shebang 和 encoding 声明
        if stripped.startswith("#!") or stripped.startswith("# -*-") or stripped.startswith("# coding"):
            continue
        # 找到 # 但不在字符串中（简单启发式）
        # 使用正则：匹配行尾的 # 注释（排除 URL 中的 #）
        m = re.search(r'(?<!["\'])# (.+)', line)
        if m:
            comment_text = m.group(1).strip()
            if comment_text:
                results.append({
                    "file": rel_path,
                    "line": i,
                    "type": "inline",
                    "lang": classify_lang(comment_text),
                    "content": comment_text,
                })

    # --- 2. 提取文档字符串 (""" ... """) ---
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            # 获取 docstring
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                expr_node = node.body[0]
                docstring = expr_node.value.value

                docstring = docstring.strip()
                if not docstring:
                    continue

                # 判断是否为纯英文需要翻译
                lang = classify_lang(docstring)

                # 计算 docstring 在源码中的起始行
                start_line = expr_node.lineno
                # 估算结束行
                end_line = start_line + docstring.count('\n')

                results.append({
                    "file": rel_path,
                    "line": start_line,
                    "end_line": end_line,
                    "type": "docstring",
                    "lang": lang,
                    "content": docstring,
                })

    return results


def main():
    all_comments = []
    py_files = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if fname.endswith(".py"):
                py_files.append(os.path.join(root, fname))

    py_files.sort()
    print(f"扫描到 {len(py_files)} 个 Python 文件...")

    for fpath in py_files:
        comments = extract_comments_from_file(fpath)
        if comments:
            all_comments.extend(comments)

    # 按文件分组写入
    en_count = 0
    zh_count = 0
    mixed_count = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        current_file = None
        for c in all_comments:
            if c["file"] != current_file:
                if current_file is not None:
                    out.write("---\n")
                current_file = c["file"]
                out.write(f"FILE: {current_file}\n")

            out.write(f"LINE: {c['line']} | TYPE: {c['type']} | LANG: {c['lang']}\n")
            if c["type"] == "docstring":
                out.write(f"END_LINE: {c.get('end_line', c['line'])}\n")
            out.write(f"{c['content']}\n")
            out.write("END\n")

            if c["lang"] == "en":
                en_count += 1
            elif c["lang"] == "zh":
                zh_count += 1
            elif c["lang"] == "mixed":
                mixed_count += 1

        if current_file is not None:
            out.write("---\n")

    print(f"\n提取完成！输出文件: {OUTPUT_FILE}")
    print(f"  总注释数: {len(all_comments)}")
    print(f"  英文 (en): {en_count}")
    print(f"  中文 (zh): {zh_count}")
    print(f"  混合 (mixed): {mixed_count}")
    print(f"  其他 (other): {len(all_comments) - en_count - zh_count - mixed_count}")


if __name__ == "__main__":
    main()
