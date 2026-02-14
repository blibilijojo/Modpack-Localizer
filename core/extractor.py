import zipfile
import json
import logging
import sqlite3
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict
from utils import file_utils, config_manager

def is_json_content(content: str) -> bool:
    """检查内容是否为JSON格式"""
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        return False

def is_toml_content(content: str) -> bool:
    """检查内容是否为TOML格式"""
    return 'displayName' in content and ('=' in content or ':=' in content)

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
        self._module_names_cache = {}  # 添加缓存属性
        self._curseforge_names_cache = {}  # 添加curseforge名称缓存属性
        self._modrinth_names_cache = {}  # 添加modrinth名称缓存属性
    
    def _extract_from_text(self, content: str, file_format: str, file_path_for_log: str) -> Dict[str, str]:
        """从文本内容中提取语言数据"""
        data = {}
        comment_counter = 0
        if file_format == 'json':
            # 始终使用正则表达式解析JSON文件
            for match in self.JSON_KEY_VALUE_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2)
                # 处理Unicode转义序列（如\u963f），但保留\n等转义字符
                import re
                # 先将\n、\t等常见转义字符暂时替换为占位符
                temp_value = value.replace('\\n', '__NEWLINE__')
                temp_value = temp_value.replace('\\t', '__TAB__')
                temp_value = temp_value.replace('\\r', '__CARRIAGE__')
                # 处理Unicode转义序列
                temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
                # 恢复占位符为原始转义字符
                temp_value = temp_value.replace('__NEWLINE__', '\\n')
                temp_value = temp_value.replace('__TAB__', '\\t')
                temp_value = temp_value.replace('__CARRIAGE__', '\\r')
                # 处理引号，将 \" 替换为 "
                temp_value = temp_value.replace('\\"', '"')
                # 忽略_comment条目
                if key != '_comment':
                    data[key] = temp_value
        elif file_format == 'lang':
            for match in self.LANG_KV_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2).strip()
                # 忽略_comment条目
                if key != '_comment':
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
        
        base_namespace = self._get_namespace_from_path(file_info.filename)
        file_format = 'lang' if path_str_lower.endswith('.lang') else 'json'
        
        # Check if other format already exists for this base namespace
        # We'll need to scan through existing namespaces to check
        # This is a simplified check - in practice, we'll handle it in extract_from_mods
        namespace = base_namespace
        log_path = f"{source_zip_name} -> {file_info.filename}"
        
        try:
            with zf.open(file_info) as f:
                content = f.read().decode('utf-8-sig')
        except UnicodeDecodeError as e:
            # 处理非UTF-8编码的文件，跳过该文件
            logging.warning(f"文件编码不是UTF-8，跳过处理: {log_path} - {e}")
            return None, None, None, None, None, None
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
                    # First pass: collect all language files for this jar
                    language_files = []
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang' not in file_info.filename or not file_info.filename.startswith('assets/'):
                            continue
                        
                        result_tuple = self._process_zip_file(zf, file_info, master_english, internal_chinese, jar_file.name)
                        if result_tuple[0] is None:
                            continue
                        
                        language_files.append(result_tuple)
                    
                    # Check for both formats in this jar
                    formats_by_namespace = {}
                    for namespace, file_format, content, extracted_data, is_english, is_chinese in language_files:
                        if namespace not in formats_by_namespace:
                            formats_by_namespace[namespace] = set()
                        formats_by_namespace[namespace].add(file_format)
                    
                    # Process files with proper namespace handling
                    for namespace, file_format, content, extracted_data, is_english, is_chinese in language_files:
                        # Determine if we need to add format suffix
                        if len(formats_by_namespace[namespace]) > 1:
                            # Both formats exist, use namespace with suffix
                            final_namespace = f"{namespace}:{file_format}"
                        else:
                            # Only one format exists, use namespace without suffix
                            final_namespace = namespace
                        
                        # 初始化命名空间信息
                        if final_namespace not in namespace_info:
                            jar_name = jar_file.name
                            if len(formats_by_namespace[namespace]) > 1:
                                jar_name += " (both formats)"
                            namespace_info[final_namespace] = NamespaceInfo(
                                name=final_namespace,
                                jar_name=jar_name,
                                file_format=file_format
                            )
                        
                        # 更新命名空间的文件格式（优先使用JSON）
                        if file_format == 'json':
                            namespace_info[final_namespace].file_format = file_format
                        
                        # 处理英文文件
                        if is_english:
                            raw_english_files[final_namespace] = content
                            namespace_info[final_namespace].raw_content = content
                            
                            for key, value in extracted_data.items():
                                entry = LanguageEntry(
                                    key=key,
                                    en=value,
                                    namespace=final_namespace
                                )
                                master_english[final_namespace][key] = entry
                        # 处理中文文件
                        elif is_chinese:
                            for key, value in extracted_data.items():
                                # 从master_english中查找对应的英文值，如果找不到则使用空字符串
                                en_value = master_english[final_namespace][key].en if final_namespace in master_english and key in master_english[final_namespace] else ""
                                entry = LanguageEntry(
                                    key=key,
                                    en=en_value,
                                    zh=value,
                                    namespace=final_namespace
                                )
                                internal_chinese[final_namespace][key] = entry
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
        
        # 构建命名空间映射，用于处理带有格式后缀的命名空间
        namespace_map = {}
        for full_namespace in master_english.keys():
            if ":" in full_namespace:
                base_namespace = full_namespace.split(":", 1)[0]
                if base_namespace not in namespace_map:
                    namespace_map[base_namespace] = []
                namespace_map[base_namespace].append(full_namespace)
            else:
                if full_namespace not in namespace_map:
                    namespace_map[full_namespace] = []
                namespace_map[full_namespace].append(full_namespace)
        
        for zip_path in reversed(zip_paths):
            if not zip_path.exists() or not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
                logging.warning(f"  - 无效的ZIP文件，已跳过: {zip_path}")
                continue
            
            current_zip_chinese_dict = defaultdict(dict)
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang/zh_cn' not in file_info.filename.lower() or not file_info.filename.startswith('assets/'):
                            continue
                        
                        result_tuple = self._process_zip_file(zf, file_info, {}, current_zip_chinese_dict, zip_path.name)
                        if result_tuple[0] is None:
                            continue
                        
                        namespace, file_format, _, extracted_data, _, _ = result_tuple
                        
                        # 过滤掉与英文相同的翻译
                        for key, zh_value in extracted_data.items():
                            # 忽略_comment键
                            if key == '_comment':
                                continue
                            
                            # 尝试匹配原始命名空间
                            en_value = master_english.get(namespace, {}).get(key, None)
                            if en_value and en_value.en != zh_value:
                                final_pack_chinese_dict[key] = zh_value
                            else:
                                # 尝试匹配带有格式后缀的命名空间
                                if namespace in namespace_map:
                                    for full_namespace in namespace_map[namespace]:
                                        en_value = master_english.get(full_namespace, {}).get(key, None)
                                        if en_value and en_value.en != zh_value:
                                            final_pack_chinese_dict[key] = zh_value
                                            break
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取汉化包: {zip_path.name} - 错误: {e}")
        
        logging.info(f"  - {len(zip_paths)} 个第三方汉化包处理完毕，共聚合 {len(final_pack_chinese_dict)} 条有效汉化。")
        return final_pack_chinese_dict
    
    def extract_module_names(self, root_dir: Path) -> List[Dict[str, str]]:
        """从指定目录提取模组名称"""
        # 检查缓存
        cache_key = str(root_dir)
        if cache_key in self._module_names_cache:
            logging.info("--- 从缓存中获取模组名称 ---")
            return self._module_names_cache[cache_key]
        
        logging.info("--- 开始提取模组名称 ---")
        
        module_names = []
        processed_files: Set[str] = set()
        
        # 支持的文件扩展名
        extensions = ['.json', '.toml', '.info']
        
        # 扫描目录中的文件
        self._scan_directory(root_dir, extensions, module_names, processed_files)
        
        # 扫描目录中的JAR文件
        jar_files = list(root_dir.glob('*.jar'))
        logging.info(f"发现 {len(jar_files)} 个JAR文件")
        
        for jar_file in jar_files:
            self._process_jar_file(jar_file, module_names, processed_files)
        
        # 去重
        unique_modules = []
        seen_names = set()
        for module in module_names:
            name = module.get('name')
            if name and name not in seen_names:
                unique_modules.append(module)
                seen_names.add(name)
        
        # 存储到缓存
        self._module_names_cache[cache_key] = unique_modules
        
        logging.info(f"模组名称提取完成。共发现 {len(unique_modules)} 个模组名称。")
        return unique_modules
    
    def extract_curseforge_names(self, root_dir: Path) -> List[Dict[str, str]]:
        """从指定目录提取curseforge名称"""
        # 检查缓存
        cache_key = str(root_dir)
        if cache_key in self._curseforge_names_cache:
            logging.info("--- 从缓存中获取curseforge名称 ---")
            return self._curseforge_names_cache[cache_key]
        
        logging.info("--- 开始提取curseforge名称 ---")
        
        curseforge_names = []
        processed_files: Set[str] = set()
        
        # 支持的文件扩展名
        extensions = ['.json', '.toml', '.info']
        
        # 扫描目录中的文件
        self._scan_directory_for_curseforge(root_dir, extensions, curseforge_names, processed_files)
        
        # 扫描目录中的JAR文件
        jar_files = list(root_dir.glob('*.jar'))
        logging.info(f"发现 {len(jar_files)} 个JAR文件")
        
        for jar_file in jar_files:
            self._process_jar_file_for_curseforge(jar_file, curseforge_names, processed_files)
        
        # 去重
        unique_curseforge = []
        seen_names = set()
        for module in curseforge_names:
            name = module.get('curseforge_name')
            if name and name not in seen_names:
                unique_curseforge.append(module)
                seen_names.add(name)
        
        # 存储到缓存
        self._curseforge_names_cache[cache_key] = unique_curseforge
        
        logging.info(f"curseforge名称提取完成。共发现 {len(unique_curseforge)} 个curseforge名称。")
        return unique_curseforge
    
    def extract_modrinth_names(self, root_dir: Path, excluded_jar_files: List[Path] = None) -> List[Dict[str, str]]:
        """从指定目录提取Modrinth名称
        
        Args:
            root_dir: 要扫描的根目录
            excluded_jar_files: 要排除的JAR文件列表（这些文件已经有Curseforge名称）
        """
        # 检查缓存
        cache_key = str(root_dir)
        if excluded_jar_files:
            # 如果有排除的文件，不使用缓存
            use_cache = False
        else:
            use_cache = True
            if cache_key in self._modrinth_names_cache:
                logging.info("--- 从缓存中获取Modrinth名称 ---")
                return self._modrinth_names_cache[cache_key]
        
        logging.info("--- 开始提取Modrinth名称 ---")
        
        modrinth_names = []
        processed_files: Set[str] = set()
        
        # 支持的文件扩展名
        extensions = ['.json', '.toml', '.info']
        
        # 扫描目录中的文件
        # 如果有排除的JAR文件，我们需要确定哪些目录文件也应该被排除
        if excluded_jar_files:
            # 从排除的JAR文件中提取模组名称，用于排除目录中的相关文件
            excluded_mod_names = set()
            for jar_file in excluded_jar_files:
                # 从JAR文件名中提取模组名称（去掉版本号等后缀）
                jar_name = jar_file.name
                # 去掉.jar后缀
                if jar_name.endswith('.jar'):
                    jar_name = jar_name[:-4]
                # 去掉常见的后缀（如-fabric, -forge等）
                import re
                # 匹配常见的后缀模式
                jar_name = re.sub(r'-fabric.*', '', jar_name, flags=re.IGNORECASE)
                jar_name = re.sub(r'-forge.*', '', jar_name, flags=re.IGNORECASE)
                jar_name = re.sub(r'-mc.*', '', jar_name, flags=re.IGNORECASE)
                jar_name = re.sub(r'_fabric.*', '', jar_name, flags=re.IGNORECASE)
                jar_name = re.sub(r'_forge.*', '', jar_name, flags=re.IGNORECASE)
                jar_name = re.sub(r'_mc.*', '', jar_name, flags=re.IGNORECASE)
                # 去掉版本号
                jar_name = re.sub(r'-\d+\.\d+.*', '', jar_name)
                jar_name = re.sub(r'_\d+\.\d+.*', '', jar_name)
                if jar_name:
                    excluded_mod_names.add(jar_name.lower())
            
            # 扫描目录中的文件，但排除那些可能属于已排除模组的文件
            for ext in extensions:
                for file_path in root_dir.glob(f'*{ext}'):
                    if file_path.is_file():
                        # 检查文件名是否与排除的模组名称相关
                        file_name = file_path.name
                        file_name_lower = file_name.lower()
                        
                        # 检查是否应该排除这个文件
                        exclude_file = False
                        for mod_name in excluded_mod_names:
                            if mod_name in file_name_lower:
                                exclude_file = True
                                break
                        
                        if not exclude_file:
                            file_key = str(file_path)
                            if file_key not in processed_files:
                                logging.debug(f"处理文件以提取Modrinth名称: {file_path}")
                                self._process_module_file_for_modrinth(file_path, modrinth_names)
                                processed_files.add(file_key)
            
            # 扫描META-INF目录，但同样排除相关文件
            meta_inf_dir = root_dir / 'META-INF'
            if meta_inf_dir.exists() and meta_inf_dir.is_dir():
                for ext in extensions:
                    for file_path in meta_inf_dir.glob(f'*{ext}'):
                        if file_path.is_file():
                            file_key = str(file_path)
                            if file_key not in processed_files:
                                logging.debug(f"处理文件以提取Modrinth名称: {file_path}")
                                self._process_module_file_for_modrinth(file_path, modrinth_names)
                                processed_files.add(file_key)
        else:
            # 如果没有排除的文件，正常扫描目录
            self._scan_directory_for_modrinth(root_dir, extensions, modrinth_names, processed_files)
        
        # 扫描目录中的JAR文件
        all_jar_files = list(root_dir.glob('*.jar'))
        
        # 过滤出需要处理的JAR文件（排除那些已经有Curseforge名称的文件）
        if excluded_jar_files:
            excluded_paths = set(str(f) for f in excluded_jar_files)
            jar_files = [f for f in all_jar_files if str(f) not in excluded_paths]
            logging.info(f"发现 {len(all_jar_files)} 个JAR文件，其中 {len(excluded_jar_files)} 个已有Curseforge名称，将处理剩余 {len(jar_files)} 个JAR文件")
        else:
            jar_files = all_jar_files
            logging.info(f"发现 {len(jar_files)} 个JAR文件")
        
        for jar_file in jar_files:
            self._process_jar_file_for_modrinth(jar_file, modrinth_names, processed_files)
        
        # 去重
        unique_modrinth = []
        seen_names = set()
        for module in modrinth_names:
            name = module.get('modrinth_name')
            if name and name not in seen_names:
                unique_modrinth.append(module)
                seen_names.add(name)
        
        # 存储到缓存（仅当没有排除文件时）
        if use_cache:
            self._modrinth_names_cache[cache_key] = unique_modrinth
        
        logging.info(f"Modrinth名称提取完成。共发现 {len(unique_modrinth)} 个Modrinth名称。")
        return unique_modrinth
    
    def _scan_directory(self, directory: Path, extensions: List[str], module_names: List[Dict[str, str]], processed_files: Set[str]):
        """扫描目录中的文件"""
        # 扫描根目录
        for ext in extensions:
            for file_path in directory.glob(f'*{ext}'):
                if file_path.is_file():
                    file_key = str(file_path)
                    if file_key not in processed_files:
                        logging.debug(f"处理文件: {file_path}")
                        self._process_module_file(file_path, module_names)
                        processed_files.add(file_key)
        
        # 扫描META-INF目录
        meta_inf_dir = directory / 'META-INF'
        if meta_inf_dir.exists() and meta_inf_dir.is_dir():
            for ext in extensions:
                for file_path in meta_inf_dir.glob(f'*{ext}'):
                    if file_path.is_file():
                        file_key = str(file_path)
                        if file_key not in processed_files:
                            logging.debug(f"处理文件: {file_path}")
                            self._process_module_file(file_path, module_names)
                            processed_files.add(file_key)
    
    def _scan_directory_for_curseforge(self, directory: Path, extensions: List[str], curseforge_names: List[Dict[str, str]], processed_files: Set[str]):
        """扫描目录中的文件以提取curseforge名称"""
        # 扫描根目录
        for ext in extensions:
            for file_path in directory.glob(f'*{ext}'):
                if file_path.is_file():
                    file_key = str(file_path)
                    if file_key not in processed_files:
                        logging.debug(f"处理文件以提取curseforge名称: {file_path}")
                        self._process_module_file_for_curseforge(file_path, curseforge_names)
                        processed_files.add(file_key)
        
        # 扫描META-INF目录
        meta_inf_dir = directory / 'META-INF'
        if meta_inf_dir.exists() and meta_inf_dir.is_dir():
            for ext in extensions:
                for file_path in meta_inf_dir.glob(f'*{ext}'):
                    if file_path.is_file():
                        file_key = str(file_path)
                        if file_key not in processed_files:
                            logging.debug(f"处理文件以提取curseforge名称: {file_path}")
                            self._process_module_file_for_curseforge(file_path, curseforge_names)
                            processed_files.add(file_key)
    
    def _scan_directory_for_modrinth(self, directory: Path, extensions: List[str], modrinth_names: List[Dict[str, str]], processed_files: Set[str]):
        """扫描目录中的文件以提取Modrinth名称"""
        # 扫描根目录
        for ext in extensions:
            for file_path in directory.glob(f'*{ext}'):
                if file_path.is_file():
                    file_key = str(file_path)
                    if file_key not in processed_files:
                        logging.debug(f"处理文件以提取Modrinth名称: {file_path}")
                        self._process_module_file_for_modrinth(file_path, modrinth_names)
                        processed_files.add(file_key)
        
        # 扫描META-INF目录
        meta_inf_dir = directory / 'META-INF'
        if meta_inf_dir.exists() and meta_inf_dir.is_dir():
            for ext in extensions:
                for file_path in meta_inf_dir.glob(f'*{ext}'):
                    if file_path.is_file():
                        file_key = str(file_path)
                        if file_key not in processed_files:
                            logging.debug(f"处理文件以提取Modrinth名称: {file_path}")
                            self._process_module_file_for_modrinth(file_path, modrinth_names)
                            processed_files.add(file_key)
    
    def _process_jar_file(self, jar_file: Path, module_names: List[Dict[str, str]], processed_files: Set[str]):
        """处理JAR文件中的模组信息"""
        try:
            with zipfile.ZipFile(jar_file, 'r') as zf:
                # 检查JAR文件中的相关文件
                for file_info in zf.infolist():
                    # 跳过目录
                    if file_info.filename.endswith('/'):
                        continue
                    
                    # 检查是否是我们要找的文件
                    file_path = file_info.filename
                    file_key = f"{jar_file}:{file_path}"
                    
                    if file_key in processed_files:
                        continue
                    
                    # 检查文件路径是否在根目录或META-INF目录
                    if '/' not in file_path or file_path.startswith('META-INF/'):
                        # 检查文件扩展名
                        ext = Path(file_path).suffix
                        if ext in ['.json', '.toml', '.info']:
                            logging.debug(f"处理JAR文件中的文件: {jar_file} -> {file_path}")
                            try:
                                with zf.open(file_info) as f:
                                    content = f.read().decode('utf-8-sig')
                                    # 创建包含JAR文件名的完整路径
                                    full_path = f"{jar_file.name}/{file_path}"
                                    # 根据文件类型处理
                                    if Path(file_path).suffix in ['.json', '.info'] or is_json_content(content):
                                        self._extract_from_json(Path(full_path), content, module_names)
                                    elif Path(file_path).suffix == '.toml' or is_toml_content(content):
                                        self._extract_from_toml(Path(full_path), content, module_names)
                                    processed_files.add(file_key)
                            except UnicodeDecodeError:
                                logging.warning(f"JAR文件中的文件编码错误，跳过处理: {jar_file} -> {file_path}")
                            except Exception as e:
                                logging.warning(f"处理JAR文件中的文件时发生错误: {jar_file} -> {file_path} - {e}")
        except zipfile.BadZipFile:
            logging.warning(f"无效的JAR文件，跳过处理: {jar_file}")
        except Exception as e:
            logging.warning(f"处理JAR文件时发生错误: {jar_file} - {e}")
    
    def _process_jar_file_for_curseforge(self, jar_file: Path, curseforge_names: List[Dict[str, str]], processed_files: Set[str]):
        """处理JAR文件中的curseforge信息"""
        try:
            with zipfile.ZipFile(jar_file, 'r') as zf:
                # 检查JAR文件中的相关文件
                for file_info in zf.infolist():
                    # 跳过目录
                    if file_info.filename.endswith('/'):
                        continue
                    
                    # 检查是否是我们要找的文件
                    file_path = file_info.filename
                    file_key = f"{jar_file}:{file_path}"
                    
                    if file_key in processed_files:
                        continue
                    
                    # 检查文件路径是否在根目录或META-INF目录
                    if '/' not in file_path or file_path.startswith('META-INF/'):
                        # 检查文件扩展名
                        ext = Path(file_path).suffix
                        if ext in ['.json', '.toml', '.info']:
                            logging.debug(f"处理JAR文件中的文件以提取curseforge名称: {jar_file} -> {file_path}")
                            try:
                                with zf.open(file_info) as f:
                                    content = f.read().decode('utf-8-sig')
                                    # 创建包含JAR文件名的完整路径
                                    full_path = f"{jar_file.name}/{file_path}"
                                    # 根据文件类型处理
                                    if Path(file_path).suffix in ['.json', '.info'] or is_json_content(content):
                                        self._extract_curseforge_from_json(Path(full_path), content, curseforge_names)
                                    elif Path(file_path).suffix == '.toml' or is_toml_content(content):
                                        self._extract_curseforge_from_toml(Path(full_path), content, curseforge_names)
                                    processed_files.add(file_key)
                            except UnicodeDecodeError:
                                logging.warning(f"JAR文件中的文件编码错误，跳过处理: {jar_file} -> {file_path}")
                            except Exception as e:
                                logging.warning(f"处理JAR文件中的文件时发生错误: {jar_file} -> {file_path} - {e}")
        except zipfile.BadZipFile:
            logging.warning(f"无效的JAR文件，跳过处理: {jar_file}")
        except Exception as e:
            logging.warning(f"处理JAR文件时发生错误: {jar_file} - {e}")
    
    def _process_jar_file_for_modrinth(self, jar_file: Path, modrinth_names: List[Dict[str, str]], processed_files: Set[str]):
        """处理JAR文件中的Modrinth信息"""
        try:
            with zipfile.ZipFile(jar_file, 'r') as zf:
                # 检查JAR文件中的相关文件
                for file_info in zf.infolist():
                    # 跳过目录
                    if file_info.filename.endswith('/'):
                        continue
                    
                    # 检查是否是我们要找的文件
                    file_path = file_info.filename
                    file_key = f"{jar_file}:{file_path}"
                    
                    if file_key in processed_files:
                        continue
                    
                    # 检查文件路径是否在根目录或META-INF目录
                    if '/' not in file_path or file_path.startswith('META-INF/'):
                        # 检查文件扩展名
                        ext = Path(file_path).suffix
                        if ext in ['.json', '.toml', '.info']:
                            logging.debug(f"处理JAR文件中的文件以提取Modrinth名称: {jar_file} -> {file_path}")
                            try:
                                with zf.open(file_info) as f:
                                    content = f.read().decode('utf-8-sig')
                                    # 创建包含JAR文件名的完整路径
                                    full_path = f"{jar_file.name}/{file_path}"
                                    # 根据文件类型处理
                                    if Path(file_path).suffix in ['.json', '.info'] or is_json_content(content):
                                        self._extract_modrinth_from_json(Path(full_path), content, modrinth_names)
                                    elif Path(file_path).suffix == '.toml' or is_toml_content(content):
                                        self._extract_modrinth_from_toml(Path(full_path), content, modrinth_names)
                                    processed_files.add(file_key)
                            except UnicodeDecodeError:
                                logging.warning(f"JAR文件中的文件编码错误，跳过处理: {jar_file} -> {file_path}")
                            except Exception as e:
                                logging.warning(f"处理JAR文件中的文件时发生错误: {jar_file} -> {file_path} - {e}")
        except zipfile.BadZipFile:
            logging.warning(f"无效的JAR文件，跳过处理: {jar_file}")
        except Exception as e:
            logging.warning(f"处理JAR文件时发生错误: {jar_file} - {e}")
    
    def _process_module_file(self, file_path: Path, module_names: List[Dict[str, str]]):
        """处理单个模组信息文件"""
        try:
            content = file_path.read_text(encoding='utf-8-sig')
            
            # 检查文件内容是否为JSON格式
            if file_path.suffix in ['.json', '.info'] or is_json_content(content):
                self._extract_from_json(file_path, content, module_names)
            elif file_path.suffix == '.toml' or is_toml_content(content):
                self._extract_from_toml(file_path, content, module_names)
        except UnicodeDecodeError:
            logging.warning(f"文件编码错误，跳过处理: {file_path}")
        except PermissionError:
            logging.warning(f"无权限访问文件，跳过处理: {file_path}")
        except Exception as e:
            logging.warning(f"处理文件时发生错误: {file_path} - {e}")
    
    def _process_module_file_for_curseforge(self, file_path: Path, curseforge_names: List[Dict[str, str]]):
        """处理单个文件以提取curseforge名称"""
        try:
            content = file_path.read_text(encoding='utf-8-sig')
            
            # 检查文件内容是否为JSON格式
            if file_path.suffix in ['.json', '.info'] or is_json_content(content):
                self._extract_curseforge_from_json(file_path, content, curseforge_names)
            elif file_path.suffix == '.toml' or is_toml_content(content):
                self._extract_curseforge_from_toml(file_path, content, curseforge_names)
        except UnicodeDecodeError:
            logging.warning(f"文件编码错误，跳过处理: {file_path}")
        except PermissionError:
            logging.warning(f"无权限访问文件，跳过处理: {file_path}")
        except Exception as e:
            logging.warning(f"处理文件时发生错误: {file_path} - {e}")
    
    def _process_module_file_for_modrinth(self, file_path: Path, modrinth_names: List[Dict[str, str]]):
        """处理单个文件以提取Modrinth名称"""
        try:
            content = file_path.read_text(encoding='utf-8-sig')
            
            # 检查文件内容是否为JSON格式
            if file_path.suffix in ['.json', '.info'] or is_json_content(content):
                self._extract_modrinth_from_json(file_path, content, modrinth_names)
            elif file_path.suffix == '.toml' or is_toml_content(content):
                self._extract_modrinth_from_toml(file_path, content, modrinth_names)
        except UnicodeDecodeError:
            logging.warning(f"文件编码错误，跳过处理: {file_path}")
        except PermissionError:
            logging.warning(f"无权限访问文件，跳过处理: {file_path}")
        except Exception as e:
            logging.warning(f"处理文件时发生错误: {file_path} - {e}")
    
    def _extract_from_json(self, file_path: Path, content: str, module_names: List[Dict[str, str]]):
        """从JSON文件中提取模组名称"""
        try:
            data = json.loads(content)
            # 尝试从不同字段提取名称
            name_fields = ['name', 'displayName', 'modName', 'title']
            
            # 检查根级别字段
            if isinstance(data, dict):
                for field in name_fields:
                    if field in data and isinstance(data[field], str):
                        module_names.append({
                            'name': data[field],
                            'source': str(file_path)
                        })
                        return
                
                # 检查mods数组 (mcmod.info格式)
                if 'mods' in data and isinstance(data['mods'], list):
                    for mod in data['mods']:
                        if isinstance(mod, dict):
                            for field in name_fields:
                                if field in mod and isinstance(mod[field], str):
                                    module_names.append({
                                        'name': mod[field],
                                        'source': str(file_path)
                                    })
                                    return
                # 检查modList数组 (另一种格式)
                elif 'modList' in data and isinstance(data['modList'], list):
                    for mod in data['modList']:
                        if isinstance(mod, dict):
                            for field in name_fields:
                                if field in mod and isinstance(mod[field], str):
                                    module_names.append({
                                        'name': mod[field],
                                        'source': str(file_path)
                                    })
                                    return
            # 检查根级别是否是数组 (mcmod.info格式的另一种形式)
            elif isinstance(data, list):
                for mod in data:
                    if isinstance(mod, dict):
                        for field in name_fields:
                            if field in mod and isinstance(mod[field], str):
                                module_names.append({
                                    'name': mod[field],
                                    'source': str(file_path)
                                })
                                return
        except json.JSONDecodeError:
            logging.warning(f"JSON格式错误，尝试修复并重新解析: {file_path}")
            # 尝试修复JSON字符串
            try:
                # 移除多余的换行符和空白字符
                import re
                # 尝试匹配name字段的简单模式
                name_match = re.search(r'"name"\s*:\s*"([^"]*)"', content)
                if name_match:
                    module_names.append({
                        'name': name_match.group(1),
                        'source': str(file_path)
                    })
                    return
                # 尝试更复杂的模式，匹配modList中的name
                modlist_name_match = re.search(r'"modList"\s*:\s*\[\s*\{[\s\S]*?"name"\s*:\s*"([^"]*)"', content)
                if modlist_name_match:
                    module_names.append({
                        'name': modlist_name_match.group(1),
                        'source': str(file_path)
                    })
                    return
            except Exception as e:
                logging.warning(f"修复JSON时发生错误: {e}")
            logging.warning(f"无法提取模组名称，跳过处理: {file_path}")
    
    def _extract_from_toml(self, file_path: Path, content: str, module_names: List[Dict[str, str]]):
        """从TOML文件中提取模组名称"""
        try:
            # 简单解析TOML格式，查找displayName字段
            import re
            # 匹配 displayName="..." 或 displayName = "..." 格式，支持包含单引号的字符串
            pattern = re.compile(r'displayName\s*=\s*(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)
            match = pattern.search(content)
            
            if match:
                module_names.append({
                    'name': match.group(2),
                    'source': str(file_path)
                })
        except Exception as e:
            logging.warning(f"解析TOML文件时发生错误: {file_path} - {e}")

    def _extract_curseforge_from_json(self, file_path: Path, content: str, curseforge_names: List[Dict[str, str]]):
        """从JSON文件中提取curseforge名称"""
        try:
            # 搜索包含curseforge.com的字符串
            import re
            # 匹配完整的curseforge链接，确保捕获完整的URL
            curseforge_pattern = re.compile(r'(?:https?://)?(?:www\.)?curseforge\.com/[^"\'\s]+', re.IGNORECASE)
            matches = curseforge_pattern.finditer(content)
            
            for match in matches:
                curseforge_url = match.group(0)
                # 确保URL包含完整的路径
                if 'minecraft/mc-mods/' in curseforge_url:
                    # 按照优先级提取curseforge名称
                    # 提取minecraft/mc-mods/后面的内容
                    parts = curseforge_url.split('minecraft/mc-mods/')
                    if len(parts) > 1:
                        curseforge_name = parts[1].split('/')[0]
                    else:
                        # 尝试通用提取规则
                        parts = curseforge_url.split('/')
                        if len(parts) > 4:
                            # 有第四个反斜杠
                            curseforge_name = parts[4]
                        elif len(parts) == 4:
                            # 没有第四个反斜杠，使用第三个反斜杠后的内容
                            curseforge_name = parts[3]
                        else:
                            # 格式不符合要求，跳过
                            continue
                    
                    # 清理提取的名称，移除可能的查询参数或其他内容
                    curseforge_name = curseforge_name.split('?')[0].split('#')[0]
                    
                    if curseforge_name and not curseforge_name.endswith(':'):
                        curseforge_names.append({
                            'curseforge_name': curseforge_name,
                            'source': str(file_path)
                        })
                        return
        except Exception as e:
            logging.warning(f"从JSON文件提取curseforge名称时发生错误: {file_path} - {e}")
    
    def _extract_modrinth_from_json(self, file_path: Path, content: str, modrinth_names: List[Dict[str, str]]):
        """从JSON文件中提取Modrinth名称"""
        try:
            # 搜索包含modrinth.com的字符串
            import re
            # 匹配包含modrinth.com的链接
            modrinth_pattern = re.compile(r'modrinth\.com[^"\']*', re.IGNORECASE)
            matches = modrinth_pattern.finditer(content)
            
            for match in matches:
                modrinth_url = match.group(0)
                # 按照优先级提取Modrinth名称
                # 主提取规则：从mod/后的内容提取
                parts = modrinth_url.split('/')
                if 'mod' in parts:
                    mod_index = parts.index('mod')
                    if mod_index + 1 < len(parts):
                        modrinth_name = parts[mod_index + 1]
                    else:
                        # 格式不符合要求，跳过
                        continue
                else:
                    # 格式不符合要求，跳过
                    continue
                
                # 清理提取的名称，移除可能的查询参数或其他内容
                modrinth_name = modrinth_name.split('?')[0].split('#')[0]
                
                if modrinth_name:
                    # 添加modrinth-前缀以区分
                    modrinth_name = f"modrinth-{modrinth_name}"
                    modrinth_names.append({
                        'modrinth_name': modrinth_name,
                        'source': str(file_path)
                    })
                    return
        except Exception as e:
            logging.warning(f"从JSON文件提取Modrinth名称时发生错误: {file_path} - {e}")

    def _extract_curseforge_from_toml(self, file_path: Path, content: str, curseforge_names: List[Dict[str, str]]):
        """从TOML文件中提取curseforge名称"""
        try:
            # 搜索包含curseforge.com的字符串
            import re
            # 匹配完整的curseforge链接，确保捕获完整的URL
            curseforge_pattern = re.compile(r'(?:https?://)?(?:www\.)?curseforge\.com/[^"\'\s]+', re.IGNORECASE)
            matches = curseforge_pattern.finditer(content)
            
            for match in matches:
                curseforge_url = match.group(0)
                # 确保URL包含完整的路径
                if 'minecraft/mc-mods/' in curseforge_url:
                    # 按照优先级提取curseforge名称
                    # 提取minecraft/mc-mods/后面的内容
                    parts = curseforge_url.split('minecraft/mc-mods/')
                    if len(parts) > 1:
                        curseforge_name = parts[1].split('/')[0]
                    else:
                        # 尝试通用提取规则
                        parts = curseforge_url.split('/')
                        if len(parts) > 4:
                            # 有第四个反斜杠
                            curseforge_name = parts[4]
                        elif len(parts) == 4:
                            # 没有第四个反斜杠，使用第三个反斜杠后的内容
                            curseforge_name = parts[3]
                        else:
                            # 格式不符合要求，跳过
                            continue
                    
                    # 清理提取的名称，移除可能的查询参数或其他内容
                    curseforge_name = curseforge_name.split('?')[0].split('#')[0]
                    
                    if curseforge_name and not curseforge_name.endswith(':'):
                        curseforge_names.append({
                            'curseforge_name': curseforge_name,
                            'source': str(file_path)
                        })
                        return
        except Exception as e:
            logging.warning(f"从TOML文件提取curseforge名称时发生错误: {file_path} - {e}")
    
    def _extract_modrinth_from_toml(self, file_path: Path, content: str, modrinth_names: List[Dict[str, str]]):
        """从TOML文件中提取Modrinth名称"""
        try:
            # 搜索包含modrinth.com的字符串
            import re
            # 匹配包含modrinth.com的链接
            modrinth_pattern = re.compile(r'modrinth\.com[^"\']*', re.IGNORECASE)
            matches = modrinth_pattern.finditer(content)
            
            for match in matches:
                modrinth_url = match.group(0)
                # 按照优先级提取Modrinth名称
                # 主提取规则：从mod/后的内容提取
                parts = modrinth_url.split('/')
                if 'mod' in parts:
                    mod_index = parts.index('mod')
                    if mod_index + 1 < len(parts):
                        modrinth_name = parts[mod_index + 1]
                    else:
                        # 格式不符合要求，跳过
                        continue
                else:
                    # 格式不符合要求，跳过
                    continue
                
                # 清理提取的名称，移除可能的查询参数或其他内容
                modrinth_name = modrinth_name.split('?')[0].split('#')[0]
                
                if modrinth_name:
                    # 添加modrinth-前缀以区分
                    modrinth_name = f"modrinth-{modrinth_name}"
                    modrinth_names.append({
                        'modrinth_name': modrinth_name,
                        'source': str(file_path)
                    })
                    return
        except Exception as e:
            logging.warning(f"从TOML文件提取Modrinth名称时发生错误: {file_path} - {e}")

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
