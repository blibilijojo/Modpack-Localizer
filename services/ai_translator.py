import openai
import logging
import json
import time
import threading
import queue
import asyncio
from collections.abc import Callable
from pathlib import Path
from itertools import cycle
from utils.error_logger import log_ai_error
from datetime import datetime, timedelta


class AIResponseNonStringValueError(ValueError):
    """模型在 JSON 某键上返回了非字符串；交由 translate_batch 重试，而非原文回填。"""


class KeyManager:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("至少需要一个有效的API密钥")
        self.available_keys = queue.Queue()
        for key in api_keys:
            self.available_keys.put(key)
        self.cooldown_keys = {}
        self.lock = threading.Lock()
        logging.info(f"密钥管理器已初始化，可用密钥数量: {self.available_keys.qsize()}")
    def _check_cooldowns(self):
        with self.lock:
            current_time = time.monotonic()
            keys_to_reactivate = [key for key, end_time in self.cooldown_keys.items() if current_time >= end_time]
            for key in keys_to_reactivate:
                del self.cooldown_keys[key]
                self.available_keys.put(key)
                logging.info(f"密钥 ...{key[-4:]} 已结束冷却，回归可用队列。")
    def get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        while True:
            self._check_cooldowns()
            try:
                key = self.available_keys.get(timeout=0.1)
                return key
            except queue.Empty:
                if should_abort and should_abort():
                    return None
                time.sleep(0.5)
    def release_key(self, key: str):
        self.available_keys.put(key)
    def penalize_key(self, key: str, cooldown_seconds: int):
        with self.lock:
            cooldown_end_time = time.monotonic() + cooldown_seconds
            self.cooldown_keys[key] = cooldown_end_time
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
    
    # 异步方法
    async def async_get_key(self, should_abort: Callable[[], bool] | None = None) -> str | None:
        while True:
            self._check_cooldowns()
            try:
                # 尝试从队列中获取密钥，使用非阻塞方式
                key = self.available_keys.get(block=False)
                return key
            except queue.Empty:
                if should_abort and should_abort():
                    return None
                # 队列空，等待一段时间后重试
                await asyncio.sleep(0.5)
    
    async def async_release_key(self, key: str):
        self.available_keys.put(key)
    
    async def async_penalize_key(self, key: str, cooldown_seconds: int):
        with self.lock:
            cooldown_end_time = time.monotonic() + cooldown_seconds
            self.cooldown_keys[key] = cooldown_end_time
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
class AITranslator:
    def __init__(self, api_services: list[dict] = None, cache_ttl=3600):
        # 处理api_services参数
        self.api_services = api_services or []
        
        # 构建密钥到服务的映射
        self.key_to_service = {}
        all_keys = []
        for service in self.api_services:
            keys = service.get("keys", [])
            for key in keys:
                self.key_to_service[key] = service
                all_keys.append(key)
        
        # 兼容旧的api_keys格式
        if not self.api_services:
            # 假设使用默认OpenAI
            self.api_services = [{"endpoint": None, "keys": all_keys, "max_threads": 4}]
        
        self.key_manager = KeyManager(all_keys)
        self.all_keys = all_keys
        # 初始化翻译缓存，用于存储已翻译的文本
        self.translation_cache = {}
        # 缓存过期时间（秒）
        self.cache_ttl = cache_ttl
        # 缓存锁，确保线程安全
        self.cache_lock = threading.RLock()
        # 取消标志
        self._cancelled = False
        self._active_stream_lock = threading.Lock()
        self._active_streams: list = []
        
        # 记录初始化信息
        service_count = len(self.api_services)
        total_keys = len(all_keys)
        logging.info(f"翻译器已初始化。服务数量: {service_count}, 密钥总数: {total_keys}, 缓存TTL: {cache_ttl}秒")

    def describe_effective_models(self, request_model: str | None) -> str:
        """
        与 translate_batch / translate_batch_async 中选用模型的规则一致：若某条 api_services
        配置了 model 且非占位「请先获取模型」，则请求使用该值；否则使用传入的 request_model
        （即界面「模型」字段）。用于日志展示实际会发往 API 的模型名。
        """
        req = (request_model or "").strip() or "（未在配置中指定模型）"
        resolved: list[str] = []
        for service in self.api_services:
            sm = (service.get("model") or "").strip()
            if sm and sm != "请先获取模型":
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
        """
        取消所有正在执行的翻译任务
        """
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
        """从其他线程关闭进行中的流式响应，打断阻塞在读取上的 HTTP 连接。"""
        with self._active_stream_lock:
            streams = tuple(self._active_streams)
            self._active_streams.clear()
        for s in streams:
            try:
                s.close()
            except Exception as e:
                logging.debug(f"关闭进行中请求流: {e}")

    def _consume_chat_completion_stream(self, client: openai.OpenAI, request_params: dict) -> str | None:
        """
        流式拉取补全内容，便于在 chunk 间隔检查取消；cancel() 会 close 流以尽快打断阻塞读。

        Returns:
            拼接后的助手文本；若用户取消则为 None。
        """
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
    
    def reset_cancel(self):
        """
        重置取消标志
        """
        self._cancelled = False
        logging.info("翻译器取消标志已重置")
    def _get_client(self, api_key: str):
        # 根据密钥获取对应的服务
        service = self.key_to_service.get(api_key)
        endpoint = service.get("endpoint") if service else None
        if endpoint:
            return openai.OpenAI(base_url=endpoint, api_key=api_key)
        else:
            # 使用标准OpenAI API配置
            return openai.OpenAI(api_key=api_key)
    
    def _cleanup_cache(self):
        """
        清理过期的缓存项
        """
        with self.cache_lock:
            current_time = time.time()
            expired_keys = []
            for key, (translation, timestamp) in self.translation_cache.items():
                if current_time - timestamp > self.cache_ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.translation_cache[key]
            
            if expired_keys:
                logging.debug(f"清理了 {len(expired_keys)} 个过期的缓存项")
    
    def _get_cached_translation(self, text):
        """
        从缓存中获取翻译结果
        
        Args:
            text: 原文文本
            
        Returns:
            翻译结果，如果缓存中不存在或已过期则返回None
        """
        with self.cache_lock:
            self._cleanup_cache()  # 先清理过期缓存
            if text in self.translation_cache:
                translation, timestamp = self.translation_cache[text]
                # 检查是否过期
                if time.time() - timestamp <= self.cache_ttl:
                    logging.debug(f"从缓存中获取翻译结果: {text}")
                    return translation
                else:
                    # 过期了，删除缓存项
                    del self.translation_cache[text]
            return None
    
    def _cache_translation(self, text, translation):
        """
        将翻译结果存入缓存
        
        Args:
            text: 原文文本
            translation: 翻译结果
        """
        with self.cache_lock:
            self.translation_cache[text] = (translation, time.time())
            logging.debug(f"缓存翻译结果: {text} → {translation}")

    def _normalize_batch_entry(self, entry):
        """
        规范化批次条目，兼容旧版字符串输入与新版结构化输入。

        Returns:
            tuple[str, dict|str, str]:
            - source_text: 用于回填与结果映射的原始文本
            - prompt_value: 发送给模型的输入值（字符串或对象）
            - cache_key: 缓存键（包含key上下文时可区分同文不同键）
        """
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
        for key in cycle(self.all_keys):
            try:
                client = self._get_client(key)
                models_response = client.models.list()
                def get_model_weight(model_name: str) -> int:
                    name = model_name.lower()
                    # 通用模型权重排序，优先考虑gpt-4系列，然后是gpt-3.5系列，最后是其他模型
                    if "gpt-4" in name: return 10
                    if "gpt-3.5" in name: return 9
                    if "gpt-" in name: return 8
                    # 其他模型根据名称长度排序
                    return 0
                model_list = models_response.data if hasattr(models_response, 'data') else models_response.models
                sorted_models = sorted([m.id.replace("models/", "") for m in model_list], key=lambda x: (-get_model_weight(x), x))
                logging.info(f"成功获取并排序了 {len(sorted_models)} 个模型")
                return sorted_models
            except Exception as e:
                logging.error(f"使用密钥 ...{key[-4:]} 获取模型列表失败: {e}")
        logging.error("所有API密钥均无法获取模型列表")
        return []
    def translate_batch(self, batch_info: tuple) -> list[str]:
        # 解析批次信息，移除超时参数
        if len(batch_info) == 5:
            batch_index_inner, batch_inner, model_name, prompt_template, _ = batch_info
        else:
            batch_index_inner, batch_inner, model_name, prompt_template = batch_info
        
        # 检查取消标志
        if self._cancelled:
            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
            return [None] * len(batch_inner)
        
        # 缓存检查
        cached_results = [None] * len(batch_inner)
        
        # 检查缓存，收集需要翻译的文本
        texts_to_translate = []
        text_indices = {}
        normalized_entries = [self._normalize_batch_entry(entry) for entry in batch_inner]
        source_texts = [entry[0] for entry in normalized_entries]

        for idx, (_, _, cache_key) in enumerate(normalized_entries):
            # 检查取消标志
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            
            # 从缓存中获取翻译结果
            cached_translation = self._get_cached_translation(cache_key)
            if cached_translation:
                cached_results[idx] = cached_translation
                logging.debug(f"批次 {batch_index_inner + 1}：条目命中缓存")
            else:
                texts_to_translate.append(normalized_entries[idx][1])
                text_indices[len(texts_to_translate) - 1] = idx
        
        # 检查取消标志
        if self._cancelled:
            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
            return [None] * len(batch_inner)
        
        # 如果所有文本都命中缓存，直接返回结果
        if not texts_to_translate:
            logging.info(f"批次 {batch_index_inner + 1}：所有文本均命中缓存，无需 API 调用")
            return cached_results
        
        # 对未命中缓存的文本进行翻译（条数已在 GUI 侧 INFO 记录，此处仅 DEBUG 避免重复）
        logging.debug(f"批次 {batch_index_inner + 1}：需要翻译 {len(texts_to_translate)} 个文本")
        
        attempt = 0
        max_attempts = 5  # 最大重试次数
        while attempt < max_attempts:
            # 检查取消标志
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            
            api_key = self.key_manager.get_key(lambda: self._cancelled)
            if api_key is None:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消（等待 API 密钥）")
                return [None] * len(batch_inner)
            logging.debug(f"线程 {threading.get_ident()} (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1}/{max_attempts} 使用密钥 ...{api_key[-4:]}")
            
            # 检查取消标志
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                self.key_manager.release_key(api_key)
                return [None] * len(batch_inner)
            
            try:
                # 根据密钥获取对应的服务，使用该服务的模型设置
                effective_model_name = model_name
                service = self.key_to_service.get(api_key)
                if service:
                    service_model = service.get('model')
                    if service_model and service_model != "请先获取模型":
                        effective_model_name = service_model
                
                client = self._get_client(api_key)
                input_dict = dict(enumerate(texts_to_translate))
                input_json = json.dumps(input_dict, ensure_ascii=False)
                # 兼容 prompt 模板中的占位符：{input_data_json}
                # 如果模板已包含该占位符，则直接替换；否则追加输入区块。
                if "{input_data_json}" in (prompt_template or ""):
                    prompt_content = (prompt_template or "").replace("{input_data_json}", input_json)
                else:
                    prompt_content = f"{prompt_template}\n\n输入: {input_json}"
                request_params = {"model": effective_model_name, "messages": [{"role": "user", "content": prompt_content}]}
                
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)
                
                # 执行API调用
                try:
                    # 检查取消标志
                    if self._cancelled:
                        logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止API调用")
                        self.key_manager.release_key(api_key)
                        return [None] * len(batch_inner)
                    
                    response_text = self._consume_chat_completion_stream(client, request_params)
                except Exception as e:
                    # 检查取消标志
                    if self._cancelled:
                        logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                        self.key_manager.release_key(api_key)
                        return [None] * len(batch_inner)
                    logging.error(f"批次 {batch_index_inner + 1}：API调用失败: {e}")
                    self.key_manager.penalize_key(api_key, 10)
                    # 不要在惩罚冷却期间立即 release key，避免冷却失效
                    attempt += 1
                    if attempt >= max_attempts:
                        logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                        # 返回原文作为回退
                        for idx, text in enumerate(source_texts):
                            if cached_results[idx] is None:
                                cached_results[idx] = text
                        return cached_results
                    continue
                
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)

                if response_text is None:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，已中止流式请求")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)

                untranslated_source_texts = [source_texts[text_indices[idx]] for idx in range(len(texts_to_translate))]
                translated_texts = self._parse_response(response_text, untranslated_source_texts)
                
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)
                
                if translated_texts:
                    # 将翻译结果存入缓存并构建完整的结果列表
                    for idx, translation in enumerate(translated_texts):
                        # 检查取消标志
                        if self._cancelled:
                            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                            self.key_manager.release_key(api_key)
                            return [None] * len(batch_inner)
                        
                        # 获取原始文本
                        source_text = untranslated_source_texts[idx]
                        source_cache_key = normalized_entries[text_indices[idx]][2]
                        # 缓存翻译结果
                        self._cache_translation(source_cache_key, translation)
                        # 填充到结果列表中
                        original_idx = text_indices[idx]
                        cached_results[original_idx] = translation
                    
                    logging.info(f"线程 {threading.get_ident()} 成功完成批次 {batch_index_inner + 1}")
                    self.key_manager.release_key(api_key)
                    return cached_results
                else:
                    log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    try:
                        self.key_manager.release_key(api_key)
                    except Exception:
                        pass
                    return [None] * len(batch_inner)
                
                attempt += 1
                error_str = str(e).lower()
                cooldown_duration = 2.0 * (2 ** min(attempt, 8))
                
                # 网络错误特殊处理
                is_network_error = any(phrase in error_str for phrase in ["timeout", "connection error", "network error", "connect"])
                
                # 账户验证错误处理
                is_account_error = any(phrase in error_str for phrase in ["403", "verify your account", "account verification"])
                
                if any(phrase in error_str for phrase in ["rate limit", "too many requests", "429", "quota exceeded"]):
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇速率限制。")
                    cooldown_duration = 60
                elif isinstance(e, ValueError):
                     logging.warning(f"批次 {batch_index_inner + 1} 遭遇内容格式错误。")
                     cooldown_duration = 10
                elif is_network_error:
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇网络错误: {e}")
                    # 网络错误增加冷却时间
                    cooldown_duration = 10 * (2 ** min(attempt, 5))
                elif is_account_error:
                    logging.error(f"批次 {batch_index_inner + 1} 遭遇账户验证错误: {e}")
                    logging.error("请验证您的OpenAI账户以继续使用API服务。")
                    # 账户错误增加冷却时间，因为需要用户操作
                    cooldown_duration = 30
                else:
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇临时错误: {e}")
                
                self.key_manager.penalize_key(api_key, cooldown_duration)
                
                # 检查是否达到最大重试次数
                if attempt >= max_attempts:
                    logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                    # 返回原文作为回退
                    for idx, text in enumerate(source_texts):
                        if cached_results[idx] is None:
                            cached_results[idx] = text
                    return cached_results
                
                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试 ({attempt}/{max_attempts})。")
    def _parse_response(self, response_text: str | None, original_batch: list[str]) -> list[str] | None:
        """
        解析AI响应，提取翻译结果
        
        Args:
            response_text: AI返回的响应文本
            original_batch: 原始文本批次
            
        Returns:
            翻译结果列表，如果解析失败则返回原始文本
        """
        if not response_text:
            logging.error("AI未返回任何文本内容")
            return None
        
        expected_length = len(original_batch)
        
        try:
            # 阶段1：预处理响应文本
            processed_text = self._preprocess_response(response_text)
            
            # 阶段2：检测错误信息
            if self._is_error_response(processed_text):
                logging.warning(f"AI返回了错误信息而不是翻译结果: {processed_text}")
                # 对于错误信息，返回与原始批次长度相同的空字符串列表，避免无限重试
                return ["" for _ in original_batch]
            
            # 阶段3：提取JSON部分
            json_str = self._extract_json(processed_text)
            if not json_str:
                preview = processed_text[:800] + ("…" if len(processed_text) > 800 else "")
                logging.error(
                    "AI响应中找不到有效的JSON对象（常见原因：输出被 max_tokens 截断、或模型未输出完整 JSON）。"
                    "响应预览: %s",
                    preview,
                )
                # 尝试直接返回原文作为回退方案
                return original_batch
            
            # 阶段4：解析JSON并构建结果
            return self._parse_json_and_build_result(
                json_str, original_batch, expected_length, full_ai_response=response_text
            )
            
        except json.JSONDecodeError as e:
            logging.error(f"解析AI的JSON响应失败: {e}. 尝试解析的字符串是: '{processed_text}'")
            # 解析失败时返回原文
            return original_batch
        except AIResponseNonStringValueError:
            raise
        except Exception as e:
            logging.error(f"解析AI响应时发生未知错误: {e}")
            # 发生未知错误时返回原文
            return original_batch
    
    def _preprocess_response(self, response_text: str) -> str:
        """
        预处理响应文本，移除代码块标记等
        
        Args:
            response_text: 原始响应文本
            
        Returns:
            预处理后的文本
        """
        processed_text = response_text.strip()
        
        # 处理 ```json 格式的代码块
        if processed_text.startswith('```json'):
            processed_text = processed_text[7:]
        if processed_text.startswith('```'):
            processed_text = processed_text[3:]
        if processed_text.endswith('```'):
            processed_text = processed_text[:-3]
        
        return processed_text
    
    def _is_error_response(self, processed_text: str) -> bool:
        """
        检测是否是错误响应
        
        Args:
            processed_text: 预处理后的响应文本
            
        Returns:
            如果是错误响应返回True，否则返回False
        """
        error_keywords = ["抱歉", "错误", "无法", "failed", "error", "cannot"]
        
        # 检查是否包含错误信息关键词
        contains_error_keyword = any(keyword in processed_text for keyword in error_keywords)
        
        # 如果不包含错误关键词，直接返回False
        if not contains_error_keyword:
            return False
        
        # 如果包含错误关键词，进一步检查
        try:
            # 尝试直接解析整个处理后的文本
            data = json.loads(processed_text)
            if isinstance(data, dict):
                # 检查JSON数据中是否包含错误信息
                for key, value in data.items():
                    if isinstance(value, str) and any(keyword in value for keyword in error_keywords):
                        # 检查是否所有值都是错误信息
                        all_error_values = True
                        for v in data.values():
                            if isinstance(v, str) and not any(keyword in v for keyword in error_keywords):
                                all_error_values = False
                                break
                        # 只有当所有值都是错误信息时，才视为错误响应
                        return all_error_values
        except Exception:
            # 如果无法解析为JSON，检查是否是纯错误信息
            # 只有当文本中只包含错误信息而没有有效的翻译内容时，才视为错误响应
            if '{' not in processed_text or '}' not in processed_text:
                return True
        
        return False
    
    def _extract_json(self, processed_text: str) -> str:
        """
        从响应文本中提取第一个完整 JSON 对象字符串。

        使用 json.JSONDecoder.raw_decode，按 JSON 语法识别字符串边界，避免简单花括号
        计数在译文含 ``}``、``{`` 等字符时提前截断，导致误判为「找不到 JSON」。
        """
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
    
    def _parse_json_and_build_result(
        self,
        json_str: str,
        original_batch: list[str],
        expected_length: int,
        *,
        full_ai_response: str | None = None,
    ) -> list[str]:
        """
        解析JSON并构建翻译结果列表
        
        Args:
            json_str: JSON字符串
            original_batch: 原始文本批次
            expected_length: 预期结果长度
            full_ai_response: 模型原始返回全文，用于异常时在控制台输出排查
        
        Returns:
            翻译结果列表
        """
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
            # 尝试直接返回原文作为回退方案
            return original_batch
        
        if len(data) != expected_length:
            logging.warning(
                "AI响应条目数量不匹配！预期: %s, 实际: %s。将使用原文回填。%s",
                expected_length,
                len(data),
                _tail_once(),
            )
            # 尝试返回尽可能多的翻译结果，其余使用原文
            reconstructed_list = list(original_batch)
            for key, value in data.items():
                try:
                    index = int(key)
                    if 0 <= index < expected_length:
                        if isinstance(value, str):
                            reconstructed_list[index] = value.replace('\n', '\\n')
                        else:
                            logging.warning(
                                "AI响应条目数量不匹配且键'%s'为非字符串类型(%s)，将重试批次。%s",
                                key,
                                type(value).__name__,
                                _tail_once(),
                            )
                            raise AIResponseNonStringValueError(
                                f"键 {key!r} 的翻译值为非字符串类型: {type(value).__name__}"
                            )
                except AIResponseNonStringValueError:
                    raise
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
                    if isinstance(value, str):
                        # 将实际换行符转换为转义形式，确保在界面上正确显示
                        reconstructed_list[index] = value.replace('\n', '\\n')
                    else:
                        logging.warning(
                            "AI为键'%s'返回了非字符串类型的值(%s)，将重试本批次。%s",
                            key,
                            type(value).__name__,
                            _tail_once(),
                        )
                        raise AIResponseNonStringValueError(
                            f"键 {key!r} 的翻译值为非字符串类型: {type(value).__name__}"
                        )
            except AIResponseNonStringValueError:
                raise
            except (ValueError, TypeError):
                logging.warning("AI返回了无效的键'%s'，已忽略。%s", key, _tail_once())
        
        # 检查是否有未填充的项
        for i in range(expected_length):
            if reconstructed_list[i] is None:
                # 使用原文作为回退
                reconstructed_list[i] = original_batch[i]
        
        return reconstructed_list
    
    async def translate_batch_async(self, batch_info: tuple) -> list[str]:
        """
        异步版本的批量翻译方法

        Args:
            batch_info: 批次信息，包含批次索引、文本批次、模型名称、提示模板

        Returns:
            翻译结果列表
        """
        # 解析批次信息，移除超时参数
        if len(batch_info) == 5:
            batch_index_inner, batch_inner, model_name, prompt_template, _ = batch_info
        else:
            batch_index_inner, batch_inner, model_name, prompt_template = batch_info

        if self._cancelled:
            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
            return [None] * len(batch_inner)

        # 缓存检查
        cached_results = [None] * len(batch_inner)
        
        # 检查缓存，收集需要翻译的文本
        texts_to_translate = []
        text_indices = {}
        normalized_entries = [self._normalize_batch_entry(entry) for entry in batch_inner]
        source_texts = [entry[0] for entry in normalized_entries]

        for idx, (_, _, cache_key) in enumerate(normalized_entries):
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            # 从缓存中获取翻译结果
            cached_translation = self._get_cached_translation(cache_key)
            if cached_translation:
                cached_results[idx] = cached_translation
                logging.debug(f"批次 {batch_index_inner + 1}：条目命中缓存")
            else:
                texts_to_translate.append(normalized_entries[idx][1])
                text_indices[len(texts_to_translate) - 1] = idx
        
        # 如果所有文本都命中缓存，直接返回结果
        if not texts_to_translate:
            logging.info(f"批次 {batch_index_inner + 1}：所有文本均命中缓存，无需 API 调用")
            return cached_results

        if self._cancelled:
            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
            return [None] * len(batch_inner)
        
        # 对未命中缓存的文本进行翻译（条数已在 GUI 侧 INFO 记录；模型名仅 DEBUG）
        logging.debug(
            f"批次 {batch_index_inner + 1}：需要翻译 {len(texts_to_translate)} 个文本，使用模型: {model_name}"
        )

        attempt = 0
        max_attempts = 5  # 最大重试次数
        while attempt < max_attempts:
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            api_key = None
            try:
                # 异步获取API密钥
                api_key = await self.key_manager.async_get_key(lambda: self._cancelled)
                if api_key is None:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消（等待 API 密钥）")
                    return [None] * len(batch_inner)
                logging.debug(f"异步线程 (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1}/{max_attempts} 使用密钥 ...{api_key[-4:]}")

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    return [None] * len(batch_inner)

                effective_model_name = model_name
                service = self.key_to_service.get(api_key)
                if service:
                    service_model = service.get("model")
                    if service_model and service_model != "请先获取模型":
                        effective_model_name = service_model

                client = self._get_client(api_key)
                input_dict = dict(enumerate(texts_to_translate))
                input_json = json.dumps(input_dict, ensure_ascii=False)
                # 兼容 prompt 模板中的占位符：{input_data_json}
                # 如果模板已包含该占位符，则直接替换；否则追加输入区块。
                if "{input_data_json}" in (prompt_template or ""):
                    prompt_content = (prompt_template or "").replace("{input_data_json}", input_json)
                else:
                    prompt_content = f"{prompt_template}\n\n输入: {input_json}"
                request_params = {"model": effective_model_name, "messages": [{"role": "user", "content": prompt_content}]}

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    return [None] * len(batch_inner)

                # 流式请求，与同步路径一致，便于 cancel() 关闭流以打断阻塞读
                response_text = await asyncio.to_thread(
                    self._consume_chat_completion_stream, client, request_params
                )

                if self._cancelled:
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    return [None] * len(batch_inner)

                if response_text is None:
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，已中止流式请求")
                    return [None] * len(batch_inner)

                untranslated_source_texts = [source_texts[text_indices[idx]] for idx in range(len(texts_to_translate))]
                translated_texts = self._parse_response(response_text, untranslated_source_texts)

                if translated_texts:
                    # 将翻译结果存入缓存并构建完整的结果列表
                    for idx, translation in enumerate(translated_texts):
                        # 缓存翻译结果
                        source_cache_key = normalized_entries[text_indices[idx]][2]
                        self._cache_translation(source_cache_key, translation)
                        # 填充到结果列表中
                        original_idx = text_indices[idx]
                        cached_results[original_idx] = translation

                    # 异步释放API密钥
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"异步线程 成功完成批次 {batch_index_inner + 1}")
                    return cached_results
                else:
                    log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    if api_key is not None:
                        try:
                            await self.key_manager.async_release_key(api_key)
                        except Exception:
                            pass
                    return [None] * len(batch_inner)

                attempt += 1
                error_str = str(e).lower()
                cooldown_duration = 2.0 * (2 ** min(attempt, 8))

                # 网络错误特殊处理
                is_network_error = any(phrase in error_str for phrase in ["timeout", "connection error", "network error", "connect"])

                # 账户验证错误处理
                is_account_error = any(phrase in error_str for phrase in ["403", "verify your account", "account verification"])

                if any(phrase in error_str for phrase in ["rate limit", "too many requests", "429", "quota exceeded"]):
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇速率限制。")
                    cooldown_duration = 60
                elif isinstance(e, ValueError):
                     logging.warning(f"批次 {batch_index_inner + 1} 遭遇内容格式错误。")
                     cooldown_duration = 10
                elif is_network_error:
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇网络错误: {e}")
                    # 网络错误增加冷却时间
                    cooldown_duration = 10 * (2 ** min(attempt, 5))
                elif is_account_error:
                    logging.error(f"批次 {batch_index_inner + 1} 遭遇账户验证错误: {e}")
                    logging.error("请验证您的OpenAI账户以继续使用API服务。")
                    # 账户错误增加冷却时间，因为需要用户操作
                    cooldown_duration = 30
                else:
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇临时错误: {e}")

                # 异步惩罚API密钥
                if api_key is not None:
                    await self.key_manager.async_penalize_key(api_key, cooldown_duration)

                # 检查是否达到最大重试次数
                if attempt >= max_attempts:
                    logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                    # 返回原文作为回退
                    for idx, text in enumerate(source_texts):
                        if cached_results[idx] is None:
                            cached_results[idx] = text
                    return cached_results

                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试 ({attempt}/{max_attempts})。")