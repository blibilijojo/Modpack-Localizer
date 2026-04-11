import zipfile
import json
import logging
import sqlite3
import re
import hashlib
import requests
import threading
import io
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from utils import file_utils, config_manager, mod_scan_cache
from utils.retry_logic import api_retry

from core.models import (
    LanguageEntry, NamespaceInfo, ExtractionResult,
    DictionaryEntry
)

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

def _curseforge_fingerprint_from_jar_bytes(file_data: bytes) -> str:
    """CurseForge 风格 MurmurHash2（与空白过滤规则与原先 process_jar_worker 一致）"""
    filtered_data = bytes([b for b in file_data if b not in (9, 10, 13, 32)])
    length = len(filtered_data)
    if length == 0:
        return "0"
    seed = 1
    m = 0x5BD1E995
    r = 24
    h = seed ^ length
    for i in range(0, length - (length % 4), 4):
        k = filtered_data[i] | (filtered_data[i+1] << 8) | (filtered_data[i+2] << 16) | (filtered_data[i+3] << 24)
        k = (k * m) & 0xFFFFFFFF
        k = (k ^ (k >> r)) & 0xFFFFFFFF
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h = (h ^ k) & 0xFFFFFFFF
    remaining = length % 4
    if remaining > 0:
        pos = length - remaining
        if remaining == 3:
            h = (h ^ (filtered_data[pos + 2] << 16)) & 0xFFFFFFFF
        if remaining >= 2:
            h = (h ^ (filtered_data[pos + 1] << 8)) & 0xFFFFFFFF
        if remaining >= 1:
            h = (h ^ filtered_data[pos]) & 0xFFFFFFFF
            h = (h * m) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) & 0xFFFFFFFF
    h = (h * m) & 0xFFFFFFFF
    h = (h ^ (h >> 15)) & 0xFFFFFFFF
    return str(h)


def _extract_mod_display_meta_from_jar_bytes(jar_file: Path, file_data: bytes) -> tuple[str, str]:
    """从 JAR 字节解析展示用 mod 名与 game_version（失败则回落为文件名）"""
    mod_name = ""
    game_version = ""
    try:
        with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
            if 'mcmod.info' in zf.namelist():
                try:
                    with zf.open('mcmod.info') as f:
                        content = f.read().decode('utf-8-sig')
                        if is_json_content(content):
                            data = json.loads(content)
                            if isinstance(data, list) and data:
                                mod_info = data[0]
                                if 'name' in mod_info:
                                    mod_name = mod_info['name']
                                if 'mcversion' in mod_info:
                                    game_version = mod_info['mcversion']
                            elif isinstance(data, dict) and 'modList' in data:
                                mod_list = data['modList']
                                if isinstance(mod_list, list) and mod_list:
                                    mod_info = mod_list[0]
                                    if 'name' in mod_info:
                                        mod_name = mod_info['name']
                                    if 'mcversion' in mod_info:
                                        game_version = mod_info['mcversion']
                except Exception:
                    pass

            if not mod_name and 'fabric.mod.json' in zf.namelist():
                try:
                    with zf.open('fabric.mod.json') as f:
                        content = f.read().decode('utf-8-sig')
                        if is_json_content(content):
                            data = json.loads(content)
                            if 'name' in data:
                                mod_name = data['name']
                            if not game_version:
                                if 'dependencies' in data and 'minecraft' in data['dependencies']:
                                    game_version = data['dependencies']['minecraft']
                except Exception:
                    pass

            if not mod_name and 'META-INF/mods.toml' in zf.namelist():
                try:
                    with zf.open('META-INF/mods.toml') as f:
                        content = f.read().decode('utf-8-sig')
                        for line in content.split('\n'):
                            line_stripped = line.strip()
                            if line_stripped.startswith('displayName') or line_stripped.startswith('name'):
                                if '=' in line_stripped:
                                    value = line_stripped.split('=', 1)[1].strip().strip('"'"'"'')
                                    if value:
                                        mod_name = value
                                        break
                except Exception:
                    pass

            if not mod_name:
                mod_name = jar_file.stem
                for suffix in ['.jar', '.zip', '.litemod']:
                    if mod_name.endswith(suffix):
                        mod_name = mod_name[:-len(suffix)]
                mod_name = mod_name.replace('.disabled', '').replace('.old', '')
    except Exception:
        mod_name = jar_file.stem
    return mod_name, game_version


def _jar_mod_fingerprints_and_meta(
    jar_file: Path, file_data: bytes, modrinth_hash: Optional[str] = None
) -> Tuple[str, str, str, str, str]:
    """
    单次读取后的完整分析。返回:
    jar_name, mod_name, curseforge_hash, modrinth_hash, game_version
    """
    if modrinth_hash is None:
        modrinth_hash = hashlib.sha1(file_data).hexdigest()
    curseforge_hash = _curseforge_fingerprint_from_jar_bytes(file_data)
    mod_name, game_version = _extract_mod_display_meta_from_jar_bytes(jar_file, file_data)
    return jar_file.name, mod_name, curseforge_hash, modrinth_hash, game_version


def process_jar_worker(jar_path_str):
    """处理单个 JAR（读盘一次）；供独立脚本或旧调用点使用。"""
    jar_file = Path(jar_path_str)
    try:
        with open(jar_file, 'rb') as f:
            file_data = f.read()
        return _jar_mod_fingerprints_and_meta(jar_file, file_data)
    except Exception:
        return jar_file.name, jar_file.stem, "", "", ""

class Extractor:
    """语言数据提取器"""
    
    def __init__(self):
        # 保持原有正则表达式规则不变
        self.LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
        self.JSON_KEY_VALUE_PATTERN = re.compile(r'"([^"]+)":\s*"((?:\\.|[^\\"])*)"', re.DOTALL)
        # 模组信息缓存，键为文件路径，值为(mod_name, curseforge_hash, modrinth_hash, game_version)
        self._mod_info_cache = {}
        self._mod_info_cache_lock = threading.Lock()
    
    def _extract_from_text(self, content: str, file_format: str, file_path_for_log: str) -> Dict[str, str]:
        """从文本内容中提取语言数据"""
        data = {}
        comment_counter = 0
        if file_format == 'json':
            # 始终使用正则表达式解析 JSON 文件
            for match in self.JSON_KEY_VALUE_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2)
                # 处理 Unicode 转义序列（如\u963f），但保留\n等转义字符
                import re
                # 先将\n、\t等常见转义字符暂时替换为占位符
                temp_value = value.replace('\\n', '__NEWLINE__')
                temp_value = temp_value.replace('\\t', '__TAB__')
                temp_value = temp_value.replace('\\r', '__CARRIAGE__')
                # 处理 Unicode 转义序列
                temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
                # 恢复占位符为原始转义字符
                temp_value = temp_value.replace('__NEWLINE__', '\\n')
                temp_value = temp_value.replace('__TAB__', '\\t')
                temp_value = temp_value.replace('__CARRIAGE__', '\\r')
                # 处理引号，将 \" 替换为 "
                temp_value = temp_value.replace('\\"', '"')
                # 处理 _comment 条目，为每个 _comment 添加序号
                if key == '_comment':
                    comment_counter += 1
                    data[f'_comment_{comment_counter}'] = temp_value
                else:
                    data[key] = temp_value
        elif file_format == 'lang':
            for match in self.LANG_KV_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2).strip()
                # 处理 _comment 条目，为每个 _comment 添加序号
                if key == '_comment':
                    comment_counter += 1
                    data[f'_comment_{comment_counter}'] = value
                else:
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
    
    def _load_dictionaries(self, community_dict_dir: str) -> tuple[Dict, Dict, Dict]:
        """加载各种词典"""
        # 加载用户词典
        user_dict = config_manager.load_user_dict()
        user_dict_by_key = user_dict.get('by_key', {})
        user_dict_by_origin = user_dict.get('by_origin_name', {})
        
        # 加载社区词典
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        
        if community_dict_dir:
            try:
                # 构建完整的文件路径
                dict_file_path = Path(community_dict_dir) / "Dict-Sqlite.db"
                
                if dict_file_path.is_file():
                    with sqlite3.connect(f"file:{dict_file_path}?mode=ro", uri=True) as con:
                        cur = con.cursor()
                        cur.execute("SELECT key, origin_name, trans_name, version FROM dict")
                        for key, origin_name, trans_name, version in cur.fetchall():
                            if key:
                                community_dict_by_key[key] = trans_name
                            if origin_name and trans_name:
                                community_dict_by_origin[origin_name].append({"trans": trans_name, "version": version or "0.0.0"})
            except Exception as e:
                logging.error(f"读取社区词典数据库时发生错误: {e}")
        
        return user_dict_by_key, user_dict_by_origin, community_dict_by_key
    
    def extract_from_mods(self, mods_dir: Path, extraction_progress_callback=None, stop_event=None) -> ExtractionResult:
        """从Mods文件夹中提取语言数据"""
        logging.debug(f"正在扫描Mods文件夹: {mods_dir}")
        
        result = ExtractionResult()
        master_english = result.master_english
        internal_chinese = result.internal_chinese
        namespace_info = result.namespace_info
        raw_english_files = result.raw_english_files
        
        jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar") if mods_dir.exists() else []
        
        for i, jar_file in enumerate(jar_files):
            if extraction_progress_callback and jar_files:
                extraction_progress_callback("scan_lang", i + 1, len(jar_files))
            
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
        
        logging.info(f"扫描完成: {len(jar_files)}个JAR, {len(master_english)}个命名空间")
        return result
    
    def extract_from_packs(self, zip_paths: List[Path], master_english: Dict[str, Dict[str, LanguageEntry]]) -> Dict[str, str]:
        """从第三方汉化包中提取语言数据"""
        final_pack_chinese_dict = {}
        
        if not zip_paths:
            logging.debug("未提供第三方汉化包，跳过处理。")
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

    def _extract_mod_info(self, jar_file: Path) -> tuple[str, str, str, str]:
        """从JAR文件中提取Mod信息（优化版本）"""
        # 检查缓存
        try:
            stat = jar_file.stat()
            cache_key = (str(jar_file), stat.st_mtime, stat.st_size)
            
            with self._mod_info_cache_lock:
                if cache_key in self._mod_info_cache:
                    return self._mod_info_cache[cache_key]
        except Exception:
            cache_key = None
        
        mod_name = ""
        curseforge_hash = ""
        modrinth_hash = ""
        game_version = ""

        try:
            # 一次性读取整个文件内容
            with open(jar_file, 'rb') as f:
                file_data = f.read()
            
            # 计算SHA1哈希（Modrinth）
            sha1_hash = hashlib.sha1()
            sha1_hash.update(file_data)
            modrinth_hash = sha1_hash.hexdigest()
            
            # 计算MurmurHash2哈希（CurseForge）
            # 过滤空白字符（制表符、换行符、回车符和空格）
            filtered_data = bytes([b for b in file_data if b not in (9, 10, 13, 32)])
            
            length = len(filtered_data)
            if length > 0:
                seed = 1
                m = 0x5BD1E995
                r = 24
                
                h = seed ^ length
                
                # 处理4字节块
                for i in range(0, length - (length % 4), 4):
                    k = filtered_data[i] | (filtered_data[i+1] << 8) | (filtered_data[i+2] << 16) | (filtered_data[i+3] << 24)
                    k = (k * m) & 0xFFFFFFFF
                    k = (k ^ (k >> r)) & 0xFFFFFFFF
                    k = (k * m) & 0xFFFFFFFF
                    
                    h = (h * m) & 0xFFFFFFFF
                    h = (h ^ k) & 0xFFFFFFFF
                
                # 处理剩余字节
                remaining = length % 4
                if remaining > 0:
                    pos = length - remaining
                    if remaining == 3:
                        h = (h ^ (filtered_data[pos + 2] << 16)) & 0xFFFFFFFF
                    if remaining >= 2:
                        h = (h ^ (filtered_data[pos + 1] << 8)) & 0xFFFFFFFF
                    if remaining >= 1:
                        h = (h ^ filtered_data[pos]) & 0xFFFFFFFF
                        h = (h * m) & 0xFFFFFFFF
                
                h = (h ^ (h >> 13)) & 0xFFFFFFFF
                h = (h * m) & 0xFFFFFFFF
                h = (h ^ (h >> 15)) & 0xFFFFFFFF
                
                curseforge_hash = str(h)
            else:
                curseforge_hash = "0"

            # 使用内存中的数据创建ZipFile对象
            with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
                # 尝试从mcmod.info提取
                if 'mcmod.info' in zf.namelist():
                    try:
                        with zf.open('mcmod.info') as f:
                            content = f.read().decode('utf-8-sig')
                            if is_json_content(content):
                                data = json.loads(content)
                                if isinstance(data, list) and data:
                                    mod_info = data[0]
                                    if 'name' in mod_info:
                                        mod_name = mod_info['name']
                                    if 'mcversion' in mod_info:
                                        game_version = mod_info['mcversion']
                                elif isinstance(data, dict) and 'modList' in data:
                                    mod_list = data['modList']
                                    if isinstance(mod_list, list) and mod_list:
                                        mod_info = mod_list[0]
                                        if 'name' in mod_info:
                                            mod_name = mod_info['name']
                                        if 'mcversion' in mod_info:
                                            game_version = mod_info['mcversion']
                    except Exception as e:
                        logging.debug(f"读取mcmod.info失败: {e}")

                # 尝试从fabric.mod.json提取
                if 'fabric.mod.json' in zf.namelist():
                    try:
                        with zf.open('fabric.mod.json') as f:
                            content = f.read().decode('utf-8-sig')
                            if is_json_content(content):
                                data = json.loads(content)
                                if not mod_name and 'name' in data:
                                    mod_name = data['name']
                                if not game_version:
                                    if 'dependencies' in data and 'minecraft' in data['dependencies']:
                                        game_version = data['dependencies']['minecraft']
                                    elif 'contact' in data and 'minecraft' in data.get('contact', {}):
                                        game_version = data['contact']['minecraft']
                    except Exception as e:
                        logging.debug(f"读取fabric.mod.json失败: {e}")

                # 尝试从mods.toml提取
                if 'META-INF/mods.toml' in zf.namelist():
                    try:
                        with zf.open('META-INF/mods.toml') as f:
                            content = f.read().decode('utf-8-sig')
                            lines = content.split('\n')
                            in_dependencies = False
                            for i, line in enumerate(lines):
                                line_stripped = line.strip()
                                if not mod_name and (line_stripped.startswith('displayName') or line_stripped.startswith('name')):
                                    if '=' in line_stripped:
                                        value = line_stripped.split('=', 1)[1].strip()
                                        value = value.strip('"'"'"'')
                                        mod_name = value
                                if not game_version:
                                    if '[[dependencies' in line:
                                        in_dependencies = True
                                    elif in_dependencies and 'minecraft' in line_stripped.lower() and '=' in line_stripped:
                                        value = line_stripped.split('=', 1)[1].strip()
                                        value = value.strip('"'"'"'')
                                        if self._is_version_string(value):
                                            game_version = value
                                        elif value.startswith('>=') or value.startswith('>'):
                                            match = re.search(r'(\d+\.\d+(?:\.\d+)?)', value)
                                            if match:
                                                game_version = match.group(1)
                                    elif ']]' in line:
                                        in_dependencies = False
                    except Exception as e:
                        logging.debug(f"读取mods.toml失败: {e}")

                # 如果没有找到名称，使用文件名
                if not mod_name:
                    mod_name = jar_file.stem
                    for suffix in ['.jar', '.zip', '.litemod']:
                        if mod_name.endswith(suffix):
                            mod_name = mod_name[:-len(suffix)]
                    mod_name = mod_name.replace('.disabled', '').replace('.old', '')

        except Exception as e:
            logging.error(f"提取Mod信息失败: {e}")
            mod_name = jar_file.stem

        if game_version:
            logging.info(f"从JAR文件提取到游戏版本: {game_version} (文件: {jar_file.name})")
        
        # 存储到缓存
        result = (mod_name, curseforge_hash, modrinth_hash, game_version)
        if cache_key:
            with self._mod_info_cache_lock:
                self._mod_info_cache[cache_key] = result
        
        return result
    
    def _is_version_string(self, value: str) -> bool:
        """检查字符串是否为版本号格式"""
        import re
        version_pattern = r'^\d+\.\d+(\.\d+)?$'
        return bool(re.match(version_pattern, value.strip()))
    
    def _match_github_version(self, game_version: str, loaders: str, github_versions: List[str]) -> str:
        """匹配最适合的GitHub版本号
        
        Args:
            game_version: 当前游戏版本，如 "1.20.1"
            loaders: 当前加载器，如 "forge"
            github_versions: GitHub版本列表，如 ["1.12.2", "1.16-fabric", "1.16"]
            
        Returns:
            最匹配的GitHub版本号
        """
        if not github_versions:
            return ""
        
        # 解析游戏版本，提取主版本号（如 1.20.1 -> 1.20）
        def get_main_version(version: str) -> str:
            parts = version.split('.')
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"
            return version
        
        # 解析GitHub版本，提取版本号和加载器
        version_info = []
        for gh_version in github_versions:
            if '-' in gh_version:
                v, l = gh_version.rsplit('-', 1)
                version_info.append((v, l, gh_version))
            else:
                version_info.append((gh_version, '', gh_version))
        
        main_game_version = get_main_version(game_version)
        
        # 优先匹配加载器和主版本号
        for v, l, full_version in version_info:
            if v == main_game_version and l == loaders:
                return full_version
        
        # 匹配主版本号（优先选择没有指定加载器的版本）
        for v, l, full_version in version_info:
            if v == main_game_version and l == "":
                return full_version
        # 如果没有无加载器版本，再选择有加载器的版本
        for v, l, full_version in version_info:
            if v == main_game_version:
                return full_version
        
        # 解析版本号为数字元组，用于比较
        def version_to_tuple(version: str) -> tuple:
            try:
                parts = version.split('.')
                return tuple(int(p) for p in parts if p.isdigit())
            except:
                return ()
        
        # 计算版本号之间的差异
        def version_diff(v1: str, v2: str) -> int:
            t1 = version_to_tuple(v1)
            t2 = version_to_tuple(v2)
            # 取较短的长度进行比较
            min_len = min(len(t1), len(t2))
            for i in range(min_len):
                if t1[i] != t2[i]:
                    return abs(t1[i] - t2[i])
            # 如果前面的部分相同，返回长度差异
            return abs(len(t1) - len(t2))
        
        # 按版本号差异排序，优先选择没有指定加载器的版本
        version_info.sort(key=lambda x: (version_diff(main_game_version, x[0]), 0 if x[1] == "" else 1))
        
        return version_info[0][2] if version_info else ""

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def _fetch_modrinth_version_files(self, modrinth_hashes: List[str]) -> Dict:
        """从Modrinth获取版本文件信息（带重试机制）"""
        url = "https://api.modrinth.com/v2/version_files"
        headers = {"Content-Type": "application/json"}
        data = {
            "hashes": modrinth_hashes,
            "algorithm": "sha1"
        }
        
        logging.info(f"从Modrinth API获取 {len(modrinth_hashes)} 个模组的信息...")
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def _fetch_modrinth_projects(self, project_ids: List[str]) -> List[Dict]:
        """从Modrinth获取项目信息（带重试机制）"""
        ids_str = ','.join([f'"{pid}"' for pid in project_ids])
        url = f"https://api.modrinth.com/v2/projects?ids=[{ids_str}]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def _get_mod_info_from_modrinth(self, modrinth_hashes: List[str]) -> Dict[str, Dict]:
        """从Modrinth获取模组信息"""
        if not modrinth_hashes:
            return {}

        try:
            # 步骤1：获取Hash与对应的版本信息（带重试）
            modrinth_version = self._fetch_modrinth_version_files(modrinth_hashes)

            logging.info(f"从Modrinth获取到 {len(modrinth_version)} 个本地模组的对应信息")

            if not modrinth_version:
                return {}

            # 提取project_id、game_versions和loaders
            project_ids = []
            hash_to_project = {}
            hash_to_game_version = {}
            hash_to_loaders = {}
            for hash_value, info in modrinth_version.items():
                project_id = info.get("project_id")
                if project_id:
                    project_ids.append(project_id)
                    hash_to_project[hash_value] = project_id
                game_versions = info.get("game_versions", [])
                if game_versions:
                    hash_to_game_version[hash_value] = game_versions[0]
                # 存储第一个加载器，或者空字符串
                loaders = info.get("loaders", [])
                hash_to_loaders[hash_value] = loaders[0] if loaders else ""

            if not project_ids:
                return {}

            # 步骤 2：获取工程信息（带重试）
            project_info = self._fetch_modrinth_projects(project_ids)

            # 构建项目信息映射
            project_map = {}
            for project in project_info:
                project_id = project.get("id")
                if project_id:
                    project_map[project_id] = {
                        "name": project.get("title"),
                        "slug": project.get("slug"),
                        "url": f"https://modrinth.com/mod/{project.get('slug')}",
                        "game_versions": project.get("game_versions", [])
                    }

            # 构建哈希到项目信息的映射
            result = {}
            for hash_value, project_id in hash_to_project.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id].copy()
                    # 优先使用从version_id获取的游戏版本
                    if hash_value in hash_to_game_version:
                        result[hash_value]["game_version"] = hash_to_game_version[hash_value]
                    elif result[hash_value].get("game_versions"):
                        result[hash_value]["game_version"] = result[hash_value]["game_versions"][0]
                    # 添加loaders字段，存储为字符串
                    result[hash_value]["loaders"] = hash_to_loaders.get(hash_value, "")

            return result
        except Exception as e:
            logging.error(f"从Modrinth获取模组信息失败: {e}")
            return {}

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def _fetch_curseforge_fingerprints(self, base_url: str, curseforge_hashes: List[str], api_key: str) -> Dict:
        """从CurseForge获取指纹匹配信息（带重试机制）"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        fingerprint_url = f"{base_url}/v1/fingerprints/432"
        data = {
            "fingerprints": [int(h) for h in curseforge_hashes]
        }
        
        logging.info(f"从CurseForge API ({base_url})获取 {len(curseforge_hashes)} 个模组的信息...")
        response = requests.post(fingerprint_url, json=data, headers=headers, timeout=30)
        
        # 检查API响应状态
        if response.status_code == 403:
            logging.error("CurseForge API密钥无效或已过期，请在设置中更新API密钥")
            raise requests.exceptions.HTTPError("API密钥无效", response=response)
        elif response.status_code == 429:
            logging.warning("CurseForge API请求频率超限")
            raise requests.exceptions.HTTPError("请求频率超限 (429)", response=response)
        
        response.raise_for_status()
        return response.json()

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def _fetch_curseforge_mods(self, base_url: str, project_ids: List[int], api_key: str) -> List[Dict]:
        """从CurseForge获取模组基本信息（带重试机制）"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        url = f"{base_url}/v1/mods"
        data = {"modIds": project_ids}
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        return response_data.get("data", [])

    def _get_mod_info_from_curseforge(self, curseforge_hashes: List[str]) -> Dict[str, Dict]:
        """从CurseForge获取模组信息"""
        if not curseforge_hashes:
            return {}

        try:
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                logging.warning("CurseForge API密钥未配置，请在设置中配置")
                return {}

            # 尝试多个API源
            base_urls = [
                "https://api.curseforge.com"
            ]

            # 步骤1：获取Hash与对应的工程ID
            exact_matches = []
            hash_to_project_id = {}
            hash_to_game_version = {}
            hash_to_loaders = {}
            project_map = {}
            
            # 尝试多个API源
            for base_url in base_urls:
                try:
                    # 使用带重试的方法获取指纹信息
                    response_data = self._fetch_curseforge_fingerprints(base_url, curseforge_hashes, api_key)
                    exact_matches = response_data.get("data", {}).get("exactMatches", [])
                    
                    # 调试：记录API响应详情
                    if not exact_matches:
                        logging.info(f"CurseForge API响应: {response_data}")
                        # 检查是否有部分匹配
                        partial_matches = response_data.get("data", {}).get("partialMatches", [])
                        if partial_matches:
                            logging.info(f"CurseForge找到 {len(partial_matches)} 个部分匹配")

                    logging.info(f"从CurseForge获取到 {len(exact_matches)} 个本地模组的对应信息")

                    if exact_matches:
                        # 提取project_id和构建fingerprint到project_id的映射
                        project_ids = []
                        for match in exact_matches:
                            project_id = match.get("id")
                            file_info = match.get("file", {})
                            fingerprint = str(file_info.get("fileFingerprint", ""))
                            if project_id and fingerprint:
                                project_ids.append(project_id)
                                hash_to_project_id[fingerprint] = project_id

                        if project_ids:
                            # 步骤2：从fingerprint响应中直接提取游戏版本和加载器信息
                            for match in exact_matches:
                                file_info = match.get("file", {})
                                fingerprint = str(file_info.get("fileFingerprint", ""))
                                game_versions = file_info.get("gameVersions", [])
                                
                                # 提取游戏版本
                                if game_versions:
                                    mc_version = None
                                    for v in game_versions:
                                        if isinstance(v, dict):
                                            if v.get("gameVersionName", "").lower() == "minecraft":
                                                mc_version = v.get("version")
                                                break
                                        elif isinstance(v, str):
                                            if re.match(r'^\d+\.\d+', v):
                                                mc_version = v
                                                break
                                    if mc_version:
                                        hash_to_game_version[fingerprint] = mc_version
                                        logging.debug(f"从CurseForge获取游戏版本: fingerprint={fingerprint[:20]}... -> {mc_version}")
                                
                                # 提取加载器信息
                                loaders = []
                                for v in game_versions:
                                    if isinstance(v, dict):
                                        game_version_name = v.get("gameVersionName", "").lower()
                                        if game_version_name in ["forge", "fabric", "quilt", "neoforge"]:
                                            loaders.append(game_version_name)
                                    elif isinstance(v, str):
                                        if v.lower() in ["forge", "fabric", "quilt", "neoforge"]:
                                            loaders.append(v.lower())
                                
                                # 存储第一个加载器，或者空字符串
                                if loaders:
                                    hash_to_loaders[fingerprint] = loaders[0]
                                else:
                                    hash_to_loaders[fingerprint] = ""

                            # 步骤3：获取工程基本信息（带重试）
                            project_info = self._fetch_curseforge_mods(base_url, project_ids, api_key)

                            # 构建项目信息映射
                            for project in project_info:
                                project_id = project.get("id")
                                if project_id:
                                    project_map[project_id] = {
                                        "name": project.get("name"),
                                        "slug": project.get("slug"),
                                        "url": f"https://www.curseforge.com/minecraft/mc-mods/{project.get('slug')}"
                                    }
                            break
                except requests.exceptions.HTTPError as e:
                    # 对于403和429错误，不需要重试其他API源
                    if "API密钥无效" in str(e) or "请求频率超限" in str(e):
                        return {}
                    logging.error(f"从CurseForge API ({base_url})获取模组信息失败: {e}")
                    continue
                except Exception as e:
                    logging.error(f"从CurseForge API ({base_url})获取模组信息失败: {e}")
                    continue

            if not exact_matches:
                return {}

            # 构建哈希到项目信息的映射
            result = {}
            for hash_value, project_id in hash_to_project_id.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id].copy()
                    if hash_value in hash_to_game_version:
                        result[hash_value]["game_version"] = hash_to_game_version[hash_value]
                    # 添加加载器信息
                    result[hash_value]["loaders"] = hash_to_loaders.get(hash_value, "")

            return result
        except Exception as e:
            logging.error(f"从CurseForge获取模组信息失败: {e}")
            return {}
    
    def run(self, mods_dir: Path, zip_paths: List[Path], community_dict_dir: str, extraction_progress_callback=None, stop_event=None) -> ExtractionResult:
        """执行完整的提取流程"""
        logging.info("语言数据聚合开始")
        
        # 从Mods中提取数据
        result = self.extract_from_mods(mods_dir, extraction_progress_callback, stop_event)
        
        # 从第三方汉化包中提取数据
        result.pack_chinese = self.extract_from_packs(zip_paths, result.master_english)
        
        # 提取Mod信息
        logging.debug("开始提取模组信息...")
        module_names = []
        curseforge_names = []
        modrinth_names = []
        
        mod_info_by_jar = {}
        curseforge_hashes = []
        modrinth_hashes = []
        hash_to_jar = {}
        
        # 获取含语言文件的JAR文件列表
        jars_with_language_files = set()
        for ns_info in result.namespace_info.values():
            # 从namespace_info中提取JAR文件名
            jar_name = ns_info.jar_name
            # 移除可能的格式后缀
            if " (both formats)" in jar_name:
                jar_name = jar_name.replace(" (both formats)", "")
            jars_with_language_files.add(jar_name)
        
        logging.debug(f"发现 {len(jars_with_language_files)} 个含语言文件的模组")
        
        if mods_dir.exists():
            jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar")
            total_jars = len(jars_with_language_files)
            
            # 过滤出需要处理的jar文件
            jars_to_process = []
            for jar_file in jar_files:
                if jar_file.name in jars_with_language_files:
                    jars_to_process.append(jar_file)
            
            fingerprint_cache = mod_scan_cache.ModFingerprintDiskCache()
            fingerprint_cache.load()
            cache_hits = 0
            cache_lock = threading.Lock()

            def _register_jar_mod_info(
                jar_path: Path,
                jar_name: str,
                mod_name: str,
                curseforge_hash: str,
                modrinth_hash: str,
                game_version: str,
                completed_counter: list,
            ) -> None:
                mod_info_by_jar[jar_name] = {
                    'name': mod_name,
                    'curseforge_hash': curseforge_hash,
                    'modrinth_hash': modrinth_hash,
                    'game_version': game_version
                }
                if curseforge_hash:
                    curseforge_hashes.append(curseforge_hash)
                    hash_to_jar[curseforge_hash] = jar_name
                if modrinth_hash:
                    modrinth_hashes.append(modrinth_hash)
                    hash_to_jar[modrinth_hash] = jar_name
                completed_counter[0] += 1
                if extraction_progress_callback:
                    extraction_progress_callback("fingerprint", completed_counter[0], total_jars)
                c = completed_counter[0]
                if c % 10 == 0 or c == total_jars:
                    logging.info(f"模组指纹进度 {c}/{total_jars}")

            completed = [0]

            def _process_one_jar(jf: Path):
                try:
                    with open(jf, 'rb') as f:
                        data = f.read()
                except OSError as e:
                    logging.warning("无法读取 JAR: %s — %s", jf, e)
                    return None
                modrinth_hash = hashlib.sha1(data).hexdigest()
                with cache_lock:
                    rec = fingerprint_cache.get(modrinth_hash)
                if rec is not None:
                    return (
                        True,
                        jf,
                        jf.name,
                        jf.stem,
                        rec["curseforge_hash"],
                        rec["modrinth_hash"],
                        "",
                    )
                jar_name, mod_name, curseforge_hash, mr, game_version = _jar_mod_fingerprints_and_meta(
                    jf, data, modrinth_hash
                )
                with cache_lock:
                    fingerprint_cache.put(modrinth_hash, {
                        'curseforge_hash': curseforge_hash,
                    })
                return (False, jf, jar_name, mod_name, curseforge_hash, mr, game_version)

            import os
            from concurrent.futures import ThreadPoolExecutor, as_completed

            max_workers = min(32, len(jars_to_process), max(1, (os.cpu_count() or 1) * 4))
            logging.debug(
                "模组指纹：%d 个线程；键为整包 SHA1，命中则跳过 Murmur 与 JAR 内元数据解析",
                max_workers,
            )

            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_jar = {executor.submit(_process_one_jar, jf): jf for jf in jars_to_process}
                    for future in as_completed(future_to_jar):
                        if stop_event and stop_event.is_set():
                            logging.info("收到停止信号，停止处理...")
                            executor.shutdown(wait=False, cancel_futures=True)
                            fingerprint_cache.save_if_dirty()
                            raise KeyboardInterrupt("用户取消了操作")
                        try:
                            row = future.result()
                            if row is None:
                                continue
                            hit, jf, jar_name, mod_name, cf_h, mr_h, gv = row
                            if hit:
                                cache_hits += 1
                            _register_jar_mod_info(jf, jar_name, mod_name, cf_h, mr_h, gv, completed)
                        except Exception as e:
                            logging.error(f"处理JAR文件时发生错误: {e}")
            finally:
                fingerprint_cache.save_if_dirty()

            if jars_to_process:
                logging.info(
                    "模组指纹缓存（SHA1）命中 %d / %d；未命中项已解析并写入 %s",
                    cache_hits,
                    len(jars_to_process),
                    mod_scan_cache.cache_path(),
                )

            # 平台查询与「扫描语言 / 指纹」分两阶段展示，避免状态栏长时间显示「扫描 Mods」
            if extraction_progress_callback:
                # 开始查询CurseForge
                extraction_progress_callback("repo_metadata", 0, 2)

            # 处理CurseForge查询
            curseforge_info = self._get_mod_info_from_curseforge(curseforge_hashes)

            # 处理Modrinth查询
            unmatched_modrinth_hashes = []
            for jar_name, info in mod_info_by_jar.items():
                if info['curseforge_hash'] not in curseforge_info and info['modrinth_hash']:
                    unmatched_modrinth_hashes.append(info['modrinth_hash'])

            modrinth_info = {}
            if unmatched_modrinth_hashes:
                if extraction_progress_callback:
                    # 开始查询Modrinth
                    extraction_progress_callback("repo_metadata", 1, 2)
                
                logging.info(f"CurseForge未匹配 {len(unmatched_modrinth_hashes)} 个模组，尝试从Modrinth获取...")
                modrinth_info = self._get_mod_info_from_modrinth(unmatched_modrinth_hashes)
            else:
                logging.info("所有模组已通过CurseForge匹配，无需调用Modrinth")

            # 完成查询
            if extraction_progress_callback:
                extraction_progress_callback("repo_metadata", 2, 2)
            
            # 整合信息
            for jar_name, info in mod_info_by_jar.items():
                mod_name = info['name']
                game_version = info.get('game_version', '')
                source = 'JAR'

                if info['curseforge_hash'] in curseforge_info:
                    cf_info = curseforge_info[info['curseforge_hash']]
                    mod_name = cf_info.get('name', mod_name)
                    if cf_info.get('game_version'):
                        game_version = cf_info.get('game_version', '')
                        source = 'CurseForge'

                if not game_version and info['modrinth_hash'] in modrinth_info:
                    mr_info = modrinth_info[info['modrinth_hash']]
                    mod_name = mr_info.get('name', mod_name)
                    if mr_info.get('game_version'):
                        game_version = mr_info.get('game_version', '')
                        source = 'Modrinth'

                # 获取加载器信息
                loaders_info = ""
                if source == 'CurseForge' and info['curseforge_hash'] in curseforge_info:
                    loaders_info = curseforge_info[info['curseforge_hash']].get('loaders', "")
                elif info['modrinth_hash'] in modrinth_info:
                    loaders_info = modrinth_info[info['modrinth_hash']].get('loaders', "")
                
                logging.debug(f"模组: {mod_name}, 版本: {game_version}, 加载器: {loaders_info}, 来源: {source}")

                module_names.append({
                    'name': mod_name,
                    'source': jar_name,
                    'game_version': game_version
                })

                # CurseForge信息
                if info['curseforge_hash']:
                    curseforge_entry = {
                        'curseforge_name': info['curseforge_hash'],
                        'source': jar_name,
                        'game_version': game_version,
                        'loaders': ""
                    }
                    if info['curseforge_hash'] in curseforge_info:
                        curseforge_entry['name'] = curseforge_info[info['curseforge_hash']].get('name')
                        curseforge_entry['slug'] = curseforge_info[info['curseforge_hash']].get('slug')
                        curseforge_entry['url'] = curseforge_info[info['curseforge_hash']].get('url')
                        curseforge_entry['loaders'] = curseforge_info[info['curseforge_hash']].get('loaders', "")
                    curseforge_names.append(curseforge_entry)

                # Modrinth信息
                if info['modrinth_hash']:
                    modrinth_entry = {
                        'modrinth_name': info['modrinth_hash'],
                        'source': jar_name,
                        'game_version': game_version,
                        'loaders': ""
                    }
                    if info['modrinth_hash'] in modrinth_info:
                        modrinth_entry['name'] = modrinth_info[info['modrinth_hash']].get('name')
                        modrinth_entry['slug'] = modrinth_info[info['modrinth_hash']].get('slug')
                        modrinth_entry['url'] = modrinth_info[info['modrinth_hash']].get('url')
                        modrinth_entry['loaders'] = modrinth_info[info['modrinth_hash']].get('loaders', "")
                    modrinth_names.append(modrinth_entry)
        
        result.module_names = module_names
        result.curseforge_names = curseforge_names
        result.modrinth_names = modrinth_names
        
        # 统计结果
        total_en = sum(len(d) for d in result.master_english.values())
        total_zh_internal = sum(len(d) for d in result.internal_chinese.values())
        
        logging.info(f"数据聚合完成: {len(result.master_english)}个命名空间, {total_en}条英文, {total_zh_internal}条自带中文, {len(module_names)}个模组")
        
        return result