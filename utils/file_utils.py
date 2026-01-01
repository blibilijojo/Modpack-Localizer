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
    # 创建转义字符映射表，保留原始转义序列
    escape_map = {
        '\\': '\\\\',
        '"': '\\"',
        '\b': '\\b',
        '\f': '\\f',
        '\n': '\\n',
        '\r': '\\r',
        '\t': '\\t'
    }
    
    def escape_char(c):
        return escape_map.get(c, c)
    
    return ''.join(escape_char(c) for c in text)

def dump_json(file_path: Path, data: dict, indent: int = 4) -> bool:
    """
    将数据以JSON格式写入文件
    
    Args:
        file_path: 要写入的文件路径
        data: 要写入的数据
        indent: JSON缩进空格数
        
    Returns:
        是否成功写入
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as e:
        logging.error(f"写入JSON到文件时发生错误 ({file_path}): {e}")
        return False