import openai
import logging
import json
import time
import threading
import queue
import asyncio
from pathlib import Path
from itertools import cycle
from utils.error_logger import log_ai_error
from datetime import datetime, timedelta
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
    def get_key(self) -> str:
        while True:
            self._check_cooldowns()
            try:
                key = self.available_keys.get(timeout=0.1)
                return key
            except queue.Empty:
                time.sleep(0.5)
    def release_key(self, key: str):
        self.available_keys.put(key)
    def penalize_key(self, key: str, cooldown_seconds: int):
        with self.lock:
            cooldown_end_time = time.monotonic() + cooldown_seconds
            self.cooldown_keys[key] = cooldown_end_time
            logging.warning(f"密钥 ...{key[-4:]} 调用失败，将被冷却 {cooldown_seconds} 秒。")
    
    # 异步方法
    async def async_get_key(self) -> str:
        while True:
            self._check_cooldowns()
            try:
                # 尝试从队列中获取密钥，使用非阻塞方式
                key = self.available_keys.get(block=False)
                return key
            except queue.Empty:
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
        
        # 记录初始化信息
        service_count = len(self.api_services)
        total_keys = len(all_keys)
        logging.info(f"翻译器已初始化 (并发模式)。服务数量: {service_count}, 密钥总数: {total_keys}, 缓存TTL: {cache_ttl}秒")
    
    def cancel(self):
        """
        取消所有正在执行的翻译任务
        """
        if not self._cancelled:
            self._cancelled = True
            logging.info("翻译器已收到取消命令，将终止所有正在执行的翻译任务")
    
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
        
        # 文本去重和缓存检查
        unique_texts = []
        text_to_indices = {}
        cached_results = [None] * len(batch_inner)
        
        # 检查缓存，收集需要翻译的文本
        for idx, text in enumerate(batch_inner):
            # 检查取消标志
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            
            # 从缓存中获取翻译结果
            cached_translation = self._get_cached_translation(text)
            if cached_translation:
                cached_results[idx] = cached_translation
                logging.debug(f"批次 {batch_index_inner + 1}：文本 '{text}' 命中缓存")
            else:
                if text not in text_to_indices:
                    text_to_indices[text] = []
                    unique_texts.append(text)
                text_to_indices[text].append(idx)
        
        # 检查取消标志
        if self._cancelled:
            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
            return [None] * len(batch_inner)
        
        # 如果所有文本都命中缓存，直接返回结果
        if not unique_texts:
            logging.info(f"批次 {batch_index_inner + 1}：所有文本均命中缓存，无需API调用")
            return cached_results
        
        # 对未命中缓存的文本进行翻译
        logging.info(f"批次 {batch_index_inner + 1}：需要翻译 {len(unique_texts)} 个唯一文本")
        
        attempt = 0
        max_attempts = 5  # 最大重试次数
        while attempt < max_attempts:
            # 检查取消标志
            if self._cancelled:
                logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                return [None] * len(batch_inner)
            
            api_key = self.key_manager.get_key()
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
                input_dict = dict(enumerate(unique_texts))
                input_json = json.dumps(input_dict, ensure_ascii=False)
                # 将输入数据添加到提示词末尾，确保AI能够正确接收输入数据
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
                    
                    # 直接执行API调用，不使用超时机制
                    response = client.chat.completions.create(**request_params)
                except Exception as e:
                    # 检查取消标志
                    if self._cancelled:
                        logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                        self.key_manager.release_key(api_key)
                        return [None] * len(batch_inner)
                    logging.error(f"批次 {batch_index_inner + 1}：API调用失败: {e}")
                    self.key_manager.penalize_key(api_key, 10)
                    self.key_manager.release_key(api_key)
                    continue
                
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)
                
                response_text = response.choices[0].message.content
                translated_unique = self._parse_response(response_text, unique_texts)
                
                # 检查取消标志
                if self._cancelled:
                    logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                    self.key_manager.release_key(api_key)
                    return [None] * len(batch_inner)
                
                if translated_unique:
                    # 将翻译结果存入缓存并构建完整的结果列表
                    for idx, (text, translation) in enumerate(zip(unique_texts, translated_unique)):
                        # 检查取消标志
                        if self._cancelled:
                            logging.info(f"批次 {batch_index_inner + 1}：翻译任务已取消，立即终止")
                            self.key_manager.release_key(api_key)
                            return [None] * len(batch_inner)
                        
                        # 缓存翻译结果
                        self._cache_translation(text, translation)
                        # 填充到结果列表中
                        for original_idx in text_to_indices[text]:
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
                    for idx, text in enumerate(batch_inner):
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
                logging.error(f"AI响应中找不到有效的JSON对象。响应: {processed_text}")
                # 尝试直接返回原文作为回退方案
                return original_batch
            
            # 阶段4：解析JSON并构建结果
            return self._parse_json_and_build_result(json_str, original_batch, expected_length)
            
        except json.JSONDecodeError as e:
            logging.error(f"解析AI的JSON响应失败: {e}. 尝试解析的字符串是: '{processed_text}'")
            # 解析失败时返回原文
            return original_batch
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
        从响应文本中提取JSON部分
        
        Args:
            processed_text: 预处理后的响应文本
            
        Returns:
            提取的JSON字符串，如果没有找到则返回空字符串
        """
        # 智能提取JSON部分，处理包含额外文本的情况
        start_index = processed_text.find('{')
        if start_index == -1:
            return ""
        
        # 找到第一个{后的所有内容
        json_candidate = processed_text[start_index:]
        
        # 计算括号匹配，找到完整的JSON对象
        brace_count = 0
        end_index = -1
        for i, char in enumerate(json_candidate):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_index = start_index + i + 1
                    break
        
        if end_index == -1:
            return ""
        
        return processed_text[start_index:end_index]
    
    def _parse_json_and_build_result(self, json_str: str, original_batch: list[str], expected_length: int) -> list[str]:
        """
        解析JSON并构建翻译结果列表
        
        Args:
            json_str: JSON字符串
            original_batch: 原始文本批次
            expected_length: 预期结果长度
            
        Returns:
            翻译结果列表
        """
        data = json.loads(json_str)
        
        if not isinstance(data, dict):
            logging.warning(f"AI响应解析出的内容不是一个字典对象。内容: {data}")
            # 尝试直接返回原文作为回退方案
            return original_batch
        
        if len(data) != expected_length:
            logging.warning(f"AI响应条目数量不匹配！预期: {expected_length}, 实际: {len(data)}。将使用原文回填。")
            # 尝试返回尽可能多的翻译结果，其余使用原文
            reconstructed_list = list(original_batch)
            for key, value in data.items():
                try:
                    index = int(key)
                    if 0 <= index < expected_length and isinstance(value, str):
                        reconstructed_list[index] = value.replace('\n', '\\n')
                except (ValueError, TypeError):
                    pass
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
                        logging.warning(f"AI为键'{key}'返回了非字符串类型的值，将使用原文回填。")
                        # 对于非字符串值，使用原文
                        reconstructed_list[index] = original_batch[index]
            except (ValueError, TypeError):
                logging.warning(f"AI返回了无效的键'{key}'，已忽略。")
        
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

        # 文本去重和缓存检查
        unique_texts = []
        text_to_indices = {}
        cached_results = [None] * len(batch_inner)

        # 检查缓存，收集需要翻译的文本
        for idx, text in enumerate(batch_inner):
            # 从缓存中获取翻译结果
            cached_translation = self._get_cached_translation(text)
            if cached_translation:
                cached_results[idx] = cached_translation
                logging.debug(f"批次 {batch_index_inner + 1}：文本 '{text}' 命中缓存")
            else:
                if text not in text_to_indices:
                    text_to_indices[text] = []
                    unique_texts.append(text)
                text_to_indices[text].append(idx)

        # 如果所有文本都命中缓存，直接返回结果
        if not unique_texts:
            logging.info(f"批次 {batch_index_inner + 1}：所有文本均命中缓存，无需API调用")
            return cached_results

        # 对未命中缓存的文本进行翻译
        logging.info(f"批次 {batch_index_inner + 1}：需要翻译 {len(unique_texts)} 个唯一文本")

        attempt = 0
        max_attempts = 5  # 最大重试次数
        while attempt < max_attempts:
            try:
                # 异步获取API密钥
                api_key = await self.key_manager.async_get_key()
                logging.debug(f"异步线程 (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1}/{max_attempts} 使用密钥 ...{api_key[-4:]}")

                effective_model_name = model_name
                client = self._get_client(api_key)
                input_dict = dict(enumerate(unique_texts))
                input_json = json.dumps(input_dict, ensure_ascii=False)
                # 将输入数据添加到提示词末尾，确保AI能够正确接收输入数据
                prompt_content = f"{prompt_template}\n\n输入: {input_json}"
                request_params = {"model": effective_model_name, "messages": [{"role": "user", "content": prompt_content}]}

                # 异步执行API调用
                response = await asyncio.to_thread(client.chat.completions.create, **request_params)
                response_text = response.choices[0].message.content
                translated_unique = self._parse_response(response_text, unique_texts)

                if translated_unique:
                    # 将翻译结果存入缓存并构建完整的结果列表
                    for idx, (text, translation) in enumerate(zip(unique_texts, translated_unique)):
                        # 缓存翻译结果
                        self._cache_translation(text, translation)
                        # 填充到结果列表中
                        for original_idx in text_to_indices[text]:
                            cached_results[original_idx] = translation

                    # 异步释放API密钥
                    await self.key_manager.async_release_key(api_key)
                    logging.info(f"异步线程 成功完成批次 {batch_index_inner + 1}")
                    return cached_results
                else:
                    log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
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
                await self.key_manager.async_penalize_key(api_key, cooldown_duration)

                # 检查是否达到最大重试次数
                if attempt >= max_attempts:
                    logging.error(f"批次 {batch_index_inner + 1} 达到最大重试次数 ({max_attempts})，翻译失败。")
                    # 返回原文作为回退
                    for idx, text in enumerate(batch_inner):
                        if cached_results[idx] is None:
                            cached_results[idx] = text
                    return cached_results

                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试 ({attempt}/{max_attempts})。")