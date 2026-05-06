from __future__ import annotations
import json
import logging
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
import re
import csv
from typing import Any

TERM_DATABASE_PATH = Path("term_database.json")

_WORD_RE = re.compile(r'\b[a-zA-Z0-9_]+\b')


class ImportMode:
    FULL = "full"
    INCREMENTAL = "incremental"


class ImportResult:
    __slots__ = ('success_count', 'failure_count', 'updated_count', 'skipped_count', 'errors', 'warnings')

    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.updated_count = 0
        self.skipped_count = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []


class FormatProcessor:
    def process(self, file_path: str) -> list[dict[str, Any]]:
        raise NotImplementedError("必须实现process方法")


class JsonFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> list[dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "terms" in data:
                return data["terms"]
            else:
                raise ValueError("JSON文件格式无效，必须是术语列表或包含terms字段的对象")
        except Exception as e:
            raise ValueError(f"处理JSON文件失败: {str(e)}")


class CsvFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> list[dict[str, Any]]:
        try:
            terms = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    term = {
                        "original": row.get("original", "").strip(),
                        "translation": row.get("translation", "").strip().split("|"),
                        "comment": row.get("comment", "").strip()
                    }
                    terms.append(term)
            return terms
        except Exception as e:
            raise ValueError(f"处理CSV文件失败: {str(e)}")


class TxtFormatProcessor(FormatProcessor):
    def process(self, file_path: str) -> list[dict[str, Any]]:
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


class TermValidator:
    REQUIRED_FIELDS = ("original", "translation")

    def validate(self, term: dict[str, Any]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for field in self.REQUIRED_FIELDS:
            if field not in term or not term[field]:
                errors.append(f"缺少必填字段: {field}")

        original = term.get("original")
        if original is not None:
            if not isinstance(original, str) or not original.strip():
                errors.append("原文术语不能为空字符串")

        translation = term.get("translation")
        if translation is not None:
            if isinstance(translation, str):
                if not translation.strip():
                    errors.append("译文不能为空字符串")
                term["translation"] = [translation.strip()]
            elif isinstance(translation, list):
                cleaned = [t.strip() for t in translation if t.strip()]
                if not cleaned:
                    errors.append("译文列表中没有有效译文")
                term["translation"] = cleaned
            else:
                errors.append("译文必须是字符串或列表")

        return len(errors) == 0, errors


class FormatProcessorRegistry:
    def __init__(self):
        self._processors: dict[str, FormatProcessor] = {
            ".json": JsonFormatProcessor(),
            ".csv": CsvFormatProcessor(),
            ".txt": TxtFormatProcessor()
        }

    def get_processor(self, file_extension: str) -> FormatProcessor | None:
        return self._processors.get(file_extension.lower())

    def register_processor(self, file_extension: str, processor: FormatProcessor):
        self._processors[file_extension.lower()] = processor


class TermDatabase:
    _instance: TermDatabase | None = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.terms: list[dict[str, Any]] = []
        self.terms_by_length: dict[int, list[dict[str, Any]]] = {}
        self.term_regex_cache: dict[str, re.Pattern] = {}
        self.term_set: set[str] = set()
        self._original_index: dict[str, dict[str, Any]] = {}
        self._id_index: dict[str, dict[str, Any]] = {}
        self._user_dict_cache: dict[str, str] | None = None
        self._user_dict_cache_time: float = 0.0
        self._user_dict_cache_ttl: float = 30.0

        self.validator = TermValidator()
        self.format_registry = FormatProcessorRegistry()

        self.load_terms()
        self._initialized = True

    def _build_indexes(self):
        self.terms_by_length.clear()
        self.term_regex_cache.clear()
        self.term_set.clear()
        self._original_index.clear()
        self._id_index.clear()

        for term in self.terms:
            original = term["original"]
            length = len(original)
            if length not in self.terms_by_length:
                self.terms_by_length[length] = []
            self.terms_by_length[length].append(term)
            self.term_set.add(original)
            self._original_index[original.lower()] = term
            self._id_index[term["id"]] = term

        for length in self.terms_by_length:
            self.terms_by_length[length].sort(key=lambda x: (-len(x["original"]), x["original"]))

        logging.debug(f"术语索引构建完成，共 {len(self.terms)} 个术语，{len(self.terms_by_length)} 个长度分组")

    def _get_user_dict_origin_terms(self) -> dict[str, str]:
        current_time = time.time()
        if self._user_dict_cache is not None and (current_time - self._user_dict_cache_time) < self._user_dict_cache_ttl:
            return self._user_dict_cache
        from utils import config_manager
        user_dict = config_manager.load_user_dict()
        self._user_dict_cache = user_dict.get("by_origin_name", {})
        self._user_dict_cache_time = current_time
        return self._user_dict_cache

    def invalidate_user_dict_cache(self):
        self._user_dict_cache = None
        self._user_dict_cache_time = 0.0

    def load_terms(self):
        try:
            if TERM_DATABASE_PATH.exists():
                with open(TERM_DATABASE_PATH, 'r', encoding='utf-8') as f:
                    self.terms = json.load(f)

                migrated = False
                for term in self.terms:
                    if isinstance(term.get("translation"), str):
                        term["translation"] = [term["translation"]]
                        migrated = True

                if migrated:
                    if self.terms:
                        self.save_terms()
                    logging.debug("术语库数据格式已迁移到多译文格式")

                logging.debug(f"成功加载术语库，共 {len(self.terms)} 个术语")
                self._build_indexes()
            else:
                self.terms = []
                self._build_indexes()
        except Exception as e:
            logging.error(f"加载术语库失败: {e}")
            self.terms = []

    def save_terms(self):
        if not self.terms:
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

    def add_term(self, original: str, translation: str, comment: str = "", save_now: bool = True) -> dict[str, Any]:
        original = original.strip()
        translation = translation.strip()
        comment = comment.strip()

        existing_term = self._original_index.get(original.lower())

        if existing_term:
            if translation not in existing_term["translation"]:
                existing_term["translation"].append(translation)
                existing_term["updated_at"] = datetime.now().isoformat()
                if save_now:
                    self.save_terms()
                    self._build_indexes()
                logging.debug(f"向现有术语添加译文: {original} -> {translation}")
            return existing_term

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

    def add_terms_batch(self, terms_data: list[dict[str, str | list[str]]]) -> int:
        count = 0
        for term_data in terms_data:
            original = term_data.get("original", "")
            translation = term_data.get("translation", "")
            comment = term_data.get("comment", "")

            if original and translation:
                if isinstance(translation, list):
                    for trans in translation:
                        if trans.strip():
                            self.add_term(original, trans, comment, save_now=False)
                            count += 1
                else:
                    self.add_term(original, translation, comment, save_now=False)
                    count += 1
        self.save_terms()
        self._build_indexes()
        logging.info(f"批量添加术语完成，共添加 {count} 个术语")
        return count

    def update_term(
        self,
        term_id: str,
        original: str | None = None,
        translation: str | list[str] | None = None,
        comment: str | None = None,
    ) -> dict[str, Any] | None:
        term = self._id_index.get(term_id)
        if term is None:
            return None
        if original is not None:
            term["original"] = original.strip()
        if translation is not None:
            if isinstance(translation, str):
                term["translation"] = [translation.strip()]
            else:
                term["translation"] = [t.strip() for t in translation if t.strip()]
        if comment is not None:
            term["comment"] = comment.strip()
        term["updated_at"] = datetime.now().isoformat()
        self.save_terms()
        self._build_indexes()
        logging.info(f"更新术语: {term['original']} -> {', '.join(term['translation'])}")
        return term

    def delete_term(self, term_id: str) -> bool:
        term = self._id_index.get(term_id)
        if term is None:
            return False
        self.terms.remove(term)
        self.save_terms()
        self._build_indexes()
        logging.info(f"删除术语: {term['original']}")
        return True

    def search_terms(self, keyword: str) -> list[dict[str, Any]]:
        keyword_lower = keyword.lower()
        return [
            term for term in self.terms
            if keyword_lower in term["original"].lower() or keyword_lower in str(term["translation"]).lower()
        ]

    def find_matching_terms(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []

        matching_terms: list[dict[str, Any]] = []
        matched_terms_set: set[str] = set()
        text_words = set(_WORD_RE.findall(text.lower()))

        user_dict_origin_terms = self._get_user_dict_origin_terms()

        for original, translation in user_dict_origin_terms.items():
            original_lower = original.lower()
            if original_lower in text_words:
                if re.search(rf'\b{re.escape(original)}\b', text, re.IGNORECASE):
                    matching_terms.append({
                        "id": f"user_dict_{original_lower}",
                        "original": original,
                        "translation": [translation],
                        "comment": "来自个人词典",
                        "created_at": "",
                        "updated_at": ""
                    })
                    matched_terms_set.add(original)

        for length in sorted(self.terms_by_length.keys(), reverse=True):
            if length > len(text):
                continue

            for term in self.terms_by_length[length]:
                original = term["original"]

                if original in matched_terms_set:
                    continue

                original_lower = original.lower()
                if original_lower not in text_words:
                    continue

                if original not in self.term_regex_cache:
                    self.term_regex_cache[original] = re.compile(rf'\b{re.escape(original)}\b', re.IGNORECASE)

                if self.term_regex_cache[original].search(text):
                    matching_terms.append(term)
                    matched_terms_set.add(original)

        return matching_terms

    def get_all_terms(self) -> list[dict[str, Any]]:
        return self.terms.copy()

    def get_term_by_id(self, term_id: str) -> dict[str, Any] | None:
        return self._id_index.get(term_id)

    def import_terms(self, file_path: str, mode: str = ImportMode.INCREMENTAL) -> ImportResult:
        result = ImportResult()
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            error_msg = f"文件不存在: {file_path}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg)
            return result

        processor = self.format_registry.get_processor(file_path_obj.suffix.lower())
        if not processor:
            error_msg = f"不支持的文件格式: {file_path_obj.suffix.lower()}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg)
            return result

        try:
            logging.info(f"开始导入术语，文件: {file_path}，模式: {mode}")
            raw_terms = processor.process(file_path)
            logging.info(f"成功解析文件，共 {len(raw_terms)} 个术语")

            if mode == ImportMode.FULL:
                self.terms.clear()
                logging.info("全量导入模式：已清空现有术语库")

            for term_data in raw_terms:
                is_valid, errors = self.validator.validate(term_data)

                if not is_valid:
                    error_msg = f"术语验证失败: {term_data.get('original', '未知')}，错误: {'; '.join(errors)}"
                    result.errors.append(error_msg)
                    result.failure_count += 1
                    logging.error(error_msg)
                    continue

                original = term_data["original"].strip()
                translations = term_data["translation"]
                comment = term_data.get("comment", "").strip()

                existing_term = self._find_term_by_original(original)

                if existing_term:
                    if mode == ImportMode.INCREMENTAL:
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
                    else:
                        existing_term["translation"] = translations
                        existing_term["comment"] = comment
                        existing_term["updated_at"] = datetime.now().isoformat()
                        result.updated_count += 1
                        logging.debug(f"替换术语: {original}")
                else:
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

            self.save_terms()
            self._build_indexes()

            logging.info(f"导入完成，成功: {result.success_count}，失败: {result.failure_count}，更新: {result.updated_count}，跳过: {result.skipped_count}")

        except Exception as e:
            error_msg = f"导入过程中发生错误: {str(e)}"
            result.errors.append(error_msg)
            result.failure_count += 1
            logging.error(error_msg, exc_info=True)

        return result

    def _find_term_by_original(self, original: str) -> dict[str, Any] | None:
        return self._original_index.get(original.lower())

    def import_terms_from_csv(self, file_path: str) -> int:
        result = self.import_terms(file_path, ImportMode.INCREMENTAL)
        return result.success_count + result.updated_count

    def export_terms_to_csv(self, file_path: str) -> bool:
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
        return str(uuid.uuid4())[:8]

    def reload(self) -> None:
        self.load_terms()
        logging.info(f"术语库已重新加载，共 {len(self.terms)} 个术语")

    @classmethod
    def notify_all_instances(cls) -> None:
        if cls._instance is not None:
            logging.info("通知TermDatabase单例实例重新加载术语库")
            cls._instance.reload()

    def clear_terms(self) -> int:
        count = len(self.terms)
        self.terms = []
        self.save_terms()
        logging.info(f"清空术语库，共删除 {count} 个术语")
        return count
