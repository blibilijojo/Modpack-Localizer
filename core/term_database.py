import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Union, Set, Type, Callable
from datetime import datetime
import re
import csv
import sys

# 处理PyInstaller单文件打包时的路径问题
def get_app_data_path():
    if getattr(sys, 'frozen', False):
        # 单文件打包模式，使用可执行文件所在目录
        return Path(sys.executable).parent
    else:
        # 开发模式，使用当前工作目录
        return Path.cwd()

APP_DATA_PATH = get_app_data_path()
TERM_DATABASE_PATH = APP_DATA_PATH / "term_database.json"

# 导入模式枚举
class ImportMode:
    FULL = "full"  # 全量导入，覆盖现有术语库
    INCREMENTAL = "incremental"  # 增量导入，只添加新术语或更新现有术语

# 导入结果数据结构
class ImportResult:
    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.updated_count = 0
        self.skipped_count = 0
        self.errors = []
        self.warnings = []

# 格式处理器基类
class FormatProcessor:
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("必须实现process方法")

# JSON格式处理器
class JsonFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 支持两种格式：直接是术语列表，或者包含术语列表的对象
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "terms" in data:
                return data["terms"]
            else:
                raise ValueError("JSON文件格式无效，必须是术语列表或包含terms字段的对象")
        except Exception as e:
            raise ValueError(f"处理JSON文件失败: {str(e)}")

# CSV格式处理器
class CsvFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            terms = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 转换CSV行到术语格式
                    term = {
                        "original": row.get("original", "").strip(),
                        "translation": row.get("translation", "").strip().split("|"),
                        "comment": row.get("comment", "").strip()
                    }
                    terms.append(term)
            return terms
        except Exception as e:
            raise ValueError(f"处理CSV文件失败: {str(e)}")

# TXT格式处理器（每行一个术语对，格式：原文=译文）
class TxtFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            terms = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    if "=" in line:
                        original, translation = line.split("=", 1)
                        term = {
                            "original": original.strip(),
                            "translation": [translation.strip()],
                            "comment": ""
                        }
                        terms.append(term)
                    else:
                        logging.warning(f"TXT文件第{line_num}行格式无效，跳过: {line}")
            return terms
        except Exception as e:
            raise ValueError(f"处理TXT文件失败: {str(e)}")

# 术语验证器
class TermValidator:
    def __init__(self):
        self.required_fields = ["original", "translation"]
    
    def validate(self, term: Dict[str, Any]) -> tuple[bool, List[str]]:
        errors = []
        
        # 检查必填字段
        for field in self.required_fields:
            if field not in term or not term[field]:
                errors.append(f"缺少必填字段: {field}")
        
        # 验证original字段
        if "original" in term:
            original = term["original"]
            if not isinstance(original, str) or len(original.strip()) == 0:
                errors.append("原文术语不能为空字符串")
        
        # 验证translation字段
        if "translation" in term:
            translation = term["translation"]
            if isinstance(translation, str):
                if len(translation.strip()) == 0:
                    errors.append("译文不能为空字符串")
                term["translation"] = [translation.strip()]  # 转换为列表格式
            elif isinstance(translation, list):
                if len(translation) == 0:
                    errors.append("译文列表不能为空")
                else:
                    # 清理译文列表中的空字符串
                    cleaned_translations = [t.strip() for t in translation if t.strip()]
                    if len(cleaned_translations) == 0:
                        errors.append("译文列表中没有有效译文")
                    term["translation"] = cleaned_translations
            else:
                errors.append("译文必须是字符串或列表")
        
        return len(errors) == 0, errors

# 格式处理器注册表
class FormatProcessorRegistry:
    def __init__(self):
        self._processors: Dict[str, FormatProcessor] = {
            ".json": JsonFormatProcessor(),
            ".csv": CsvFormatProcessor(),
            ".txt": TxtFormatProcessor()
        }
    
    def get_processor(self, file_extension: str) -> Optional[FormatProcessor]:
        return self._processors.get(file_extension.lower())
    
    def register_processor(self, file_extension: str, processor: FormatProcessor):
        self._processors[file_extension.lower()] = processor

class TermDatabase:
    # 单例实例
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TermDatabase, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        # 确保初始化只执行一次
        if self._initialized:
            return
        
        self.terms: List[Dict[str, Any]] = []
        self.terms_by_length: Dict[int, List[Dict[str, Any]]] = {}  # 按长度分组的术语
        self.term_regex_cache: Dict[str, re.Pattern] = {}  # 正则表达式缓存
        self.term_set: Set[str] = set()  # 术语原始字符串集合
        
        # 初始化导入相关组件
        self.validator = TermValidator()
        self.format_registry = FormatProcessorRegistry()
        
        self.load_terms()
        self._initialized = True
    
    def _build_indexes(self):
        """
        构建术语索引，用于优化查询性能
        """
        self.terms_by_length.clear()
        self.term_regex_cache.clear()
        self.term_set.clear()
        
        # 构建按长度分组的术语索引
        for term in self.terms:
            original = term["original"]
            length = len(original)
            if length not in self.terms_by_length:
                self.terms_by_length[length] = []
            self.terms_by_length[length].append(term)
            self.term_set.add(original)
        
        # 按长度降序排序分组
        for length in self.terms_by_length:
            # 按原始字符串长度降序，同一长度内按字母顺序
            self.terms_by_length[length].sort(key=lambda x: (-len(x["original"]), x["original"]))
        
        logging.debug(f"术语索引构建完成，共 {len(self.terms)} 个术语，{len(self.terms_by_length)} 个长度分组")
    def load_terms(self):
        """
        从文件加载术语库，支持从旧格式迁移
        """
        try:
            if TERM_DATABASE_PATH.exists():
                with open(TERM_DATABASE_PATH, 'r', encoding='utf-8') as f:
                    self.terms = json.load(f)
                
                # 数据迁移：将旧格式的字符串translation转换为列表
                migrated = False
                for term in self.terms:
                    if isinstance(term.get("translation"), str):
                        term["translation"] = [term["translation"]]
                        migrated = True
                
                if migrated:
                    # 只有当术语列表不为空时才保存
                    if self.terms:
                        self.save_terms()
                    logging.debug("术语库数据格式已迁移到多译文格式")
                
                logging.debug(f"成功加载术语库，共 {len(self.terms)} 个术语")
                # 构建索引
                self._build_indexes()
            else:
                self.terms = []
                # 初始化空索引
                self._build_indexes()
        except Exception as e:
            logging.error(f"加载术语库失败: {e}")
            self.terms = []
    def save_terms(self):
        """
        保存术语库到文件，只有当术语列表不为空时才保存
        """
        # 如果术语列表为空，不保存文件
        if not self.terms:
            # 如果文件已存在，删除它
            if TERM_DATABASE_PATH.exists():
                try:
                    TERM_DATABASE_PATH.unlink()
                    logging.debug("术语库文件已删除，因为术语列表为空")
                except Exception as e:
                    logging.error(f"删除空术语库文件失败: {e}")
            return
        
        try:
            with open(TERM_DATABASE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.terms, f, ensure_ascii=False, indent=4)
            logging.debug(f"成功保存术语库，共 {len(self.terms)} 个术语")
        except Exception as e:
            logging.error(f"保存术语库失败: {e}")
    def add_term(self, original: str, translation: str, comment: str = "", save_now: bool = True) -> Dict[str, Any]:
        """
        添加术语，支持向现有术语添加多个译文，忽略大小写
        Args:
            original: 原文术语
            translation: 译文术语
            comment: 注释
            save_now: 是否立即保存到文件，批量导入时可设为False以提高性能
        Returns:
            术语字典（现有或新创建的）
        """
        original = original.strip()
        translation = translation.strip()
        comment = comment.strip()
        
        # 检查是否已存在相同原文的术语（忽略大小写）
        existing_term = None
        original_lower = original.lower()
        for term in self.terms:
            if term["original"].lower() == original_lower:
                existing_term = term
                break
        
        if existing_term:
            # 向现有术语添加译文（去重）
            if translation not in existing_term["translation"]:
                existing_term["translation"].append(translation)
                existing_term["updated_at"] = datetime.now().isoformat()
                if save_now:
                    self.save_terms()
                    self._build_indexes()
                logging.debug(f"向现有术语添加译文: {original} -> {translation}")
            return existing_term
        else:
            # 创建新术语
            term = {
                "id": self._generate_term_id(),
                "original": original,
                "translation": [translation],
                "comment": comment,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            self.terms.append(term)
            if save_now:
                self.save_terms()
                self._build_indexes()
            logging.debug(f"添加新术语: {original} -> {translation}")
            return term
    
    def add_terms_batch(self, terms_data: List[Dict[str, Union[str, List[str]]]]) -> int:
        """
        批量添加术语
        Args:
            terms_data: 术语数据列表，每个字典包含original, translation, comment字段
                       translation支持字符串或列表
        Returns:
            成功添加的术语数量
        """
        count = 0
        for term_data in terms_data:
            original = term_data.get("original", "")
            translation = term_data.get("translation", "")
            comment = term_data.get("comment", "")
            
            if original and translation:
                if isinstance(translation, list):
                    # 处理多个译文
                    for trans in translation:
                        if trans.strip():
                            self.add_term(original, trans, comment, save_now=False)
                            count += 1
                else:
                    # 处理单个译文
                    self.add_term(original, translation, comment, save_now=False)
                    count += 1
        # 批量导入完成后统一保存和构建索引
        self.save_terms()
        self._build_indexes()
        logging.info(f"批量添加术语完成，共添加 {count} 个术语")
        return count
    def update_term(self, term_id: str, original: Optional[str] = None, translation: Optional[Union[str, List[str]]] = None, 
                   comment: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        更新现有术语
        Args:
            term_id: 术语ID
            original: 原文术语（可选）
            translation: 译文术语（可选，支持字符串或列表）
            comment: 注释（可选）
        Returns:
            更新后的术语字典，找不到则返回None
        """
        for term in self.terms:
            if term["id"] == term_id:
                if original is not None:
                    term["original"] = original.strip()
                if translation is not None:
                    if isinstance(translation, str):
                        # 单个译文，转换为列表
                        term["translation"] = [translation.strip()]
                    else:
                        # 多个译文，去重
                        term["translation"] = [t.strip() for t in translation if t.strip()]
                if comment is not None:
                    term["comment"] = comment.strip()
                term["updated_at"] = datetime.now().isoformat()
                self.save_terms()
                logging.info(f"更新术语: {term['original']} -> {', '.join(term['translation'])}")
                return term
        return None
    def delete_term(self, term_id: str) -> bool:
        """
        删除术语
        Args:
            term_id: 术语ID
        Returns:
            删除成功返回True，否则返回False
        """
        for i, term in enumerate(self.terms):
            if term["id"] == term_id:
                del self.terms[i]
                self.save_terms()
                logging.info(f"删除术语: {term['original']}")
                return True
        return False
    def search_terms(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索术语
        Args:
            keyword: 搜索关键词
        Returns:
            匹配的术语列表
        """
        results = []
        keyword = keyword.lower()
        for term in self.terms:
            if keyword in term["original"].lower() or keyword in term["translation"].lower():
                results.append(term)
        return results
    def find_matching_terms(self, text: str) -> List[Dict[str, Any]]:
        """
        查找文本中匹配的完整单词术语
        Args:
            text: 要匹配的文本
        Returns:
            匹配的术语列表
        """
        import re
        from utils import config_manager
        matching_terms = []
        matched_terms_set = set()  # 避免重复匹配
        
        # 快速检查：如果文本为空，直接返回空列表
        if not text:
            return []
        
        # 提取文本中的所有单词，用于快速过滤
        text_words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower()))
        
        # 加载个人词典，将其纳入术语匹配考量范围
        user_dict = config_manager.load_user_dict()
        user_dict_origin_terms = user_dict.get("by_origin_name", {})
        
        # 先处理个人词典中的术语
        for original, translation in user_dict_origin_terms.items():
            original_lower = original.lower()
            if original_lower in text_words:
                # 创建临时术语对象，模拟术语库中的术语结构
                temp_term = {
                    "id": f"user_dict_{original_lower}",
                    "original": original,
                    "translation": [translation],
                    "comment": "来自个人词典",
                    "created_at": "",
                    "updated_at": ""
                }
                # 检查是否在文本中完整匹配
                if re.search(rf'\b{re.escape(original)}\b', text, re.IGNORECASE):
                    matching_terms.append(temp_term)
                    matched_terms_set.add(original)
        
        # 按长度降序遍历术语分组
        for length in sorted(self.terms_by_length.keys(), reverse=True):
            # 跳过长度大于文本的术语
            if length > len(text):
                continue
            
            terms_in_length = self.terms_by_length[length]
            for term in terms_in_length:
                original = term["original"]
                
                # 跳过已匹配的术语（包括个人词典中的）
                if original in matched_terms_set:
                    continue
                
                # 快速过滤：如果术语的小写形式不在文本单词中，跳过
                original_lower = original.lower()
                if original_lower not in text_words:
                    continue
                
                # 从缓存获取或创建正则表达式
                if original not in self.term_regex_cache:
                    # 创建正则表达式，匹配完整单词，忽略大小写
                    self.term_regex_cache[original] = re.compile(rf'\b{re.escape(original)}\b', re.IGNORECASE)
                
                pattern = self.term_regex_cache[original]
                if pattern.search(text):
                    matching_terms.append(term)
                    matched_terms_set.add(original)
        
        return matching_terms
    def get_all_terms(self) -> List[Dict[str, Any]]:
        """
        获取所有术语
        Returns:
            术语列表
        """
        return self.terms.copy()
    def get_term_by_id(self, term_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取术语
        Args:
            term_id: 术语ID
        Returns:
            术语字典，找不到则返回None
        """
        for term in self.terms:
            if term["id"] == term_id:
                return term
        return None

    def import_terms(self, file_path: str, mode: str = ImportMode.INCREMENTAL) -> ImportResult:
        """
        从文件导入术语，支持多种格式和导入模式
        Args:
            file_path: 文件路径
            mode: 导入模式，支持full（全量导入）和incremental（增量导入）
        Returns:
            导入结果对象，包含成功、失败、更新和跳过的术语数量以及错误信息
        """
        result = ImportResult()
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            error_msg = f"文件不存在: {file_path}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg)
            return result
        
        # 获取文件扩展名
        file_extension = file_path_obj.suffix.lower()
        
        # 获取对应的格式处理器
        processor = self.format_registry.get_processor(file_extension)
        if not processor:
            error_msg = f"不支持的文件格式: {file_extension}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg)
            return result
        
        try:
            # 读取和解析文件
            logging.info(f"开始导入术语，文件: {file_path}，模式: {mode}")
            raw_terms = processor.process(file_path)
            logging.info(f"成功解析文件，共 {len(raw_terms)} 个术语")
            
            # 全量导入模式：清空现有术语库
            if mode == ImportMode.FULL:
                self.terms.clear()
                logging.info("全量导入模式：已清空现有术语库")
            
            # 处理每个术语
            for term_data in raw_terms:
                # 验证术语数据
                is_valid, errors = self.validator.validate(term_data)
                
                if not is_valid:
                    error_msg = f"术语验证失败: {term_data.get('original', '未知')}，错误: {'; '.join(errors)}"
                    result.errors.append(error_msg)
                    result.failure_count += 1
                    logging.error(error_msg)
                    continue
                
                # 提取术语字段
                original = term_data["original"].strip()
                translations = term_data["translation"]
                comment = term_data.get("comment", "").strip()
                
                # 查找现有术语
                existing_term = self._find_term_by_original(original)
                
                if existing_term:
                    # 增量导入模式：更新现有术语
                    if mode == ImportMode.INCREMENTAL:
                        # 合并译文（去重）
                        original_translations = set(existing_term["translation"])
                        new_translations = set(translations)
                        added_translations = new_translations - original_translations
                        
                        if added_translations:
                            existing_term["translation"].extend(added_translations)
                            existing_term["updated_at"] = datetime.now().isoformat()
                            if comment:
                                existing_term["comment"] = comment
                            result.updated_count += 1
                            logging.debug(f"更新术语: {original}，新增译文: {', '.join(added_translations)}")
                        else:
                            result.skipped_count += 1
                            logging.debug(f"跳过术语: {original}，译文无变化")
                    else:  # 全量导入模式：替换现有术语
                        existing_term["translation"] = translations
                        existing_term["comment"] = comment
                        existing_term["updated_at"] = datetime.now().isoformat()
                        result.updated_count += 1
                        logging.debug(f"替换术语: {original}")
                else:
                    # 添加新术语
                    new_term = {
                        "id": self._generate_term_id(),
                        "original": original,
                        "translation": translations,
                        "comment": comment,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                    self.terms.append(new_term)
                    result.success_count += 1
                    logging.debug(f"添加新术语: {original} -> {', '.join(translations)}")
            
            # 保存术语库并重建索引
            self.save_terms()
            self._build_indexes()
            
            logging.info(f"导入完成，成功: {result.success_count}，失败: {result.failure_count}，更新: {result.updated_count}，跳过: {result.skipped_count}")
            
        except Exception as e:
            error_msg = f"导入过程中发生错误: {str(e)}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg, exc_info=True)
        
        return result
    
    def _find_term_by_original(self, original: str) -> Optional[Dict[str, Any]]:
        """
        根据原文查找术语，忽略大小写
        Args:
            original: 原文术语
        Returns:
            匹配的术语字典，找不到则返回None
        """
        original_lower = original.lower()
        for term in self.terms:
            if term["original"].lower() == original_lower:
                return term
        return None
    
    def import_terms_from_csv(self, file_path: str) -> int:
        """
        从CSV文件导入术语（兼容旧版本方法）
        Args:
            file_path: CSV文件路径
        Returns:
            导入的术语数量
        """
        result = self.import_terms(file_path, ImportMode.INCREMENTAL)
        return result.success_count + result.updated_count
    def export_terms_to_csv(self, file_path: str) -> bool:
        """
        将术语导出为CSV文件
        Args:
            file_path: CSV文件路径
        Returns:
            导出成功返回True，否则返回False
        """
        import csv
        try:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                fieldnames = ["id", "original", "translation", "comment", "created_at", "updated_at"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for term in self.terms:
                    writer.writerow(term)
            logging.info(f"成功导出术语库到CSV: {file_path}")
            return True
        except Exception as e:
            logging.error(f"导出术语库失败: {e}")
            return False
    def _generate_term_id(self) -> str:
        """
        生成唯一的术语ID
        Returns:
            术语ID字符串
        """
        import uuid
        return str(uuid.uuid4())[:8]
    def reload(self) -> None:
        """
        重新加载术语库
        """
        self.load_terms()
        logging.info(f"术语库已重新加载，共 {len(self.terms)} 个术语")
    
    @classmethod
    def notify_all_instances(cls) -> None:
        """
        通知单例TermDatabase实例重新加载术语库
        用于社区词典导入后更新所有打开的术语库
        """
        if cls._instance is not None:
            logging.info("通知TermDatabase单例实例重新加载术语库")
            cls._instance.reload()
    
    def clear_terms(self) -> int:
        """
        清空术语库
        Returns:
            清空的术语数量
        """
        count = len(self.terms)
        self.terms = []
        self.save_terms()
        logging.info(f"清空术语库，共删除 {count} 个术语")
        return count