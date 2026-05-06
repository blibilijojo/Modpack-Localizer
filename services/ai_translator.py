from __future__ import annotations
import openai
import logging
import json
import time
import threading
import asyncio
from collections import OrderedDict
from collections.abc import Callable
from itertools import cycle
from utils.error_logger import ErrorLogger
from services.key_manager import KeyManager
from services.ai_stream_handler import StreamManager
from services.ai_response_parser import (
    AIResponseNonStringValueError,
    parse_response as _parse_response_impl,
)

# 保持向后兼容：外部可能直接 import AIResponseNonStringValueError
__all__ = ['AITranslator', 'AIResponseNonStringValueError']


class AITranslator:
    MAX_CACHE_SIZE = 10000
    _PLACEHOLDER_MODEL = "请先获取模型"

    def __init__(self, api_services: list[dict] = None, cache_ttl=3600, disable_cooldown: bool = False):
        self.api_services = api_services or []

        self.key_to_service = {}
        all_keys = []
        for service in self.api_services:
            keys = service.get("keys", [])
            for key in keys:
                self.key_to_service[key] = service
                all_keys.append(key)

        if not self.api_services:
            self.api_services = [{"endpoint": None, "keys": all_keys, "max_threads": 4}]

        self.key_manager = KeyManager(all_keys, disable_cooldown=disable_cooldown)
        self.all_keys = all_keys
        self.translation_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self.cache_ttl = cache_ttl
        self.cache_lock = threading.RLock()
        self._cancelled = False
        self._stream_manager = StreamManager()

        service_count = len(self.api_services)
        total_keys = len(all_keys)
        logging.info(f"翻译器已初始化。服务数量: {service_count}, 密钥总数: {total_keys}, 缓存TTL: {cache_ttl}秒")

    def describe_effective_models(self, request_model: str | None) -> str:
        req = (request_model or "").strip() or "（未在配置中指定模型）"
        resolved: list[str] = []
        for service in self.api_services:
            sm = (service.get("model") or "").strip()
            if sm and sm != self._PLACEHOLDER_MODEL:
                resolved.append(sm)
            else:
                resolved.append(req)
        uniq: list[str] = []
        for m in resolved:
            if m not in uniq:
                uniq.append(m)
        if len(uniq) == 1:
            return uniq[0]
        return f"依服务而异: {', '.join(uniq)}（界面基准: {req}）"

    def cancel(self):
        if not self._cancelled:
            self._cancelled = True
            self._stream_manager.close_all()
            logging.info("翻译器已收到取消命令，将终止所有正在执行的翻译任务")

    def reset_cancel(self):
        self._cancelled = False
        logging.info("翻译器取消标志已重置")

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def _cancelled_result(self, batch_inner: list) -> list[str | None]:
        return [None] * len(batch_inner)

    def _get_client(self, api_key: str) -> openai.OpenAI:
        service = self.key_to_service.get(api_key)
        endpoint = service.get("endpoint") if service else None
        if endpoint:
            return openai.OpenAI(base_url=endpoint, api_key=api_key)
        return openai.OpenAI(api_key=api_key)

    def _get_async_client(self, api_key: str) -> openai.AsyncOpenAI:
        service = self.key_to_service.get(api_key)
        endpoint = service.get("endpoint") if service else None
        if endpoint:
            return openai.AsyncOpenAI(base_url=endpoint, api_key=api_key)
        return openai.AsyncOpenAI(api_key=api_key)

    def _cleanup_cache(self):
        with self.cache_lock:
            current_time = time.time()
            expired_keys = [k for k, (_, ts) in self.translation_cache.items() if current_time - ts > self.cache_ttl]
            for key in expired_keys:
                del self.translation_cache[key]
            while len(self.translation_cache) > self.MAX_CACHE_SIZE:
                self.translation_cache.popitem(last=False)
            if expired_keys:
                logging.debug(f"清理了 {len(expired_keys)} 个过期的缓存项")

    def _get_cached_translation(self, text):
        with self.cache_lock:
            self._cleanup_cache()
            if text in self.translation_cache:
                translation, timestamp = self.translation_cache[text]
                if time.time() - timestamp <= self.cache_ttl:
                    self.translation_cache.move_to_end(text)
                    logging.debug(f"从缓存中获取翻译结果: {text}")
                    return translation
                else:
                    del self.translation_cache[text]
            return None

    def _cache_translation(self, text, translation):
        with self.cache_lock:
            self.translation_cache[text] = (translation, time.time())
            self.translation_cache.move_to_end(text)
            while len(self.translation_cache) > self.MAX_CACHE_SIZE:
                self.translation_cache.popitem(last=False)
            logging.debug(f"缓存翻译结果: {text} → {translation}")

    def _normalize_batch_entry(self, entry):
        if isinstance(entry, dict):
            source_text = str(entry.get("text", ""))
            source_key = str(entry.get("key", "") or "")
            prompt_value = {"text": source_text, "key": source_key}
            cache_key = f"{source_key}\x1f{source_text}" if source_key else source_text
            return source_text, prompt_value, cache_key

        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            source_key = str(entry[0] or "")
            source_text = str(entry[1] or "")
            prompt_value = {"text": source_text, "key": source_key}
            cache_key = f"{source_key}\x1f{source_text}" if source_key else source_text
            return source_text, prompt_value, cache_key

        source_text = str(entry or "")
        return source_text, source_text, source_text

    def fetch_models(self) -> list[str]:
        logging.info(f"正在获取模型列表...")
        max_attempts = len(self.all_keys) * 3
        for i, key in enumerate(cycle(self.all_keys)):
            if i >= max_attempts:
                break
            try:
                client = self._get_client(key)
                models_response = client.models.list()
                def get_model_weight(model_name: str) -> int:
                    name = model_name.lower()
                    if "gpt-4" in name: return 10
                    if "gpt-3.5" in name: return 9
                    if "gpt-" in name: return 8
                    return 0
                model_list = models_response.data if hasattr(models_response, 'data') else models_response.models
                sorted_models = sorted([m.id.replace("models/", "") for m in model_list], key=lambda x: (-get_model_weight(x), x))
                logging.info(f"成功获取并排序了 {len(sorted_models)} 个模型")
                return sorted_models
            except Exception as e:
                logging.error(f"使用密钥 ...{key[-4:]} 获取模型列表失败: {e}")
        logging.error("所有API密钥均无法获取模型列表")
        return []

    def _prepare_batch(self, batch_info: tuple):
        if len(batch_info) == 5:
            batch_index_inner, batch_inner, model_name, prompt_template, _ = batch_info
        else:
            batch_index_inner, batch_inner, model_name, prompt_template = batch_info

        if self._cancelled:
            return None

        cached_results = [None] * len(batch_inner)
        normalized_entries = [self._normalize_batch_entry(entry) for entry in batch_inner]
        source_texts = [entry[0] for entry in normalized_entries]
        texts_to_translate = []
        text_indices = {}

        for idx, (_, _, cache_key) in enumerate(normalized_entries):
            if self._cancelled:
                return None
            cached_translation = self._get_cached_translation(cache_key)
            if cached_translation:
                cached_results[idx] = cached_translation
            else:
                texts_to_translate.append(normalized_entries[idx][1])
                text_indices[len(texts_to_translate) - 1] = idx

        if self._cancelled:
            return None

        if not texts_to_translate:
            logging.info(f"批次 {batch_index_inner + 1}：所有文本均命中缓存，无需 API 调用")
            return cached_results

        return (batch_index_inner, batch_inner, model_name, prompt_template,
                cached_results, normalized_entries, source_texts,
                texts_to_translate, text_indices)

    def _build_request_params(self, model_name, api_key, texts_to_translate, prompt_template):
        effective_model_name = model_name
        service = self.key_to_service.get(api_key)
        if service:
            service_model = service.get('model')
            if service_model and service_model != self._PLACEHOLDER_MODEL:
                effective_model_name = service_model

        input_dict = dict(enumerate(texts_to_translate))
        input_json = json.dumps(input_dict, ensure_ascii=False)
        if "{input_data_json}" in (prompt_template or ""):
            prompt_content = (prompt_template or "").replace("{input_data_json}", input_json)
        else:
            prompt_content = f"{prompt_template}\n\n输入: {input_json}"
        return {"model": effective_model_name, "messages": [{"role": "user", "content": prompt_content}]}, prompt_content

    def _process_translation_result(self, response_text, context):
        (batch_index_inner, batch_inner, model_name, prompt_template,
         cached_results, normalized_entries, source_texts,
         texts_to_translate, text_indices) = context

        untranslated_source_texts = [source_texts[text_indices[idx]] for idx in range(len(texts_to_translate))]
        translated_texts = _parse_response_impl(response_text, untranslated_source_texts)

        if translated_texts:
            for idx, translation in enumerate(translated_texts):
                if translation is not None:
                    source_cache_key = normalized_entries[text_indices[idx]][2]
                    self._cache_translation(source_cache_key, translation)
                original_idx = text_indices[idx]
                cached_results[original_idx] = translation
            return cached_results, True
        else:
            return cached_results, False

    def _extract_batch_info(self, batch_info: tuple) -> tuple[int, list]:
        return batch_info[0], batch_info[1]

    def _prepare_or_return_cached(self, batch_info: tuple) -> tuple | list | None:
        batch_index_inner, batch_inner = self._extract_batch_info(batch_info)
        prepared = self._prepare_batch(batch_info)
        if prepared is None:
            return [None] * len(batch_inner)
        if isinstance(prepared, list):
            return prepared
        return prepared

    def _cancelled_result(self, batch_inner: list) -> list[str | None]:
        return [None] * len(batch_inner)

    def _classify_error_and_get_cooldown(self, error: Exception, attempt: int, batch_index: int) -> float:
        error_str = str(error).lower()
        cooldown_duration = 2.0 * (2 ** min(attempt, 8))

        is_network_error = any(phrase in error_str for phrase in ["timeout", "connection error", "network error", "connect"])
        is_account_error = any(phrase in error_str for phrase in ["403", "verify your account", "account verification"])

        if any(phrase in error_str for phrase in ["rate limit", "too many requests", "429", "quota exceeded"]):
            logging.warning(f"批次 {batch_index + 1} 遭遇速率限制。")
            cooldown_duration = 60
        elif isinstance(error, ValueError):
            logging.warning(f"批次 {batch_index + 1} 遭遇内容格式错误。")
            cooldown_duration = 10
        elif is_network_error:
            logging.warning(f"批次 {batch_index + 1} 遭遇网络错误: {error}")
            cooldown_duration = 10 * (2 ** min(attempt, 5))
        elif is_account_error:
            logging.error(f"批次 {batch_index + 1} 遭遇账户验证错误: {error}")
            logging.error("请验证您的OpenAI账户以继续使用API服务。")
            cooldown_duration = 30
        else:
            logging.warning(f"批次 {batch_index + 1} 遭遇临时错误: {error}")

        return cooldown_duration

    def translate_batch(self, batch_info: tuple) -> list[str]:
        batch_index_inner, batch_inner = self._extract_batch_info(batch_info)

        prepared = self._prepare_or_return_cached(batch_info)
        if isinstance(prepared, list):
            return prepared

        (batch_index_inner, batch_inner, model_name, prompt_template,
         cached_results, normalized_entries, source_texts,
         texts_to_translate, text_indices) = prepared

        logging.debug(f"批次 {batch_index_inner + 1}：需要翻译 {len(texts_to_translate)} 个文本")

        attempt = 0
        max_attempts = 5
        while attempt < max_attempts:
            if self._cancelled:
                return self._cancelled_result(batch_inner)

            api_key = self.key_manager.get_key(lambda: self._cancelled)
            if api_key is None:
                return self._cancelled_result(batch_inner)
            logging.debug(f"线程 {threading.get_ident()} (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1}/{max_attempts} 使用密钥 ...{api_key[-4:]}")

            if self._cancelled:
                self.key_manager.release_key(api_key)
                return self._cancelled_result(batch_inner)

            try:
                request_params, prompt_content = self._build_request_params(model_name, api_key, texts_to_translate, prompt_template)
                client = self._get_client(api_key)

                if self._cancelled:
                    self.key_manager.release_key(api_key)
                    return self._cancelled_result(batch_inner)

                try:
                    if self._cancelled:
                        self.key_manager.release_key(api_key)
                        return self._cancelled_result(batch_inner)

                    response_text = self._stream_manager.consume_sync(client, request_params, lambda: self._cancelled)
                except Exception as e:
                    if self._cancelled:
                        self.key_manager.release_key(api_key)
                        return self._cancelled_result(batch_inner)
                    logging.error(f"批次 {batch_index_inner + 1}：API调用失败: {e}")
                    self.key_manager.penalize_key(api_key, 10)
                    attempt += 1
                    if attempt >= max_attempts:
                        return cached_results
                    continue

                if self._cancelled:
                    self.key_manager.release_key(api_key)
                    return self._cancelled_result(batch_inner)

                if response_text is None:
                    self.key_manager.release_key(api_key)
                    return self._cancelled_result(batch_inner)

                cached_results, success = self._process_translation_result(response_text, prepared)

                if self._cancelled:
                    self.key_manager.release_key(api_key)
                    return self._cancelled_result(batch_inner)

                if success:
                    logging.info(f"线程 {threading.get_ident()} 成功完成批次 {batch_index_inner + 1}")
                    self.key_manager.release_key(api_key)
                    return cached_results
                else:
                    ErrorLogger.log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                if self._cancelled:
                    try:
                        self.key_manager.release_key(api_key)
                    except Exception:
                        pass
                    return self._cancelled_result(batch_inner)

                attempt += 1
                cooldown_duration = self._classify_error_and_get_cooldown(e, attempt, batch_index_inner)

                self.key_manager.penalize_key(api_key, cooldown_duration)

                if attempt >= max_attempts:
                    logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                    return cached_results

                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试 ({attempt}/{max_attempts})。")

    async def translate_batch_async(self, batch_info: tuple) -> list[str]:
        batch_index_inner, batch_inner = self._extract_batch_info(batch_info)

        prepared = self._prepare_or_return_cached(batch_info)
        if isinstance(prepared, list):
            return prepared

        (batch_index_inner, batch_inner, model_name, prompt_template,
         cached_results, normalized_entries, source_texts,
         texts_to_translate, text_indices) = prepared

        logging.debug(f"批次 {batch_index_inner + 1}：需要翻译 {len(texts_to_translate)} 个文本，使用模型: {model_name}")

        attempt = 0
        max_attempts = 5
        while attempt < max_attempts:
            if self._cancelled:
                return [None] * len(batch_inner)
            api_key = None
            try:
                api_key = await self.key_manager.async_get_key(lambda: self._cancelled)
                if api_key is None:
                    return [None] * len(batch_inner)
                logging.debug(f"异步线程 (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1}/{max_attempts} 使用密钥 ...{api_key[-4:]}")

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    return [None] * len(batch_inner)

                request_params, prompt_content = self._build_request_params(model_name, api_key, texts_to_translate, prompt_template)
                async_client = self._get_async_client(api_key)

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    return [None] * len(batch_inner)

                response_text = await self._stream_manager.consume_async(async_client, request_params, lambda: self._cancelled)

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    return [None] * len(batch_inner)

                if response_text is None:
                    await self.key_manager.async_release_key(api_key)
                    return [None] * len(batch_inner)

                cached_results, success = self._process_translation_result(response_text, prepared)

                if success:
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"异步线程 成功完成批次 {batch_index_inner + 1}")
                    return cached_results
                else:
                    ErrorLogger.log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                if self._cancelled:
                    if api_key is not None:
                        try:
                            await self.key_manager.async_release_key(api_key)
                        except Exception:
                            pass
                    return [None] * len(batch_inner)

                attempt += 1
                cooldown_duration = self._classify_error_and_get_cooldown(e, attempt, batch_index_inner)

                if api_key is not None:
                    await self.key_manager.async_penalize_key(api_key, cooldown_duration)

                if attempt >= max_attempts:
                    logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                    return cached_results

                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试 ({attempt}/{max_attempts})。")
