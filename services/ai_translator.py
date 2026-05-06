from __future__ import annotations
import openai
import logging
import json
import time
import threading
import asyncio
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from itertools import cycle
from utils.error_logger import ErrorLogger
from datetime import datetime, timedelta
from services.key_manager import KeyManager


class AIResponseNonStringValueError(ValueError):
    pass


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
        self._active_stream_lock = threading.Lock()
        self._active_streams: list = []

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
            self._close_active_streams()
            logging.info("翻译器已收到取消命令，将终止所有正在执行的翻译任务")

    def _register_stream(self, stream) -> None:
        with self._active_stream_lock:
            self._active_streams.append(stream)

    def _unregister_stream(self, stream) -> None:
        with self._active_stream_lock:
            try:
                self._active_streams.remove(stream)
            except ValueError:
                pass

    def _close_active_streams(self) -> None:
        with self._active_stream_lock:
            streams = tuple(self._active_streams)
            self._active_streams.clear()
        for s in streams:
            try:
                s.close()
            except Exception as e:
                logging.debug(f"关闭进行中请求流: {e}")

    def _consume_chat_completion_stream(self, client: openai.OpenAI, request_params: dict) -> str | None:
        params = dict(request_params)
        params["stream"] = True
        stream = client.chat.completions.create(**params)
        self._register_stream(stream)
        parts: list[str] = []
        try:
            try:
                for chunk in stream:
                    if self._cancelled:
                        return None
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is not None and delta.content:
                        parts.append(delta.content)
            except Exception:
                if self._cancelled:
                    return None
                raise
            return "".join(parts)
        finally:
            self._unregister_stream(stream)
            try:
                stream.close()
            except Exception:
                pass

    async def _consume_chat_completion_stream_async(self, client: openai.AsyncOpenAI, request_params: dict) -> str | None:
        params = dict(request_params)
        params["stream"] = True
        stream = await client.chat.completions.create(**params)
        self._register_stream(stream)
        parts: list[str] = []
        try:
            try:
                async for chunk in stream:
                    if self._cancelled:
                        return None
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is not None and delta.content:
                        parts.append(delta.content)
            except Exception:
                if self._cancelled:
                    return None
                raise
            return "".join(parts)
        finally:
            self._unregister_stream(stream)
            try:
                await stream.close()
            except Exception:
                pass

    def reset_cancel(self):
        self._cancelled = False
        logging.info("翻译器取消标志已重置")

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
        translated_texts = self._parse_response(response_text, untranslated_source_texts)

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

                    response_text = self._consume_chat_completion_stream(client, request_params)
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

                response_text = await self._consume_chat_completion_stream_async(async_client, request_params)

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

    def _parse_response(self, response_text: str | None, original_batch: list[str]) -> list[str | None] | None:
        if not response_text:
            logging.error("AI未返回任何文本内容")
            return None

        expected_length = len(original_batch)

        try:
            processed_text = self._preprocess_response(response_text)

            json_str = self._extract_json(processed_text)
            if not json_str:
                if self._is_error_response(processed_text):
                    logging.warning(f"AI返回了错误信息而不是翻译结果: {processed_text[:200]}")
                    return None
                preview = processed_text[:800] + ("…" if len(processed_text) > 800 else "")
                logging.error(
                    "AI响应中找不到有效的JSON对象（常见原因：输出被 max_tokens 截断、或模型未输出完整 JSON）。"
                    "响应预览: %s",
                    preview,
                )
                return None

            return self._parse_json_and_build_result(
                json_str, original_batch, expected_length, full_ai_response=response_text
            )

        except json.JSONDecodeError as e:
            logging.error(f"解析AI的JSON响应失败: {e}. 尝试解析的字符串是: '{processed_text}'")
            return None
        except AIResponseNonStringValueError:
            raise
        except Exception as e:
            logging.error(f"解析AI响应时发生未知错误: {e}")
            return None

    def _preprocess_response(self, response_text: str) -> str:
        processed_text = response_text.strip()

        if processed_text.startswith('```json'):
            processed_text = processed_text[7:]
        if processed_text.startswith('```'):
            processed_text = processed_text[3:]
        if processed_text.endswith('```'):
            processed_text = processed_text[:-3]

        return processed_text

    def _is_error_response(self, processed_text: str) -> bool:
        if '{' in processed_text and '}' in processed_text:
            return False

        error_indicators = [
            "抱歉", "我无法", "i cannot", "i'm sorry",
            "as an ai", "as a language model",
            "failed to", "error:",
        ]
        lower_text = processed_text.lower().strip()
        if len(lower_text) < 200:
            return any(indicator in lower_text for indicator in error_indicators)

        return False

    def _extract_json(self, processed_text: str) -> str:
        start_index = processed_text.find("{")
        if start_index == -1:
            return ""
        decoder = json.JSONDecoder()
        try:
            _, end = decoder.raw_decode(processed_text, start_index)
            return processed_text[start_index:end]
        except json.JSONDecodeError:
            pass

        json_candidate = processed_text[start_index:]
        brace_count = 0
        end_index = -1
        for i, char in enumerate(json_candidate):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_index = start_index + i + 1
                    break

        if end_index == -1:
            return ""

        return processed_text[start_index:end_index]

    def _extract_translation_value(self, value, key: str, _tail_once) -> str | None:
        if isinstance(value, str):
            return value.replace('\n', '\\n')
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                return text.replace('\n', '\\n')
            translation = value.get("translation")
            if isinstance(translation, str):
                return translation.replace('\n', '\\n')
            for v in value.values():
                if isinstance(v, str):
                    return v.replace('\n', '\\n')
            logging.warning(
                "AI为键'%s'返回了dict但无法提取文本(%s)，将重试本批次。%s",
                key, type(value).__name__, _tail_once(),
            )
            raise AIResponseNonStringValueError(
                f"键 {key!r} 的dict值中未找到可提取的文本字段"
            )
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first.replace('\n', '\\n')
        logging.warning(
            "AI为键'%s'返回了非字符串类型的值(%s)，将重试本批次。%s",
            key, type(value).__name__, _tail_once(),
        )
        raise AIResponseNonStringValueError(
            f"键 {key!r} 的翻译值为非字符串类型: {type(value).__name__}"
        )

    def _parse_json_and_build_result(
        self,
        json_str: str,
        original_batch: list[str],
        expected_length: int,
        *,
        full_ai_response: str | None = None,
    ) -> list[str]:
        _full_logged = False

        def _tail_once() -> str:
            nonlocal _full_logged
            if not full_ai_response or _full_logged:
                return ""
            _full_logged = True
            return f"\n完整AI返回：\n{full_ai_response}"

        data = json.loads(json_str)

        if not isinstance(data, dict):
            logging.warning(
                "AI响应解析出的内容不是一个字典对象。内容: %s%s", data, _tail_once()
            )
            return None

        if len(data) != expected_length:
            logging.warning(
                "AI响应条目数量不匹配！预期: %s, 实际: %s。缺失项将不应用。%s",
                expected_length,
                len(data),
                _tail_once(),
            )
            reconstructed_list = [None] * expected_length
            for key, value in data.items():
                try:
                    index = int(key)
                    if 0 <= index < expected_length:
                        extracted = self._extract_translation_value(value, key, _tail_once)
                        if extracted is not None:
                            reconstructed_list[index] = extracted
                except (ValueError, TypeError):
                    logging.warning(
                        "AI返回了无效的键'%s'，已忽略。%s", key, _tail_once()
                    )
            return reconstructed_list

        reconstructed_list = [None] * expected_length
        for key, value in data.items():
            try:
                index = int(key)
                if 0 <= index < expected_length:
                    extracted = self._extract_translation_value(value, key, _tail_once)
                    if extracted is not None:
                        reconstructed_list[index] = extracted
            except (ValueError, TypeError):
                logging.warning("AI返回了无效的键'%s'，已忽略。%s", key, _tail_once())

        return reconstructed_list
