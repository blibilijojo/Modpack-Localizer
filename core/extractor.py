import zipfile
import json
import logging
import sqlite3
import re
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
from utils import file_utils, config_manager

from .models import (
    LanguageEntry, NamespaceInfo, ExtractionResult,
    DictionaryEntry
)

class Extractor:
    """语言数据提取器"""
    
    def __init__(self):
        # 保持原有正则表达式规则不变
        self.LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
        self.JSON_KEY_VALUE_PATTERN = re.compile(r'"([^"]+)":\s*"((?:\\.|[^\\"])*)"', re.DOTALL)
    
    def _unescape_unicode(self, text: str) -> str:
        r"""
        自定义unescape函数，只处理Unicode转义序列（\uXXXX），保留其他转义字符（如\n、\t等）
        """
        import re
        
        def replace_unicode(match):
            """替换单个Unicode转义序列"""
            hex_str = match.group(1)
            try:
                # 将十六进制字符串转换为整数，再转换为字符
                return chr(int(hex_str, 16))
            except ValueError:
                # 如果转换失败，返回原始匹配字符串
                return match.group(0)
        
        # 使用正则表达式匹配所有\uXXXX格式的Unicode转义序列
        return re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, text)
    
    def _extract_from_text(self, content: str, file_format: str, file_path_for_log: str) -> Dict[str, str]:
        """
        从文本内容中提取语言数据，保持原始格式
        """
        data = {}
        if file_format == 'json':
            # 直接使用正则表达式解析，保留原始转义字符
            for match in self.JSON_KEY_VALUE_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2)
                # 处理Unicode转义序列，但保留其他转义字符
                value = self._unescape_unicode(value)
                data[key] = value
        elif file_format == 'lang':
            for match in self.LANG_KV_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2).strip()
                # 处理Unicode转义序列，但保留其他转义字符
                value = self._unescape_unicode(value)
                data[key] = value
        return data
    
    def _get_namespace_from_path(self, path_str: str) -> str:
        """从文件路径中获取命名空间"""
        parts = Path(path_str).parts
        if 'assets' in parts:
            try:
                return parts[parts.index('assets') + 1]
            except (ValueError, IndexError):
                pass
        return 'minecraft'
    
    def _process_zip_file(self, zf, file_info, master_english, temp_dicts, source_zip_name: str) -> Optional[tuple]:
        """处理ZIP文件中的语言文件"""
        path_str_lower = file_info.filename.lower()
        is_english = 'lang/en_us' in path_str_lower
        is_chinese = 'lang/zh_cn' in path_str_lower
        
        if not (is_english or is_chinese):
            return None, None, None, None, None, None
        
        namespace = self._get_namespace_from_path(file_info.filename)
        file_format = 'lang' if path_str_lower.endswith('.lang') else 'json'
        log_path = f"{source_zip_name} -> {file_info.filename}"
        
        try:
            with zf.open(file_info) as f:
                content = f.read().decode('utf-8-sig')
        except Exception as e:
            logging.warning(f"读取zip内文件失败: {log_path} - {e}")
            return None, None, None, None, None, None
        
        extracted_data = self._extract_from_text(content, file_format, log_path)
        
        return namespace, file_format, content, extracted_data, is_english, is_chinese
    
    def _load_dictionaries(self, community_dict_path: str) -> tuple[Dict, Dict, Dict]:
        """加载各种词典"""
        # 加载用户词典
        user_dict = config_manager.load_user_dict()
        user_dict_by_key = user_dict.get('by_key', {})
        user_dict_by_origin = user_dict.get('by_origin_name', {})
        
        # 加载社区词典
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        
        if community_dict_path and Path(community_dict_path).is_file():
            try:
                with sqlite3.connect(f"file:{community_dict_path}?mode=ro", uri=True) as con:
                    cur = con.cursor()
                    cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
                    for key, origin_name, trans_name, version in cur.fetchall():
                        if key:
                            community_dict_by_key[key] = trans_name
                        if origin_name and trans_name:
                            community_dict_by_origin[origin_name].append({"trans": trans_name, "version": version or "0.0.0"})
            except sqlite3.Error as e:
                logging.error(f"读取社区词典数据库时发生错误: {e}")
        
        return user_dict_by_key, user_dict_by_origin, community_dict_by_key
    
    def extract_from_mods(self, mods_dir: Path, progress_update_callback=None) -> ExtractionResult:
        """从Mods文件夹中提取语言数据"""
        logging.info(f"  - 正在扫描Mods文件夹: {mods_dir}")
        
        result = ExtractionResult()
        master_english = result.master_english
        internal_chinese = result.internal_chinese
        namespace_info = result.namespace_info
        raw_english_files = result.raw_english_files
        
        jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar") if mods_dir.exists() else []
        
        for i, jar_file in enumerate(jar_files):
            if progress_update_callback:
                progress_update_callback(i + 1, len(jar_files))
            
            try:
                with zipfile.ZipFile(jar_file, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang' not in file_info.filename:
                            continue
                        
                        result_tuple = self._process_zip_file(zf, file_info, master_english, internal_chinese, jar_file.name)
                        if result_tuple[0] is None:
                            continue
                        
                        namespace, file_format, content, extracted_data, is_english, is_chinese = result_tuple
                        
                        # 初始化命名空间信息
                        if namespace not in namespace_info:
                            namespace_info[namespace] = NamespaceInfo(
                                name=namespace,
                                jar_name=jar_file.name,
                                file_format=file_format
                            )
                        
                        # 更新命名空间的文件格式（优先使用JSON）
                        if file_format == 'json':
                            namespace_info[namespace].file_format = file_format
                        
                        # 处理英文文件
                        if is_english:
                            raw_english_files[namespace] = content
                            namespace_info[namespace].raw_content = content
                            
                            for key, value in extracted_data.items():
                                entry = LanguageEntry(
                                    key=key,
                                    en=value,
                                    namespace=namespace
                                )
                                master_english[namespace][key] = entry
                        # 处理中文文件
                        elif is_chinese:
                            for key, value in extracted_data.items():
                                # 从master_english中查找对应的英文值，如果找不到则使用空字符串
                                en_value = master_english[namespace][key].en if namespace in master_english and key in master_english[namespace] else ""
                                entry = LanguageEntry(
                                    key=key,
                                    en=en_value,
                                    zh=value,
                                    namespace=namespace
                                )
                                internal_chinese[namespace][key] = entry
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取JAR文件: {jar_file.name} - 错误: {e}")
        
        logging.info(f"  - Mods扫描完成。共扫描 {len(jar_files)} 个JAR文件，发现 {len(master_english)} 个含语言文件的命名空间。")
        return result
    
    def extract_from_packs(self, zip_paths: List[Path], master_english: Dict[str, Dict[str, LanguageEntry]]) -> Dict[str, str]:
        """从第三方汉化包中提取语言数据"""
        final_pack_chinese_dict = {}
        
        if not zip_paths:
            logging.info("  - 未提供第三方汉化包，跳过处理。")
            return final_pack_chinese_dict
        
        logging.info(f"  - 正在读取 {len(zip_paths)} 个第三方汉化包...")
        
        for zip_path in reversed(zip_paths):
            if not zip_path.exists() or not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
                logging.warning(f"  - 无效的ZIP文件，已跳过: {zip_path}")
                continue
            
            current_zip_chinese_dict = defaultdict(dict)
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang/zh_cn' not in file_info.filename.lower():
                            continue
                        
                        result_tuple = self._process_zip_file(zf, file_info, {}, current_zip_chinese_dict, zip_path.name)
                        if result_tuple[0] is None:
                            continue
                        
                        namespace, _, _, extracted_data, _, _ = result_tuple
                        
                        # 过滤掉与英文相同的翻译
                        for key, zh_value in extracted_data.items():
                            en_value = master_english.get(namespace, {}).get(key, None)
                            if en_value and en_value.en != zh_value:
                                final_pack_chinese_dict[key] = zh_value
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取汉化包: {zip_path.name} - 错误: {e}")
        
        logging.info(f"  - {len(zip_paths)} 个第三方汉化包处理完毕，共聚合 {len(final_pack_chinese_dict)} 条有效汉化。")
        return final_pack_chinese_dict
    
    def run(self, mods_dir: Path, zip_paths: List[Path], community_dict_path: str, progress_update_callback=None) -> ExtractionResult:
        """执行完整的提取流程"""
        logging.info("--- 阶段 1: 开始聚合所有语言数据 ---")
        
        # 从Mods中提取数据
        result = self.extract_from_mods(mods_dir, progress_update_callback)
        
        # 从第三方汉化包中提取数据
        result.pack_chinese = self.extract_from_packs(zip_paths, result.master_english)
        
        # 统计结果
        total_en = sum(len(d) for d in result.master_english.values())
        total_zh_internal = sum(len(d) for d in result.internal_chinese.values())
        
        logging.info(f"数据聚合完成。共发现 {len(result.master_english)} 个命名空间, {total_en} 条英文原文, {total_zh_internal} 条模组自带中文。")
        
        return result
