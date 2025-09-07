import zipfile
import io
import json
import logging
import sqlite3
import re
from pathlib import Path
from utils import file_utils, config_manager
from collections import defaultdict

def _remove_comments_from_json(json_str: str) -> str:
    json_str = re.sub(r"//.*$", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
    return json_str

class DataAggregator:
    def __init__(self, mods_dir: Path, zip_paths: list[Path], community_dict_path: str):
        self.mods_dir = mods_dir
        self.zip_paths = zip_paths
        self.community_dict_path = Path(community_dict_path) if community_dict_path else None

    def _is_actually_translated(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        if re.search(r'[\u4e00-\u9fa5]', text):
            return True
        if re.search(r'[a-zA-Z]', text):
            return False
        return True

    def run(self, progress_update_callback=None):
        logging.info("开始聚合数据...")
        user_dictionary = self._load_user_dictionary()
        community_dict_by_key, community_dict_by_origin = self._load_community_dictionary()
        master_english_dicts, internal_chinese_dicts, namespace_formats, namespace_to_jar = self._aggregate_from_mods(progress_update_callback)
        pack_chinese_dict = self._aggregate_from_zips()
        
        total_en = sum(len(d) for d in master_english_dicts.values())
        total_zh = sum(len(d) for d in internal_chinese_dicts.values())
        logging.info(f"数据聚合完成。共 {len(master_english_dicts)} 个命名空间, 英文条目: {total_en}, 中文条目: {total_zh}")
        
        return user_dictionary, community_dict_by_key, community_dict_by_origin, master_english_dicts, internal_chinese_dicts, pack_chinese_dict, namespace_formats, namespace_to_jar

    def _load_user_dictionary(self) -> dict:
        logging.info("  - 正在加载用户个人词典...")
        user_dict = config_manager.load_user_dict()
        key_count = len(user_dict.get('by_key', {}))
        origin_count = len(user_dict.get('by_origin_name', {}))
        if key_count > 0 or origin_count > 0:
            logging.info(f"  - 成功从个人词典加载 {key_count} 条Key匹配和 {origin_count} 条原文匹配。")
        return user_dict

    def _load_community_dictionary(self) -> tuple[dict, dict]:
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        
        if not self.community_dict_path or not self.community_dict_path.is_file():
            logging.info("  - 未提供社区词典文件，跳过加载。")
            return community_dict_by_key, dict(community_dict_by_origin)
            
        logging.info(f"  - 正在从社区词典加载: {self.community_dict_path.name}")
        try:
            con = sqlite3.connect(f"file:{self.community_dict_path}?mode=ro", uri=True)
            cur = con.cursor()
            cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
            rows = cur.fetchall()
            
            for row in rows:
                key, origin_name, trans_name, version = row
                if key:
                    community_dict_by_key[key] = trans_name
                if origin_name and trans_name:
                    community_dict_by_origin[origin_name].append(
                        {"trans": trans_name, "version": version or "0.0.0"}
                    )
            
            total_entries = len(community_dict_by_key) + sum(len(v) for v in community_dict_by_origin.values())
            logging.info(f"  - 成功从社区词典加载 {total_entries} 条数据。")
        except sqlite3.Error as e:
            logging.error(f"  - 读取社区词典数据库时发生错误: {e}")
        finally:
            if 'con' in locals() and con:
                con.close()
        
        return community_dict_by_key, dict(community_dict_by_origin)

    def _get_namespace_from_path(self, path_str: str) -> str:
        try:
            parts = Path(path_str).parts
            if 'assets' in parts:
                assets_index = parts.index('assets')
                if len(parts) > assets_index + 1:
                    return parts[assets_index + 1]
        except Exception: pass
        return 'minecraft'

    def _aggregate_from_mods(self, progress_update_callback=None):
        logging.info(f"  - 正在扫描Mods文件夹: {self.mods_dir}")
        master_english_dicts = defaultdict(dict)
        internal_chinese_dicts = defaultdict(dict)
        namespace_formats = {}
        namespace_to_jar = {}
        jar_files = file_utils.find_files_in_dir(self.mods_dir, "*.jar")
        total_jars = len(jar_files)
        
        for i, jar_file in enumerate(jar_files):
            if progress_update_callback: progress_update_callback(i + 1, total_jars)
            try:
                with zipfile.ZipFile(jar_file, 'r') as zf:
                    file_list = sorted(zf.infolist(), key=lambda f: f.filename.lower().endswith('.lang'))
                    for file_info in file_list:
                        if file_info.is_dir(): continue
                        path_str_lower = file_info.filename.lower()
                        
                        if 'lang/en_us.json' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace not in namespace_to_jar: namespace_to_jar[namespace] = jar_file.name
                            if namespace in namespace_formats: continue
                            namespace_formats[namespace] = 'json'
                            with zf.open(file_info) as f:
                                try:
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    data = json.loads(_remove_comments_from_json(content), strict=False)
                                    filtered_data = {key: value for key, value in data.items() if value and value.strip()}
                                    master_english_dicts[namespace].update(filtered_data)
                                except Exception as e: logging.warning(f"解析 en_us.json 失败: {file_info.filename} - {e}")
                        
                        elif 'lang/en_us.lang' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace not in namespace_to_jar: namespace_to_jar[namespace] = jar_file.name
                            if namespace in namespace_formats: continue
                            namespace_formats[namespace] = 'lang'
                            with zf.open(file_info) as f:
                                try:
                                    lines = [line.decode('utf-8-sig').strip() for line in f.readlines()]
                                    for line in lines:
                                        if line and not line.startswith('#'):
                                            parts = line.split('=', 1)
                                            if len(parts) == 2 and parts[1] and parts[1].strip():
                                                master_english_dicts[namespace][parts[0]] = parts[1]
                                except Exception as e: logging.warning(f"解析 en_us.lang 失败: {file_info.filename} - {e}")

                        elif 'lang/zh_cn.json' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            with zf.open(file_info) as f:
                                try:
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    data = json.loads(_remove_comments_from_json(content), strict=False)
                                    for key, value in data.items():
                                        if self._is_actually_translated(value):
                                            internal_chinese_dicts[namespace][key] = value
                                except Exception as e: logging.warning(f"解析 zh_cn.json 失败: {file_info.filename} - {e}")
                        
                        elif 'lang/zh_cn.lang' in path_str_lower:
                            namespace = self._get_namespace_from_path(file_info.filename)
                            if namespace in namespace_formats and namespace_formats[namespace] == 'json': continue
                            with zf.open(file_info) as f:
                                try:
                                    lines = [line.decode('utf-8-sig').strip() for line in f.readlines()]
                                    for line in lines:
                                        if line and not line.startswith('#'):
                                            parts = line.split('=', 1)
                                            if len(parts) == 2 and self._is_actually_translated(parts[1]):
                                                internal_chinese_dicts[namespace][parts[0]] = parts[1]
                                except Exception as e: logging.warning(f"解析 zh_cn.lang 失败: {file_info.filename} - {e}")
                                    
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取JAR文件: {jar_file.name} - 错误: {e}")
        return master_english_dicts, internal_chinese_dicts, namespace_formats, namespace_to_jar

    def _aggregate_from_zips(self):
        final_pack_chinese_dict = {}
        if not self.zip_paths:
            return final_pack_chinese_dict
            
        logging.info(f"  - 正在读取第三方汉化包...")
        for zip_path in reversed(self.zip_paths):
            logging.debug(f"  - 处理汉化包 (优先级高): {zip_path.name}")
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
                                    content = io.TextIOWrapper(f, encoding='utf-8-sig').read()
                                    data = json.loads(_remove_comments_from_json(content), strict=False)
                                    for key, value in data.items():
                                        if self._is_actually_translated(value):
                                            current_zip_dict[key] = value
                                except Exception as e: logging.warning(f"解析ZIP中的 {file_info.filename} 失败: {e}")
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取第三方汉化包: {zip_path.name} - 错误: {e}")
            final_pack_chinese_dict.update(current_zip_dict)
        return final_pack_chinese_dict