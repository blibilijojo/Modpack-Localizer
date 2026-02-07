import zipfile
import io
import json
import logging
import sqlite3
import re
from pathlib import Path
from utils import file_utils, config_manager
from collections import defaultdict
class DataAggregator:
    def __init__(self, mods_dir: Path, zip_paths: list[Path], community_dict_path: str):
        self.mods_dir = mods_dir
        self.zip_paths = zip_paths
        self.community_dict_path = Path(community_dict_path) if community_dict_path else None
        self.raw_english_files = {}
        self.LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
        self.JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
    def _extract_from_text(self, content: str, file_format: str, file_path_for_log: str) -> dict:
        data = {}
        if file_format == 'json':
            try:
                # 使用标准JSON解析库解析JSON文件
                data = json.loads(content)
            except json.JSONDecodeError:
                # 如果标准解析失败，回退到正则表达式解析
                logging.warning(f"标准JSON解析失败，回退到正则表达式解析: {file_path_for_log}")
                for match in self.JSON_KEY_VALUE_PATTERN.finditer(content):
                    key = match.group(1)
                    value = match.group(2)
                    data[key] = value
            return data
        elif file_format == 'lang':
            for match in self.LANG_KV_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2).strip()
                data[key] = value
        return data
    def run(self, progress_update_callback=None):
        logging.info("--- 阶段 1: 开始聚合所有语言数据 ---")
        user_dictionary = self._load_user_dictionary()
        community_dict_by_key, community_dict_by_origin = self._load_community_dictionary()
        master_english_dicts, internal_chinese_dicts, namespace_formats, namespace_to_jar = self._aggregate_from_mods(progress_update_callback)
        pack_chinese_dict = self._aggregate_from_zips(master_english_dicts)
        total_en = sum(len(d) for d in master_english_dicts.values())
        total_zh_internal = sum(len(d) for d in internal_chinese_dicts.values())
        logging.info(f"数据聚合完成。共发现 {len(master_english_dicts)} 个命名空间, {total_en} 条英文原文, {total_zh_internal} 条模组自带中文。")
        return user_dictionary, community_dict_by_key, community_dict_by_origin, master_english_dicts, internal_chinese_dicts, pack_chinese_dict, namespace_formats, namespace_to_jar, self.raw_english_files
    def _load_user_dictionary(self) -> dict:
        logging.info("  - 正在加载用户个人词典...")
        user_dict = config_manager.load_user_dict()
        logging.info(f"  - 用户词典加载成功: {len(user_dict.get('by_key', {}))} 条 [Key] 规则, {len(user_dict.get('by_origin_name', {}))} 条 [原文] 规则")
        return user_dict
    def _load_community_dictionary(self) -> tuple[dict, dict]:
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        if not self.community_dict_path or not self.community_dict_path.is_file():
            logging.info("  - 未提供社区词典文件或路径无效，跳过加载。")
            return {}, {}
        logging.info(f"  - 正在从社区词典加载: {self.community_dict_path.name}")
        try:
            with sqlite3.connect(f"file:{self.community_dict_path}?mode=ro", uri=True) as con:
                cur = con.cursor()
                cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
                for key, origin_name, trans_name, version in cur.fetchall():
                    if key: community_dict_by_key[key] = trans_name
                    if origin_name and trans_name:
                        # 仅导入单词数量为1到2个的条目
                        word_count = len(origin_name.split())
                        if 1 <= word_count <= 2:
                            community_dict_by_origin[origin_name].append({"trans": trans_name, "version": version or "0.0.0"})
        except sqlite3.Error as e:
            logging.error(f"  - 读取社区词典数据库时发生错误: {e}")
        logging.info(f"  - 社区词典加载成功: {len(community_dict_by_key)} 条 [Key] 规则, {len(community_dict_by_origin)} 条 [原文] 规则")
        return community_dict_by_key, dict(community_dict_by_origin)
    def _get_namespace_from_path(self, path_str: str) -> str:
        parts = Path(path_str).parts
        if 'assets' in parts:
            try:
                return parts[parts.index('assets') + 1]
            except (ValueError, IndexError):
                pass
        return 'minecraft'
    def _process_zip_file(self, zf, file_info, master_english_dicts, temp_dicts, source_zip_name: str):
        path_str_lower = file_info.filename.lower()
        is_english = 'lang/en_us' in path_str_lower
        is_chinese = 'lang/zh_cn' in path_str_lower
        if not (is_english or is_chinese):
            return None, None
        namespace = self._get_namespace_from_path(file_info.filename)
        file_format = 'lang' if path_str_lower.endswith('.lang') else 'json'
        log_path = f"{source_zip_name} -> {file_info.filename}"
        try:
            with zf.open(file_info) as f:
                content = f.read().decode('utf-8-sig')
        except Exception as e:
            logging.warning(f"读取zip内文件失败: {log_path} - {e}")
            return None, None
        extracted_data = self._extract_from_text(content, file_format, log_path)
        if is_english:
            if namespace not in self.raw_english_files:
                self.raw_english_files[namespace] = content
            master_english_dicts[namespace].update(extracted_data)
        elif is_chinese:
            temp_dicts[namespace].update(extracted_data)
        return namespace, file_format
    def _aggregate_from_mods(self, progress_update_callback=None):
        logging.info(f"  - 正在扫描Mods文件夹: {self.mods_dir}")
        master_english_dicts = defaultdict(dict)
        temp_internal_chinese_dicts = defaultdict(dict)
        namespace_formats = {}
        namespace_to_jar = {}
        if not self.mods_dir.exists():
            logging.warning(f"  - 配置的Mods目录不存在: {self.mods_dir}")
            jar_files = []
        else:
            jar_files = file_utils.find_files_in_dir(self.mods_dir, "*.jar")
        for i, jar_file in enumerate(jar_files):
            if progress_update_callback: progress_update_callback(i + 1, len(jar_files))
            try:
                with zipfile.ZipFile(jar_file, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang' not in file_info.filename: continue
                        namespace, file_format = self._process_zip_file(zf, file_info, master_english_dicts, temp_internal_chinese_dicts, jar_file.name)
                        if namespace and namespace not in namespace_to_jar:
                             namespace_to_jar[namespace] = jar_file.name
                        if namespace and file_format and namespace not in namespace_formats:
                             namespace_formats[namespace] = file_format
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取JAR文件: {jar_file.name} - 错误: {e}")
        internal_chinese_dicts = defaultdict(dict)
        for ns, zh_dict in temp_internal_chinese_dicts.items():
            en_dict = master_english_dicts.get(ns, {})
            for key, zh_value in zh_dict.items():
                if en_dict.get(key) != zh_value:
                    internal_chinese_dicts[ns][key] = zh_value
        logging.info(f"  - Mods扫描完成。共扫描 {len(jar_files)} 个JAR文件，发现 {len(master_english_dicts)} 个含语言文件的命名空间。")
        return master_english_dicts, internal_chinese_dicts, namespace_formats, namespace_to_jar
    def _aggregate_from_zips(self, master_english_dicts: dict):
        final_pack_chinese_dict = {}
        if not self.zip_paths: 
            logging.info("  - 未提供第三方汉化包，跳过处理。")
            return {}
        logging.info(f"  - 正在读取 {len(self.zip_paths)} 个第三方汉化包...")
        for zip_path in reversed(self.zip_paths):
            if not zip_path.exists():
                logging.warning(f"  - ZIP文件不存在，已跳过: {zip_path}")
                continue
            elif not zip_path.is_file():
                logging.warning(f"  - ZIP路径不是文件，已跳过: {zip_path}")
                continue
            elif not zipfile.is_zipfile(zip_path):
                logging.warning(f"  - 文件不是有效的ZIP格式，已跳过: {zip_path}")
                continue
            current_zip_chinese_dict = defaultdict(dict)
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang/zh_cn' not in file_info.filename.lower(): continue
                        self._process_zip_file(zf, file_info, {}, current_zip_chinese_dict, zip_path.name)
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取汉化包: {zip_path.name} - 错误: {e}")
            filtered_zip_dict = {}
            for ns, zh_dict in current_zip_chinese_dict.items():
                en_dict = master_english_dicts.get(ns, {})
                for key, zh_value in zh_dict.items():
                    if en_dict.get(key) != zh_value:
                        filtered_zip_dict[key] = zh_value
            final_pack_chinese_dict.update(filtered_zip_dict)
        logging.info(f"  - {len(self.zip_paths)} 个第三方汉化包处理完毕，共聚合 {len(final_pack_chinese_dict)} 条有效汉化。")
        return final_pack_chinese_dict