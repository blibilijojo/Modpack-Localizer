from __future__ import annotations
from typing import Tuple, List, Dict, Optional
import re
import os
import json
import logging
from abc import ABC, abstractmethod
from io import BytesIO, StringIO
from pathlib import Path
import ftb_snbt_lib as slib
from ftb_snbt_lib import tag

def read_file(file: BytesIO) -> str:
    try:
        return StringIO(file.getvalue().decode('utf-8-sig')).read()
    except UnicodeDecodeError:
        return StringIO(file.getvalue().decode('ISO-8859-1')).read()

def escape_text(text: str) -> str:
    for match, seq in ((r'%', r'%%'), (r'"', r'\"')):
        text = text.replace(match, seq)
    return text

def filter_text(text: str) -> bool:
    if not text:
        return False
    if text.startswith("{") and text.endswith("}"):
        return False
    if text.startswith("[") and text.endswith("]"):
        return False
    return True

def safe_name(name: str) -> str:
    """生成安全的文件名"""
    return re.compile(r'\W+').sub("", name.lower().replace(" ", "_"))

def generate_language_key(modpack_name: str, quest_name: str, element_path: str) -> str:
    """生成规范的语言键"""
    # 清理和规范化各部分
    modpack_part = safe_name(modpack_name)
    quest_part = safe_name(quest_name)
    element_part = safe_name(element_path)
    
    # 构建语言键
    return f"{modpack_part}.{quest_part}.{element_part}"

def detect_key_conflicts(keys: List[str]) -> List[str]:
    """检测语言键冲突"""
    key_counts = {}
    conflicts = []
    
    for key in keys:
        if key in key_counts:
            key_counts[key] += 1
            if key_counts[key] == 2:
                conflicts.append(key)
        else:
            key_counts[key] = 1
    
    return conflicts

def detect_ftb_version(root: Path) -> bool:
    """检测 FTB Quests 是否为 1.21+ 版本结构"""
    components: List[str] = [c.as_posix() for c in root.components()]
    
    for i in range(len(components) - 1):
        if components[i].lower() == "quests" and components[i+1].lower() == "lang":
            return True

    candidates = [
        root / "config" / "ftbquests" / "quests" / "lang",
        root / "ftbquests" / "quests" / "lang",
        root / "quests" / "lang",
        root / "lang",
    ]

    for path in candidates:
        if path.exists() and path.is_dir():
            return True
    return False

def is_allowed_dir(entry: Path, root: Path, is_ftb_1_21: bool, source_lang: str) -> bool:
    """检查目录是否应该被处理"""
    if not entry.is_dir():
        return True
    if entry == root:
        return True

    name = entry.name.lower()
    path_str = entry.as_posix()

    # FTB Quests 逻辑
    if "ftbquests" in path_str.lower() or "quests" in path_str.lower():
        if name in ["ftbquests", "quests", "config"]:
            return True

        if is_ftb_1_21:
            if name == "lang":
                return True
            comps: List[str] = [c.as_posix() for c in entry.components()]
            has_lang = any(c.lower() == "lang" for c in comps)
            has_source = any(c.lower() == source_lang for c in comps)
            return has_lang and has_source
        else:
            return True

    # 通用逻辑
    allowed_roots = ["resources", "mods", "kubejs", "assets", "lang"]
    try:
        rel = entry.relative_to(root)
        if rel.parts:
            first_name = rel.parts[0].lower()
            if first_name == "config":
                return len(rel.parts) == 1  # 仅允许 config 根目录
            if first_name in allowed_roots:
                return True
    except ValueError:
        pass
    
    root_name = root.name.lower()
    return root_name in allowed_roots

def should_process_file(path: Path, source_lang: str, is_ftb_1_21: bool) -> bool:
    """检查文件是否应该被处理"""
    ext = path.suffix.lower()

    match ext:
        case ".snbt":
            if not is_ftb_1_21:
                return True

            components: List[str] = [c.as_posix() for c in path.components()]
            if (idx := next((i for i, c in enumerate(components) if c.lower() == "lang"), None)) is not None:
                if idx + 1 < len(components):
                    next_comp = components[idx + 1]
                    if next_comp == path.name:
                        return path.stem.lower() == source_lang
                    return next_comp.lower() == source_lang
            return False
        case ".json":
            return source_lang in path.name.lower()
        case ".lang":
            return source_lang in path.name.lower()
        case _:
            return False

class ConversionManager:
    def __init__(self, converter: BaseQuestConverter):
        self.converter = converter
        self.logger = logging.getLogger(self.__class__.__qualname__)
        
    def __call__(self, modpack_name: str, quest_files: List[BytesIO], lang_dict: Dict) -> Tuple[List, Dict]:
        """执行任务转换"""
        try:
            self.logger.info(f"开始转换任务，模组包名称: {modpack_name}")
            self.logger.info(f"待处理的任务文件数量: {len(quest_files)}")
            
            # 记录开始时间
            import time
            start_time = time.time()
            
            quest_arr, lang_dict = self.converter.convert(modpack_name, quest_files, lang_dict)
            
            # 计算处理时间
            elapsed_time = time.time() - start_time
            self.logger.info(f"任务转换完成，耗时: {elapsed_time:.2f} 秒")
            self.logger.info(f"生成的语言键数量: {len(lang_dict)}")
            
            return quest_arr, lang_dict
        except Exception as e:
            self.logger.error(f"任务转换过程中发生错误: {e}", exc_info=True)
            # 返回空结果，避免影响后续流程
            return [], lang_dict

class BaseQuestConverter(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__qualname__)

    @abstractmethod
    def read(self, quest: BytesIO) -> Tuple[str, Dict]:
        pass

    def convert(self, modpack_name: str, quest_files: List[BytesIO], lang_dict: Dict) -> Tuple[List, Dict]:
        """转换任务文件并生成语言键"""
        modpack_name = safe_name(modpack_name)
        quest_arr = [self.read(quest) for quest in quest_files]
        
        # 收集所有生成的键，用于检测冲突
        all_keys = []
        
        for quest_name, quest_data in quest_arr:
            quest_key = f"{modpack_name}.{quest_name}"
            self.logger.info("Converting quest (%s)", quest_name)
            self._convert(quest_key, quest_data, lang_dict)
            
            # 收集生成的键
            for key in lang_dict.keys():
                all_keys.append(key)
        
        # 检测键冲突
        conflicts = detect_key_conflicts(all_keys)
        if conflicts:
            self.logger.warning(f"检测到 {len(conflicts)} 个语言键冲突: {conflicts}")
        
        self.logger.info("Converted %s quests", len(quest_arr))
        return quest_arr, lang_dict

    @abstractmethod
    def _convert(self, quest_key: str, quest_data: Dict, lang_dict: Dict):
        pass

class FTBQuestConverter(BaseQuestConverter):
    def read(self, quest: BytesIO) -> Tuple[str, tag.Compound]:
        quest_name = safe_name(os.path.splitext(quest.name)[0])
        quest_data = slib.loads(read_file(quest))
        assert isinstance(quest_data, tag.Compound), "The quest data must be a Compound tag object"
        return quest_name, quest_data
    
    def _convert(self, quest_key: str, quest_data: tag.Compound, lang_dict: Dict):
        # 扩展可翻译的键列表
        TRANSLATABLE_FTB_KEYS = {"title", "subtitle", "description", "text", "name", "hint", "rewardText"}
        
        for element in list(quest_data.keys()):
            try:
                value = quest_data[element]
                
                # 递归处理复合标签
                if isinstance(value, tag.Compound):
                    self._convert(f"{quest_key}.{element}", value, lang_dict)
                
                # 处理复合标签列表
                elif isinstance(value, tag.List) and value.subtype and issubclass(value.subtype, tag.Compound):
                    for idx in range(len(value)):
                        try:
                            self._convert(f"{quest_key}.{element}{idx}", value[idx], lang_dict)
                        except Exception as e:
                            self.logger.warning(f"处理列表元素 {idx} 时出错: {e}")
                
                # 处理可翻译的字符串
                if element in TRANSLATABLE_FTB_KEYS:
                    # 单个字符串
                    if isinstance(value, tag.String):
                        text = str(value)
                        if filter_text(text):
                            lang_key = f"{quest_key}.{element}"
                            lang_dict[lang_key] = escape_text(text)
                            quest_data[element] = tag.String(f"{{{lang_key}}}")
                    
                    # 字符串列表
                    elif isinstance(value, tag.List) and value.subtype and issubclass(value.subtype, tag.String):
                        indices_to_process = [
                            i for i, item in enumerate(value) 
                            if isinstance(item, tag.String) and filter_text(str(item))
                        ]
                        for lang_idx, data_idx in enumerate(indices_to_process):
                            try:
                                lang_key = f"{quest_key}.{element}{lang_idx}"
                                original_text = str(value[data_idx])
                                lang_dict[lang_key] = escape_text(original_text)
                                value[data_idx] = tag.String(f"{{{lang_key}}}")
                            except Exception as e:
                                self.logger.warning(f"处理字符串列表元素 {data_idx} 时出错: {e}")
            except Exception as e:
                self.logger.warning(f"处理元素 {element} 时出错: {e}")
    
    def convert(self, modpack_name: str, quest_files: List[BytesIO], lang_dict: Dict) -> Tuple[List, Dict]:
        """转换任务文件并生成语言键"""
        modpack_name = safe_name(modpack_name)
        quest_arr = [self.read(quest) for quest in quest_files]
        
        # 收集所有生成的键，用于检测冲突
        all_keys = []
        
        for quest_name, quest_data in quest_arr:
            quest_key = f"{modpack_name}.{quest_name}"
            self.logger.info("Converting quest (%s)", quest_name)
            self._convert(quest_key, quest_data, lang_dict)
            
            # 收集生成的键
            for key in lang_dict.keys():
                all_keys.append(key)
        
        # 检测键冲突
        conflicts = detect_key_conflicts(all_keys)
        if conflicts:
            self.logger.warning(f"检测到 {len(conflicts)} 个语言键冲突: {conflicts}")
        
        self.logger.info("Converted %s quests", len(quest_arr))
        return quest_arr, lang_dict

class BQMQuestConverter(BaseQuestConverter):
    def read(self, quest: BytesIO) -> Tuple[str, Dict]:
        quest_name = safe_name(os.path.splitext(quest.name)[0])
        quest_data = json.loads(read_file(quest))
        assert isinstance(quest_data, dict), "The quest data must be a dictionary"
        return quest_name, quest_data

    def infer_version(self, quest_data: Dict) -> int:
        if 'questDatabase:9' in quest_data:
            return 1
        if 'questDatabase' in quest_data:
            if 'properties' in quest_data['questDatabase'][0]:
                return 3
            else:
                return 2
        raise ValueError("The quest data is not a valid BQM format")
    
    def _convert(self, quest_key: str, quest_data: Dict, lang_dict: Dict):
        quest_version = self.infer_version(quest_data)
        if quest_version == 1:
            self._convert_v1(quest_key, quest_data, lang_dict)
        elif quest_version == 2:
            self._convert_v2(quest_key, quest_data, lang_dict)
        elif quest_version == 3:
            self._convert_v3(quest_key, quest_data, lang_dict)
        else:
            raise ValueError("Unknown quest version")
    
    def _convert_v1(self, quest_key: str, quest_data: Dict, lang_dict: Dict):        
        quest_db = quest_data['questDatabase:9']
        for quest in quest_db.values():
            idx = quest.get('questID:3')
            properties = quest['properties:10']['betterquesting:10']
            self._update(properties, lang_dict, f'{quest_key}.quests{idx}', 'name:8', 'desc:8')
        questline_db = quest_data['questLines:9']
        for questline in questline_db.values():
            idx = questline.get('lineID:3')
            properties = questline['properties:10']['betterquesting:10']
            self._update(properties, lang_dict, f'{quest_key}.questlines{idx}', 'name:8', 'desc:8')

    def _convert_v2(self, quest_key: str, quest_data: Dict, lang_dict: Dict):
        quest_db = quest_data['questDatabase']
        for quest in quest_db:
            idx = quest.get('questID')
            properties = quest
            self._update(properties, lang_dict, f'{quest_key}.quests{idx}', 'name', 'description')
        questline_db = quest_data['questLines']
        for idx, questline in enumerate(questline_db):
            properties = questline
            self._update(properties, lang_dict, f'{quest_key}.questlines{idx}', 'name', 'description')

    def _convert_v3(self, quest_key: str, quest_data: Dict, lang_dict: Dict):
        quest_db = quest_data['questDatabase']
        for quest in quest_db:
            idx = quest.get('questID')
            properties = quest['properties']['betterquesting']
            self._update(properties, lang_dict, f'{quest_key}.quests{idx}', 'name', 'desc')
        questline_db = quest_data['questLines']
        for questline in questline_db:
            idx = questline.get('lineID')
            properties = questline['properties']['betterquesting']
            self._update(properties, lang_dict, f'{quest_key}.questlines{idx}', 'name', 'desc')

    def _update(self, properties: Dict, lang_dict: Dict, quest_key_base: str, name_key: str, desc_key: str):
        name = properties.get(name_key) or 'No Name'
        desc = properties.get(desc_key) or 'No Description'
        lang_dict[f"{quest_key_base}.name"] = name
        lang_dict[f"{quest_key_base}.desc"] = desc
        properties[name_key] = f"{quest_key_base}.name"
        properties[desc_key] = f"{quest_key_base}.desc"


class LANGConverter:
    def convert_lang_to_json(self, data: str) -> Dict:
        output = {}
        for line in data.splitlines():
            if line.startswith("#") or not line:
                continue
            match = re.compile('(.*)=(.*)').match(line)
            if match:
                key, value = match.groups()
                output[key] = value.replace("%n", r"\n")
        return output

    def convert_json_to_lang(self, data: Dict) -> str:
        output = ""
        for key, value in data.items():
            value = str(value).replace(r"\n", "%n")
            output += f"{key}={value}\n"
        return output
