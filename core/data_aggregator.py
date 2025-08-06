# core/data_aggregator.py

import zipfile
import io
import json
import logging
import sqlite3
import re  # --- ADDED: Import regular expressions for comment removal ---
from pathlib import Path
from utils import file_utils
from collections import defaultdict

# --- ADDED: Helper function to remove comments from a JSON string before parsing ---
def _remove_comments_from_json(json_str: str) -> str:
    """Removes C-style comments (// and /* */) from a JSON string."""
    # Remove // comments
    json_str = re.sub(r"//.*$", "", json_str, flags=re.MULTILINE)
    # Remove /* */ comments
    json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
    return json_str


class DataAggregator:
    def __init__(self, mods_dir: Path, zip_paths: list[Path], community_dict_path: str):
        self.mods_dir = mods_dir
        self.zip_paths = zip_paths
        self.community_dict_path = Path(community_dict_path) if community_dict_path else None

    def run(self, progress_update_callback=None):
        logging.info("开始聚合数据...")
        community_dict = self._load_community_dictionary()
        master_english_dicts, internal_chinese_dicts, namespace_formats = self._aggregate_from_mods(progress_update_callback)
        pack_chinese_dict = self._aggregate_from_zips()
        return community_dict, master_english_dicts, internal_chinese_dicts, pack_chinese_dict, namespace_formats

    def _load_community_dictionary(self) -> dict:
        community_dict = {}
        if not self.community_dict_path or not self.community_dict_path.is_file():
            logging.info("未提供或未找到社区词典文件，跳过加载。")
            return community_dict
        logging.info(f"正在从社区词典加载: {self.community_dict_path.name}")
        try:
            con = sqlite3.connect(self.community_dict_path)
            cur = con.cursor()
            cur.execute("SELECT key, trans_name FROM dict")
            rows = cur.fetchall()
            community_dict = {row[0]: row[1] for row in rows}
            logging.info(f"成功从社区词典加载 {len(community_dict)} 条补充翻译。")
        except sqlite3.Error as e:
            logging.error(f"读取社区词典数据库时发生错误: {e}")
        finally:
            if 'con' in locals() and con:
                con.close()
        return community_dict

    def _get_namespace_from_path(self, path_str: str) -> str:
        try:
            parts = Path(path_str).parts
            if 'assets' in parts:
                assets_index = parts.index('assets')
                if len(parts) > assets_index + 1:
                    return parts[assets_index + 1]
        except Exception:
            pass
        return 'minecraft'

    def _aggregate_from_mods(self, progress_update_callback=None):
        logging.info(f"正在扫描Mods文件夹: {self.mods_dir}")
        master_english_dicts = defaultdict(dict)
        internal_chinese_dicts = defaultdict(dict)
        namespace_formats = {}
        jar_files = file_utils.find_files_in_dir(self.mods_dir, "*.jar")
        total_jars = len(jar_files)
        
        for i, jar_file in enumerate(jar_files):
            if progress_update_callback:
                progress_update_callback(i + 1, total_jars)
            try:
                with zipfile.ZipFile(jar_file, 'r') as zf:
                    file_list = sorted(zf.infolist(), key=lambda f: f.filename.lower().endswith('.lang'))
                    for file_info in file_list:
                        if file_info.is_dir(): continue
                        path_str_lower = file_info.filename.lower()
                        
                        # --- MODIFIED: Handle commented en_us.json ---
                        if 'lang/en_us.json' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace in namespace_formats: continue
                            logging.info(f"在 {jar_file.name} 中检测到 '{namespace}' 的 .json 语言文件。")
                            namespace_formats[namespace] = 'json'
                            with zf.open(file_info) as f:
                                try:
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    clean_content = _remove_comments_from_json(content)
                                    data = json.loads(clean_content)
                                    master_english_dicts[namespace].update(data)
                                except Exception as e:
                                    logging.warning(f"解析 en_us.json 失败: {file_info.filename} - {e}")
                        
                        elif 'lang/en_us.lang' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace in namespace_formats: continue
                            logging.info(f"在 {jar_file.name} 中检测到 '{namespace}' 的 .lang 语言文件。")
                            namespace_formats[namespace] = 'lang'
                            with zf.open(file_info) as f:
                                try:
                                    lines = [line.decode('utf-8-sig').strip() for line in f.readlines()]
                                    for line in lines:
                                        if line and not line.startswith('#'):
                                            parts = line.split('=', 1)
                                            if len(parts) == 2:
                                                master_english_dicts[namespace][parts[0]] = parts[1]
                                except Exception as e:
                                    logging.warning(f"解析 en_us.lang 失败: {file_info.filename} - {e}")

                        # --- MODIFIED: Handle commented zh_cn.json ---
                        elif 'lang/zh_cn.json' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            with zf.open(file_info) as f:
                                try:
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    clean_content = _remove_comments_from_json(content)
                                    data = json.loads(clean_content)
                                    internal_chinese_dicts[namespace].update(data)
                                except Exception as e:
                                    logging.warning(f"解析 zh_cn.json 失败: {file_info.filename} - {e}")
                        
                        elif 'lang/zh_cn.lang' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace in namespace_formats and namespace_formats[namespace] == 'json': continue
                            with zf.open(file_info) as f:
                                try:
                                    lines = [line.decode('utf-8-sig').strip() for line in f.readlines()]
                                    for line in lines:
                                        if line and not line.startswith('#'):
                                            parts = line.split('=', 1)
                                            if len(parts) == 2:
                                                internal_chinese_dicts[namespace][parts[0]] = parts[1]
                                except Exception as e:
                                    logging.warning(f"解析 zh_cn.lang 失败: {file_info.filename} - {e}")
                                    
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取JAR文件: {jar_file.name} - 错误: {e}")
        total_en = sum(len(d) for d in master_english_dicts.values())
        total_zh = sum(len(d) for d in internal_chinese_dicts.values())
        logging.info(f"从Mods聚合完成。共 {len(master_english_dicts)} 个命名空间, 英文条目: {total_en}, 中文条目: {total_zh}")
        return master_english_dicts, internal_chinese_dicts, namespace_formats

    def _aggregate_from_zips(self):
        final_pack_chinese_dict = {}
        for zip_path in reversed(self.zip_paths):
            logging.info(f"正在读取第三方汉化包 (优先级高): {zip_path.name}")
            if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
                logging.warning(f"第三方汉化包路径无效或文件不存在，已跳过: {zip_path}")
                continue
            current_zip_dict = {}
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir(): continue
                        file_path = Path(file_info.filename)
                        if "assets" in file_path.parts and file_path.name == 'zh_cn.json':
                            with zf.open(file_info) as f:
                                try:
                                    # --- MODIFIED: Also handle commented JSON in zip files ---
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    clean_content = _remove_comments_from_json(content)
                                    current_zip_dict.update(json.loads(clean_content))
                                except Exception as e:
                                    logging.warning(f"解析ZIP中的 {file_info.filename} 失败: {e}")
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取第三方汉化包: {zip_path.name} - 错误: {e}")
            final_pack_chinese_dict.update(current_zip_dict)
            logging.info(f"从 {zip_path.name} 加载了 {len(current_zip_dict)} 条汉化。")
        logging.info(f"从所有第三方汉化包中聚合完成，共 {len(final_pack_chinese_dict)} 条独立汉化。")
        return final_pack_chinese_dict