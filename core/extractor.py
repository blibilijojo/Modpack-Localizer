import zipfile
import json
import logging
import sqlite3
import re
import hashlib
import requests
import concurrent.futures
import threading
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

    def _compute_modrinth_hash(self, file_path: Path) -> str:
        """计算Modrinth哈希值 (SHA1)"""
        sha1_hash = hashlib.sha1()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha1_hash.update(byte_block)
            return sha1_hash.hexdigest()
        except Exception as e:
            logging.error(f"计算Modrinth哈希失败: {e}")
            return ""
    
    def _compute_curseforge_hash(self, file_path: Path) -> int:
        """计算CurseForge哈希值 (MurmurHash2)"""
        try:
            data = []
            with open(file_path, "rb") as f:
                for byte in f.read():
                    if byte not in (9, 10, 13, 32):  # 跳过制表符、换行符、回车符和空格
                        data.append(byte)
            
            length = len(data)
            h = 1 ^ length  # 1 是种子
            i = 0
            
            while i + 3 < length:
                k = data[i] | (data[i+1] << 8) | (data[i+2] << 16) | (data[i+3] << 24)
                k = (k * 0x5BD1E995) & 0xFFFFFFFF
                k = k ^ (k >> 24)
                k = (k * 0x5BD1E995) & 0xFFFFFFFF
                h = (h * 0x5BD1E995) & 0xFFFFFFFF
                h = h ^ k
                i += 4
            
            # 处理剩余字节
            if i < length:
                if length - i == 3:
                    h = h ^ (data[i] | (data[i+1] << 8) | (data[i+2] << 16))
                    h = (h * 0x5BD1E995) & 0xFFFFFFFF
                elif length - i == 2:
                    h = h ^ (data[i] | (data[i+1] << 8))
                    h = (h * 0x5BD1E995) & 0xFFFFFFFF
                elif length - i == 1:
                    h = h ^ data[i]
                    h = (h * 0x5BD1E995) & 0xFFFFFFFF
            
            h = h ^ (h >> 13)
            h = (h * 0x5BD1E995) & 0xFFFFFFFF
            h = h ^ (h >> 15)
            
            return h
        except Exception as e:
            logging.error(f"计算CurseForge哈希失败: {e}")
            return 0
    
    def _extract_mod_info(self, jar_file: Path) -> tuple[str, str, str]:
        """从JAR文件中提取Mod信息"""
        mod_name = ""
        curseforge_hash = ""
        modrinth_hash = ""
        
        try:
            # 计算哈希值
            modrinth_hash = self._compute_modrinth_hash(jar_file)
            curseforge_hash = str(self._compute_curseforge_hash(jar_file))
            
            # 提取Mod名称
            with zipfile.ZipFile(jar_file, 'r') as zf:
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
                                elif isinstance(data, dict) and 'modList' in data:
                                    mod_list = data['modList']
                                    if isinstance(mod_list, list) and mod_list:
                                        mod_info = mod_list[0]
                                        if 'name' in mod_info:
                                            mod_name = mod_info['name']
                    except Exception as e:
                        logging.debug(f"读取mcmod.info失败: {e}")
                
                # 尝试从fabric.mod.json提取
                if not mod_name and 'fabric.mod.json' in zf.namelist():
                    try:
                        with zf.open('fabric.mod.json') as f:
                            content = f.read().decode('utf-8-sig')
                            if is_json_content(content):
                                data = json.loads(content)
                                if 'name' in data:
                                    mod_name = data['name']
                    except Exception as e:
                        logging.debug(f"读取fabric.mod.json失败: {e}")
                
                # 尝试从mods.toml提取
                if not mod_name and 'META-INF/mods.toml' in zf.namelist():
                    try:
                        with zf.open('META-INF/mods.toml') as f:
                            content = f.read().decode('utf-8-sig')
                            # 简单解析toml文件
                            for line in content.split('\n'):
                                line = line.strip()
                                if line.startswith('displayName') or line.startswith('name'):
                                    if '=' in line:
                                        value = line.split('=', 1)[1].strip()
                                        # 去除引号
                                        value = value.strip('"'"'"'')
                                        mod_name = value
                                        break
                    except Exception as e:
                        logging.debug(f"读取mods.toml失败: {e}")
                
                # 如果没有找到名称，使用文件名
                if not mod_name:
                    mod_name = jar_file.stem
                    # 移除常见的后缀
                    for suffix in ['.jar', '.zip', '.litemod']:
                        if mod_name.endswith(suffix):
                            mod_name = mod_name[:-len(suffix)]
                    # 移除.disabled和.old后缀
                    mod_name = mod_name.replace('.disabled', '').replace('.old', '')
                    
        except Exception as e:
            logging.error(f"提取Mod信息失败: {e}")
            # 如果失败，使用文件名作为mod名称
            mod_name = jar_file.stem
        
        return mod_name, curseforge_hash, modrinth_hash
    
    def _get_mod_info_from_modrinth(self, modrinth_hashes: List[str]) -> Dict[str, Dict]:
        """从Modrinth获取模组信息"""
        if not modrinth_hashes:
            return {}
        
        try:
            # 步骤1：获取Hash与对应的工程ID
            url = "https://api.modrinth.com/v2/version_files"
            headers = {"Content-Type": "application/json"}
            data = {
                "hashes": modrinth_hashes,
                "algorithm": "sha1"
            }
            
            logging.info(f"从Modrinth API获取 {len(modrinth_hashes)} 个模组的信息...")
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            modrinth_version = response.json()
            
            logging.info(f"从Modrinth获取到 {len(modrinth_version)} 个本地模组的对应信息")
            
            if not modrinth_version:
                return {}
            
            # 提取project_id
            project_ids = []
            hash_to_project = {}
            for hash_value, info in modrinth_version.items():
                project_id = info.get("project_id")
                if project_id:
                    project_ids.append(project_id)
                    hash_to_project[hash_value] = project_id
            
            if not project_ids:
                return {}
            
            # 步骤2：获取工程信息
            url = f"https://api.modrinth.com/v2/projects?ids=[{','.join([f'\"{pid}\"' for pid in project_ids])}]"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            project_info = response.json()
            
            # 构建项目信息映射
            project_map = {}
            for project in project_info:
                project_id = project.get("id")
                if project_id:
                    project_map[project_id] = {
                        "name": project.get("name"),
                        "slug": project.get("slug"),
                        "url": f"https://modrinth.com/mod/{project.get('slug')}"
                    }
            
            # 构建哈希到项目信息的映射
            result = {}
            for hash_value, project_id in hash_to_project.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id]
            
            return result
        except Exception as e:
            logging.error(f"从Modrinth获取模组信息失败: {e}")
            return {}
    
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

            # 步骤1：获取Hash与对应的工程ID
            url = "https://api.curseforge.com/v1/fingerprints/432"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key
            }
            data = {
                "fingerprints": [int(h) for h in curseforge_hashes]
            }
            
            logging.info(f"从CurseForge API获取 {len(curseforge_hashes)} 个模组的信息...")
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            exact_matches = response_data.get("data", {}).get("exactMatches", [])
            
            logging.info(f"从CurseForge获取到 {len(exact_matches)} 个本地模组的对应信息")
            
            if not exact_matches:
                return {}
            
            # 提取project_id
            project_ids = []
            hash_to_project = {}
            for match in exact_matches:
                project_id = match.get("id")
                fingerprint = str(match.get("file", {}).get("fileFingerprint"))
                if project_id and fingerprint:
                    project_ids.append(project_id)
                    hash_to_project[fingerprint] = project_id
            
            if not project_ids:
                return {}
            
            # 步骤2：获取工程信息
            url = "https://api.curseforge.com/v1/mods"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key
            }
            data = {
                "modIds": project_ids
            }
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            project_info = response_data.get("data", [])
            
            # 构建项目信息映射
            project_map = {}
            for project in project_info:
                project_id = project.get("id")
                if project_id:
                    project_map[project_id] = {
                        "name": project.get("name"),
                        "slug": project.get("slug"),
                        "url": f"https://www.curseforge.com/minecraft/mc-mods/{project.get('slug')}"
                    }
            
            # 构建哈希到项目信息的映射
            result = {}
            for hash_value, project_id in hash_to_project.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id]
            
            return result
        except Exception as e:
            logging.error(f"从CurseForge获取模组信息失败: {e}")
            return {}
    
    def run(self, mods_dir: Path, zip_paths: List[Path], community_dict_dir: str, progress_update_callback=None) -> ExtractionResult:
        """执行完整的提取流程"""
        logging.info("--- 阶段 1: 开始聚合所有语言数据 ---")
        
        # 从Mods中提取数据
        result = self.extract_from_mods(mods_dir, progress_update_callback)
        
        # 从第三方汉化包中提取数据
        result.pack_chinese = self.extract_from_packs(zip_paths, result.master_english)
        
        # 提取Mod信息
        logging.info("开始提取模组信息...")
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
        
        logging.info(f"发现 {len(jars_with_language_files)} 个含语言文件的模组")
        
        if mods_dir.exists():
            jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar")
            total_jars = len(jars_with_language_files)
            processed_count = 0
            processed_count_lock = threading.Lock()
            mod_info_lock = threading.Lock()
            
            # 过滤出需要处理的jar文件
            jars_to_process = []
            for jar_file in jar_files:
                if jar_file.name in jars_with_language_files:
                    jars_to_process.append(jar_file)
            
            # 定义处理单个jar文件的函数
            def process_jar(jar_file):
                nonlocal processed_count
                jar_name = jar_file.name
                
                # 提取模组信息
                mod_name, curseforge_hash, modrinth_hash = self._extract_mod_info(jar_file)
                
                # 线程安全地更新共享数据
                with mod_info_lock:
                    # 存储初步信息
                    mod_info_by_jar[jar_name] = {
                        'name': mod_name,
                        'curseforge_hash': curseforge_hash,
                        'modrinth_hash': modrinth_hash
                    }
                    
                    # 收集哈希值用于API查询
                    if curseforge_hash:
                        curseforge_hashes.append(curseforge_hash)
                        hash_to_jar[curseforge_hash] = jar_name
                    if modrinth_hash:
                        modrinth_hashes.append(modrinth_hash)
                        hash_to_jar[modrinth_hash] = jar_name
                
                # 更新处理计数
                with processed_count_lock:
                    nonlocal processed_count
                    processed_count += 1
                    if progress_update_callback:
                        progress_update_callback(processed_count, total_jars)
                    
                    # 每处理10个文件记录一次日志
                    if processed_count % 10 == 0 or processed_count == total_jars:
                        logging.info(f"已处理 {processed_count}/{total_jars} 个含语言文件的模组")
            
            # 使用线程池处理JAR文件，设置32个线程
            max_workers = 32
            logging.info(f"使用线程池处理，最大线程数: {max_workers}")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务到线程池
                futures = [executor.submit(process_jar, jar_file) for jar_file in jars_to_process]
                
                # 等待所有任务完成
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"处理JAR文件时发生错误: {e}")
            
            # 从CurseForge获取信息
            curseforge_info = self._get_mod_info_from_curseforge(curseforge_hashes)
            
            # 收集未被CurseForge处理的模组的Modrinth哈希
            unprocessed_modrinth_hashes = []
            for jar_name, info in mod_info_by_jar.items():
                if info['curseforge_hash'] not in curseforge_info and info['modrinth_hash']:
                    unprocessed_modrinth_hashes.append(info['modrinth_hash'])
            
            # 从Modrinth获取未被CurseForge处理的模组信息
            modrinth_info = self._get_mod_info_from_modrinth(unprocessed_modrinth_hashes)
            
            # 整合信息
            for jar_name, info in mod_info_by_jar.items():
                # 模组名称优先使用API获取的名称
                mod_name = info['name']
                if info['curseforge_hash'] in curseforge_info:
                    mod_name = curseforge_info[info['curseforge_hash']].get('name', mod_name)
                elif info['modrinth_hash'] in modrinth_info:
                    mod_name = modrinth_info[info['modrinth_hash']].get('name', mod_name)
                
                module_names.append({
                    'name': mod_name,
                    'source': jar_name
                })
                
                # CurseForge信息
                if info['curseforge_hash']:
                    curseforge_entry = {
                        'curseforge_name': info['curseforge_hash'],
                        'source': jar_name
                    }
                    if info['curseforge_hash'] in curseforge_info:
                        curseforge_entry['name'] = curseforge_info[info['curseforge_hash']].get('name')
                        curseforge_entry['slug'] = curseforge_info[info['curseforge_hash']].get('slug')
                        curseforge_entry['url'] = curseforge_info[info['curseforge_hash']].get('url')
                    curseforge_names.append(curseforge_entry)
                
                # Modrinth信息
                if info['modrinth_hash']:
                    modrinth_entry = {
                        'modrinth_name': info['modrinth_hash'],
                        'source': jar_name
                    }
                    if info['modrinth_hash'] in modrinth_info:
                        modrinth_entry['name'] = modrinth_info[info['modrinth_hash']].get('name')
                        modrinth_entry['slug'] = modrinth_info[info['modrinth_hash']].get('slug')
                        modrinth_entry['url'] = modrinth_info[info['modrinth_hash']].get('url')
                    modrinth_names.append(modrinth_entry)
        
        result.module_names = module_names
        result.curseforge_names = curseforge_names
        result.modrinth_names = modrinth_names
        
        logging.info(f"模组信息提取完成。共提取 {len(module_names)} 个模组名称, {len(curseforge_names)} 个CurseForge哈希, {len(modrinth_names)} 个Modrinth哈希。")
        
        # 统计结果
        total_en = sum(len(d) for d in result.master_english.values())
        total_zh_internal = sum(len(d) for d in result.internal_chinese.values())
        
        logging.info(f"数据聚合完成。共发现 {len(result.master_english)} 个命名空间, {total_en} 条英文原文, {total_zh_internal} 条模组自带中文。")
        
        return result