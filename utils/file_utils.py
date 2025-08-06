# Modpack_Localizer/utils/file_utils.py
import json
from pathlib import Path
import logging

def load_json(file_path: Path) -> dict | None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"文件未找到，跳过: {file_path}")
        return None
    except json.JSONDecodeError:
        logging.error(f"JSON解析错误，文件可能已损坏，跳过: {file_path}")
        return None
    except Exception as e:
        logging.error(f"加载JSON时发生未知错误 ({file_path}): {e}")
        return None

def find_files_in_dir(directory: Path, pattern: str) -> list[Path]:
    if not directory.is_dir():
        logging.warning(f"目录不存在: {directory}")
        return []
    return list(directory.rglob(pattern))

def escape_json_string(text: str) -> str:
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')