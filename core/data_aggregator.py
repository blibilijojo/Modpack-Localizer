import zipfile
import json
import logging
from pathlib import Path
from collections import defaultdict
import re

from utils.file_utils import load_json
from utils.config_manager import load_user_dict
from utils.dictionary_searcher import DictionarySearcher

class DataAggregator:
    def __init__(self, mods_dir: Path, zip_paths: list[Path], community_dict_path: str):
        self.mods_dir = mods_dir
        self.zip_paths = zip_paths
        self.community_dict_path = community_dict_path

    def _is_actually_translated(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        if re.search(r'[\u4e00-\u9fa5]', text):
            return True
        if re.search(r'[a-zA-Z]', text):
            return False
        return True

    def run(self, progress_callback=None):
        master_english_dicts = defaultdict(dict)
        internal_chinese_dicts = defaultdict(dict)
        pack_chinese_dict = {}
        namespace_formats = {}
        namespace_to_jar = {}
        
        jar_files = sorted([p for p in self.mods_dir.glob("*.jar") if p.is_file()])
        total_jars = len(jar_files)

        for i, jar_path in enumerate(jar_files):
            if progress_callback:
                progress_callback(i + 1, total_jars)
            
            try:
                with zipfile.ZipFile(jar_path, 'r') as zf:
                    english_dict, chinese_dict, lang_format = self._process_lang_files_from_zip(zf)
                    
                    for namespace, content in english_dict.items():
                        master_english_dicts[namespace].update(content)
                        namespace_to_jar[namespace] = jar_path.name
                        if lang_format.get(namespace):
                            namespace_formats[namespace] = lang_format[namespace]
                            
                    for namespace, content in chinese_dict.items():
                        internal_chinese_dicts[namespace].update(content)

            except (zipfile.BadZipFile, FileNotFoundError) as e:
                logging.error(f"处理文件失败 {jar_path.name}: {e}")

        for zip_path in self.zip_paths:
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    _, chinese_dict, _ = self._process_lang_files_from_zip(zf)
                    for namespace, content in chinese_dict.items():
                        pack_chinese_dict.update(content)
            except (zipfile.BadZipFile, FileNotFoundError) as e:
                logging.error(f"处理汉化包失败 {zip_path.name}: {e}")

        user_dictionary = load_user_dict()
        
        community_dict_by_key = {}
        community_dict_by_origin = defaultdict(list)
        searcher = DictionarySearcher(self.community_dict_path)
        if searcher.is_available():
            logging.info("  - 正在从社区词典加载...")
            all_entries = searcher.get_all_entries()
            logging.info(f"  - 成功从社区词典加载 {len(all_entries)} 条数据。")
            for entry in all_entries:
                key = entry.get('KEY')
                origin = entry.get('ORIGIN_NAME')
                trans = entry.get('TRANS_NAME')
                version = entry.get('VERSION', '0.0.0')

                if key and trans:
                    community_dict_by_key[key] = trans
                if origin and trans:
                    community_dict_by_origin[origin].append({'trans': trans, 'version': version})
            searcher.close()

        return (
            user_dictionary, 
            community_dict_by_key, 
            dict(community_dict_by_origin), 
            dict(master_english_dicts), 
            dict(internal_chinese_dicts), 
            pack_chinese_dict, 
            namespace_formats, 
            namespace_to_jar
        )

    def _process_lang_files_from_zip(self, zip_file: zipfile.ZipFile):
        english_files = defaultdict(dict)
        chinese_files = defaultdict(dict)
        namespace_formats = {}
        
        for file_info in zip_file.infolist():
            if file_info.is_dir():
                continue

            file_path = Path(file_info.filename)
            
            if "assets" not in file_path.parts or "lang" not in file_path.parts:
                continue

            is_en = file_path.name.lower() in ("en_us.json", "en_us.lang")
            is_zh = file_path.name.lower() in ("zh_cn.json", "zh_cn.lang")
            
            if not (is_en or is_zh):
                continue
            
            try:
                namespace = file_path.parts[file_path.parts.index("assets") + 1]
                content = zip_file.read(file_info.filename).decode('utf-8', errors='replace')
                
                if file_path.suffix == '.json':
                    data = json.loads(content)
                    lang_format = 'json'
                elif file_path.suffix == '.lang':
                    data = dict(line.strip().split('=', 1) for line in content.splitlines() if '=' in line and not line.startswith('#'))
                    lang_format = 'lang'
                else:
                    continue

                if is_en:
                    english_files[namespace].update(data)
                    namespace_formats[namespace] = lang_format
                
                if is_zh:
                    for key, value in data.items():
                        if self._is_actually_translated(value):
                            chinese_files[namespace][key] = value

            except (json.JSONDecodeError, ValueError) as e:
                logging.warning(f"解析语言文件失败 {file_info.filename}: {e}")
                    
        return english_files, chinese_files, namespace_formats