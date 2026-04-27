from __future__ import annotations
import re
import logging
import threading
from collections import defaultdict
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import (
    LanguageEntry, TranslationResult, NamespaceInfo,
    ExtractionResult, TranslationContext, TranslationSource,
    resolve_origin_name_conflict,
    JSON_KEY_VALUE_PATTERN, LANG_KV_PATTERN
)

class Translator:

    PLACEHOLDER_PERCENT = re.compile(r'%\d*\$?[a-zA-Z]+')
    PLACEHOLDER_BRACE = re.compile(r'\$\{[^}]+\}')
    PLACEHOLDER_DOLLAR = re.compile(r'\$\d+')
    CHINESE_CHAR = re.compile('[一-鿿]')
    ENGLISH_LETTER = re.compile(r'[a-zA-Z]')

    @staticmethod
    def resolve_origin_name_conflict(candidates: list[dict]) -> str | None:
        return resolve_origin_name_conflict(candidates)

    @staticmethod
    @lru_cache(maxsize=131072)
    def _is_valid_translation_cached(text: str) -> bool:
        if not text or not text.strip():
            return False
        cleaned = Translator.PLACEHOLDER_PERCENT.sub('', text)
        cleaned = Translator.PLACEHOLDER_BRACE.sub('', cleaned)
        cleaned = Translator.PLACEHOLDER_DOLLAR.sub('', cleaned)
        cleaned = cleaned.replace('%', '')
        if Translator.CHINESE_CHAR.search(cleaned):
            return True
        return not Translator.ENGLISH_LETTER.search(cleaned)

    def _is_valid_translation(self, text: str | None) -> bool:
        if text is None:
            return False
        return self._is_valid_translation_cached(text)

    def _decide_translation_for_key(
        self,
        key: str,
        english_value: str,
        ctx: TranslationContext,
    ) -> tuple[str | None, str | None]:
        has_user_dict_key = bool(ctx.user_dict_by_key)
        has_user_dict_origin = bool(ctx.user_dict_by_origin)
        has_community_dict_key = bool(ctx.community_dict_by_key)
        has_community_dict_origin = bool(ctx.community_dict_by_origin)
        has_pack_chinese_dict = bool(ctx.pack_chinese_dict)

        if key.startswith('_comment'):
            if key in ctx.internal_chinese:
                return ctx.internal_chinese[key].zh, TranslationSource.MOD_BUILTIN
            return "", TranslationSource.PENDING

        if self._is_valid_translation(english_value):
            return english_value, TranslationSource.ORIGINAL_COPY
        if key in ctx.internal_chinese:
            return ctx.internal_chinese[key].zh, TranslationSource.MOD_BUILTIN
        if has_user_dict_key and key in ctx.user_dict_by_key:
            return ctx.user_dict_by_key[key], TranslationSource.USER_DICT_KEY
        if has_user_dict_origin and english_value in ctx.user_dict_by_origin:
            return ctx.user_dict_by_origin[english_value], TranslationSource.USER_DICT_ORIGIN
        if has_pack_chinese_dict and key in ctx.pack_chinese_dict:
            return ctx.pack_chinese_dict[key], TranslationSource.COMMUNITY_PACK
        if ctx.use_community_dict_key and has_community_dict_key and key in ctx.community_dict_by_key:
            return ctx.community_dict_by_key[key], TranslationSource.COMMUNITY_DICT_KEY
        if ctx.use_community_dict_origin and has_community_dict_origin and english_value in ctx.community_dict_by_origin:
            if ctx.dictionary_manager:
                best_translation = ctx.dictionary_manager.get_community_origin_translation(english_value)
                if best_translation:
                    return best_translation, TranslationSource.COMMUNITY_DICT_ORIGIN
            else:
                candidates = ctx.community_dict_by_origin[english_value]
                best_translation = self.resolve_origin_name_conflict(candidates)
                if best_translation:
                    return best_translation, TranslationSource.COMMUNITY_DICT_ORIGIN

        return None, None

    def _normalize_translation_result(
        self, translation: str | None, source: str | None
    ) -> tuple[str, str]:
        if source == TranslationSource.ORIGINAL_COPY:
            return translation or "", source
        if source == TranslationSource.PENDING:
            return translation or "", TranslationSource.PENDING
        if not self._is_valid_translation(translation):
            return "", TranslationSource.PENDING
        return translation or "", source

    def _process_namespace_with_incremental(
        self,
        namespace: str,
        english_entries: dict[str, LanguageEntry],
        existing_translations: dict[str, LanguageEntry],
        ctx: TranslationContext,
        update_existing: bool,
    ) -> dict[str, LanguageEntry]:
        ns_result: dict[str, LanguageEntry] = {}
        ordered_keys = list(english_entries.keys())

        for key in ordered_keys:
            english_entry = english_entries.get(key)
            if not english_entry:
                continue

            english_value = english_entry.en

            if key in existing_translations and not update_existing:
                existing_entry = existing_translations[key]
                translation, source = self._normalize_translation_result(
                    existing_entry.zh, existing_entry.source
                )
            else:
                translation, source = self._decide_translation_for_key(
                    key,
                    english_value,
                    ctx,
                )
                translation, source = self._normalize_translation_result(translation, source)

            ns_result[key] = LanguageEntry(
                key=key,
                en=english_value,
                zh=translation,
                source=source,
                namespace=namespace
            )

        return ns_result

    def _build_translation_context(
        self,
        namespace: str,
        extraction_result: ExtractionResult,
        user_dict_by_key: dict,
        user_dict_by_origin: dict,
        community_dict_by_key: dict,
        community_dict_by_origin: dict,
        use_community_dict_key: bool,
        use_community_dict_origin: bool,
        dictionary_manager,
    ) -> TranslationContext:
        internal_chinese = extraction_result.internal_chinese.get(namespace, {})
        return TranslationContext(
            user_dict_by_key=user_dict_by_key,
            user_dict_by_origin=user_dict_by_origin,
            community_dict_by_key=community_dict_by_key,
            community_dict_by_origin=community_dict_by_origin,
            internal_chinese=internal_chinese,
            pack_chinese_dict=extraction_result.pack_chinese,
            use_community_dict_key=use_community_dict_key,
            use_community_dict_origin=use_community_dict_origin,
            dictionary_manager=dictionary_manager,
        )

    def _process_namespace_task(
        self,
        namespace: str,
        english_entries: dict[str, LanguageEntry],
        extraction_result: ExtractionResult,
        existing_translations: dict[str, dict[str, LanguageEntry]] | None,
        update_existing: bool,
        user_dict_by_key: dict,
        user_dict_by_origin: dict,
        community_dict_by_key: dict,
        community_dict_by_origin: dict,
        use_community_dict_key: bool,
        use_community_dict_origin: bool,
        dictionary_manager,
    ) -> tuple[str, dict[str, LanguageEntry]]:
        ctx = self._build_translation_context(
            namespace, extraction_result,
            user_dict_by_key, user_dict_by_origin,
            community_dict_by_key, community_dict_by_origin,
            use_community_dict_key, use_community_dict_origin,
            dictionary_manager,
        )

        existing_ns_translations = existing_translations.get(namespace, {}) if existing_translations else {}

        if update_existing or not existing_ns_translations:
            ns_result = self._process_namespace_with_incremental(
                namespace=namespace,
                english_entries=english_entries,
                existing_translations=existing_ns_translations,
                ctx=ctx,
                update_existing=update_existing,
            )
        else:
            ns_result = existing_ns_translations

        return namespace, ns_result

    def run(
        self,
        extraction_result: ExtractionResult,
        user_dictionary: dict,
        community_dict_by_key: dict[str, str],
        community_dict_by_origin: dict[str, list[dict]],
        settings: dict,
        dictionary_manager=None,
        existing_translations: dict[str, dict[str, LanguageEntry]] | None = None,
        update_existing: bool = False
    ) -> TranslationResult:
        logging.info("--- 阶段 2: 执行翻译决策逻辑 ---")

        result = TranslationResult()
        workbench_data = result.workbench_data
        source_counts = result.source_counts
        source_counts_lock = threading.Lock()

        user_dict_by_key = user_dictionary.get('by_key', {})
        user_dict_by_origin = user_dictionary.get('by_origin_name', {})

        use_community_dict_key = settings.get('use_community_dict_key', True)
        use_community_dict_origin = settings.get('use_community_dict_origin', True)

        namespaces = list(extraction_result.master_english.items())
        namespace_count = len(namespaces)

        common_kwargs = dict(
            extraction_result=extraction_result,
            existing_translations=existing_translations,
            update_existing=update_existing,
            user_dict_by_key=user_dict_by_key,
            user_dict_by_origin=user_dict_by_origin,
            community_dict_by_key=community_dict_by_key,
            community_dict_by_origin=community_dict_by_origin,
            use_community_dict_key=use_community_dict_key,
            use_community_dict_origin=use_community_dict_origin,
            dictionary_manager=dictionary_manager,
        )

        def _accumulate_source_counts(ns_result: dict[str, LanguageEntry]):
            for entry in ns_result.values():
                source = entry.source or TranslationSource.PENDING
                with source_counts_lock:
                    source_counts[source] = source_counts.get(source, 0) + 1

        if namespace_count <= 3:
            logging.info(f"使用串行方式处理 {namespace_count} 个命名空间")
            for namespace, english_entries in namespaces:
                _, ns_result = self._process_namespace_task(
                    namespace=namespace,
                    english_entries=english_entries,
                    **common_kwargs
                )
                workbench_data[namespace] = ns_result
                _accumulate_source_counts(ns_result)
        else:
            logging.info(f"使用并行方式处理 {namespace_count} 个命名空间")

            max_workers = min(8, namespace_count)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self._process_namespace_task,
                        namespace=namespace,
                        english_entries=english_entries,
                        **common_kwargs
                    )
                    for namespace, english_entries in namespaces
                ]

                for future in as_completed(futures):
                    namespace, ns_result = future.result()
                    workbench_data[namespace] = ns_result
                    _accumulate_source_counts(ns_result)

        result.total_entries = sum(len(entries) for entries in workbench_data.values())

        logging.info("--- 翻译决策贡献分析 ---")
        logging.info(f"总条目数: {result.total_entries}")
        for source, count in sorted(source_counts.items()):
            percentage = (count / result.total_entries) * 100 if result.total_entries > 0 else 0
            logging.info(f"  ▷ {source}: {count} 条 ({percentage:.2f}%)")
        logging.info("--------------------------")

        logging.info("翻译决策引擎运行完毕。")
        return result
