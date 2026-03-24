import json
import sys
import tempfile
from pathlib import Path
import logging

def is_frozen() -> bool:
    """
    检测当前是否在打包后的 exe 环境中运行（支持 PyInstaller 和 Nuitka）
    
    使用多层检测逻辑：
    1. 检查 sys.frozen 或 sys.nuitka 属性
    2. 检查是否有 _MEIPASS 或 _NUITKA_SYS 属性（打包后的临时目录）
    3. 检查可执行文件是否在系统临时目录中（Nuitka 的打包特征）
    
    Returns:
        如果是打包后的 exe 环境返回 True，否则返回 False
    """
    # 方法 1: 检查 sys.frozen 或 sys.nuitka 属性
    frozen = getattr(sys, 'frozen', False) or getattr(sys, 'nuitka', False)
    if frozen:
        return True
    
    # 方法 2: 检查是否在 PyInstaller/Nuitka 的临时目录中运行
    if hasattr(sys, '_MEIPASS') or hasattr(sys, '_NUITKA_SYS'):
        return True
    
    # 方法 3: 检查可执行文件是否在临时目录中（Nuitka 会在临时目录运行）
    exe_path = Path(sys.executable) if hasattr(sys, 'executable') else None
    if exe_path:
        temp_dir = Path(tempfile.gettempdir())
        try:
            exe_path.resolve().relative_to(temp_dir)
            return True  # 在临时目录中运行，说明是打包的 exe
        except ValueError:
            pass
    
    return False

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