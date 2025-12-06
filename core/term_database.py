import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Union, Set
from datetime import datetime
import re

TERM_DATABASE_PATH = Path("term_database.json")

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
        
        logging.info(f"术语索引构建完成，共 {len(self.terms)} 个术语，{len(self.terms_by_length)} 个长度分组")
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
                    self.save_terms()
                    logging.info("术语库数据格式已迁移到多译文格式")
                
                logging.info(f"成功加载术语库，共 {len(self.terms)} 个术语")
                # 构建索引
                self._build_indexes()
            else:
                self.terms = []
                logging.info("术语库文件不存在，创建空术语库")
                # 初始化空索引
                self._build_indexes()
        except Exception as e:
            logging.error(f"加载术语库失败: {e}")
            self.terms = []
    def save_terms(self):
        """
        保存术语库到文件
        """
        try:
            with open(TERM_DATABASE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.terms, f, ensure_ascii=False, indent=4)
            logging.info(f"成功保存术语库，共 {len(self.terms)} 个术语")
        except Exception as e:
            logging.error(f"保存术语库失败: {e}")
    def add_term(self, original: str, translation: str, domain: str = "general", comment: str = "", save_now: bool = True) -> Dict[str, Any]:
        """
        添加术语，支持向现有术语添加多个译文，忽略大小写
        Args:
            original: 原文术语
            translation: 译文术语
            domain: 术语领域（如general, mod, quest等）
            comment: 注释
            save_now: 是否立即保存到文件，批量导入时可设为False以提高性能
        Returns:
            术语字典（现有或新创建的）
        """
        original = original.strip()
        translation = translation.strip()
        domain = domain.strip()
        comment = comment.strip()
        
        # 检查是否已存在相同原文的术语（忽略大小写）
        existing_term = None
        original_lower = original.lower()
        for term in self.terms:
            if term["original"].lower() == original_lower and term["domain"] == domain:
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
                "domain": domain,
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
            terms_data: 术语数据列表，每个字典包含original, translation, domain, comment字段
                       translation支持字符串或列表
        Returns:
            成功添加的术语数量
        """
        count = 0
        for term_data in terms_data:
            original = term_data.get("original", "")
            translation = term_data.get("translation", "")
            domain = term_data.get("domain", "general")
            comment = term_data.get("comment", "")
            
            if original and translation:
                if isinstance(translation, list):
                    # 处理多个译文
                    for trans in translation:
                        if trans.strip():
                            self.add_term(original, trans, domain, comment, save_now=False)
                            count += 1
                else:
                    # 处理单个译文
                    self.add_term(original, translation, domain, comment, save_now=False)
                    count += 1
        # 批量导入完成后统一保存和构建索引
        self.save_terms()
        self._build_indexes()
        logging.info(f"批量添加术语完成，共添加 {count} 个术语")
        return count
    def update_term(self, term_id: str, original: Optional[str] = None, translation: Optional[Union[str, List[str]]] = None, 
                   domain: Optional[str] = None, comment: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        更新现有术语
        Args:
            term_id: 术语ID
            original: 原文术语（可选）
            translation: 译文术语（可选，支持字符串或列表）
            domain: 术语领域（可选）
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
                if domain is not None:
                    term["domain"] = domain.strip()
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
    def search_terms(self, keyword: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索术语
        Args:
            keyword: 搜索关键词
            domain: 术语领域（可选）
        Returns:
            匹配的术语列表
        """
        results = []
        keyword = keyword.lower()
        for term in self.terms:
            if keyword in term["original"].lower() or keyword in term["translation"].lower():
                if domain is None or term["domain"] == domain:
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
        matching_terms = []
        matched_terms_set = set()  # 避免重复匹配
        
        # 快速检查：如果文本为空，直接返回空列表
        if not text:
            return []
        
        # 提取文本中的所有单词，用于快速过滤
        text_words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower()))
        
        # 按长度降序遍历术语分组
        for length in sorted(self.terms_by_length.keys(), reverse=True):
            # 跳过长度大于文本的术语
            if length > len(text):
                continue
            
            terms_in_length = self.terms_by_length[length]
            for term in terms_in_length:
                original = term["original"]
                
                # 跳过已匹配的术语
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
    def get_all_terms(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有术语
        Args:
            domain: 术语领域（可选）
        Returns:
            术语列表
        """
        if domain is None:
            return self.terms.copy()
        return [term for term in self.terms if term["domain"] == domain]
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
    def get_domains(self) -> List[str]:
        """
        获取所有术语领域
        Returns:
            术语领域列表
        """
        domains = set()
        for term in self.terms:
            domains.add(term["domain"])
        return sorted(list(domains))
    def import_terms_from_csv(self, file_path: str) -> int:
        """
        从CSV文件导入术语
        Args:
            file_path: CSV文件路径
        Returns:
            导入的术语数量
        """
        import csv
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    original = row.get("original", "")
                    translation = row.get("translation", "")
                    domain = row.get("domain", "general")
                    comment = row.get("comment", "")
                    if original and translation:
                        self.add_term(original, translation, domain, comment)
                        count += 1
        except Exception as e:
            logging.error(f"导入术语库失败: {e}")
        return count
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
                fieldnames = ["id", "original", "translation", "domain", "comment", "created_at", "updated_at"]
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
    
    def clear_terms(self, domain: Optional[str] = None) -> int:
        """
        清空术语库
        Args:
            domain: 术语领域（可选）
        Returns:
            清空的术语数量
        """
        if domain is None:
            count = len(self.terms)
            self.terms = []
        else:
            count = len([term for term in self.terms if term["domain"] == domain])
            self.terms = [term for term in self.terms if term["domain"] != domain]
        self.save_terms()
        logging.info(f"清空术语库，共删除 {count} 个术语")
        return count