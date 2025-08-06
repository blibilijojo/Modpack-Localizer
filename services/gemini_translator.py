# services/gemini_translator.py

import openai
import logging
import json
import time
from itertools import cycle
import threading

class GeminiTranslator:
    def __init__(self, api_keys: list[str], api_endpoint: str | None = None):
        if not api_keys or not any(api_keys):
            raise ValueError("至少需要一个有效的API密钥")
        
        self.api_endpoint = api_endpoint.strip() if api_endpoint else None
        
        self.api_keys_iterable = api_keys
        self.api_keys_cycle = cycle(self.api_keys_iterable)
        self.current_api_key = next(self.api_keys_cycle)
        self._key_rotation_lock = threading.Lock()
        
        logging.info(f"翻译器已初始化 (OpenAI 兼容模式)。API服务器: {self.api_endpoint or 'Google官方'}, 密钥数量: {len(self.api_keys_iterable)}")

    def _rotate_key(self):
        with self._key_rotation_lock:
            try:
                self.current_api_key = next(self.api_keys_cycle)
                logging.warning(f"线程 {threading.get_ident()} 正在轮换到下一个密钥: ...{self.current_api_key[-4:]}")
                return True
            except StopIteration: return False

    def _get_client(self, timeout=10.0):
        """Creates an OpenAI client configured for either official Google API or a custom endpoint."""
        if self.api_endpoint:
            # For custom proxy endpoints, use standard bearer token authentication
            return openai.OpenAI(base_url=self.api_endpoint, api_key=self.current_api_key, timeout=timeout)
        else:
            # For Google's official OpenAI-compatible endpoint, the key must be in the query parameter
            return openai.OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="non_empty_dummy_value", # API key is not sent in header for Google
                default_query={"key": self.current_api_key},
                timeout=timeout
            )

    def fetch_models(self) -> list[str]:
        logging.info(f"正在获取模型列表...")
        initial_key = self.current_api_key
        for _ in range(len(self.api_keys_iterable)):
            try:
                client = self._get_client()
                models_response = client.models.list()
                
                def get_model_weight(model_name: str) -> int:
                    name = model_name.lower()
                    if "gemini-1.5-pro" in name: return 9
                    if "gemini-1.5-flash" in name: return 8
                    return 0
                
                model_list = models_response.data if hasattr(models_response, 'data') else models_response.models
                
                # The id from Google's endpoint is 'models/gemini-1.5-flash-latest'
                sorted_models = sorted([m.id.replace("models/", "") for m in model_list], key=lambda x: (-get_model_weight(x), x))
                logging.info(f"成功获取并排序了 {len(sorted_models)} 个模型")
                return sorted_models
            except Exception as e:
                logging.error(f"获取模型列表失败: {e}")
                if not self._rotate_key() or (self.current_api_key == initial_key and len(self.api_keys_iterable) > 1):
                    break
        logging.error("所有API密钥均无法获取模型列表")
        return []

    def translate_batch(self, batch_info: tuple) -> list[str]:
        # --- REFACTORED: `use_grounding` is now received and used ---
        batch_index, batch, model_name, prompt_template, max_retries, retry_interval, use_grounding = batch_info
        
        thread_id = threading.get_ident()
        attempt = 0
        while True:
            attempt += 1
            retry_display = f"(尝试 {attempt}/{max_retries})" if max_retries != 0 else f"(尝试 {attempt})"
            try:
                logging.info(f"线程 {thread_id} 开始翻译批次 {batch_index + 1} {retry_display}...")
                
                # The model name for Google's endpoint needs the "models/" prefix
                effective_model_name = f"models/{model_name}" if not self.api_endpoint else model_name
                client = self._get_client(timeout=120.0)

                prompt_content = prompt_template.format(input_texts=json.dumps(batch, ensure_ascii=False))
                
                # --- REFACTORED: Dynamically build request parameters ---
                request_params = {
                    "model": effective_model_name,
                    "messages": [{"role": "user", "content": prompt_content}],
                    "response_format": {"type": "json_object"}
                }
                
                if use_grounding:
                    # Use the tool format compatible with Gemini models via OpenAI interface
                    request_params["tools"] = [{"type": "google_search_retrieval"}]
                    # Enforce the use of the tool. 'auto' is usually sufficient.
                    request_params["tool_choice"] = "auto"
                    logging.info(f"批次 {batch_index + 1} 已启用接地翻译模式 (Grounding via Google Search)")

                response = client.chat.completions.create(**request_params)
                
                response_text = response.choices[0].message.content
                translated_batch = self._parse_response(response_text, len(batch))
                
                if translated_batch:
                    logging.info(f"线程 {thread_id} 成功完成批次 {batch_index + 1}")
                    return translated_batch
                else:
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                logging.warning(f"批次 {batch_index + 1} {retry_display} 失败: {e}")
                
                # --- REFACTORED: Add specific error handling for tool usage ---
                if "tool use is not supported" in str(e).lower():
                    logging.error(f"模型 '{model_name}' 或当前API端点不支持工具（接地翻译），请尝试更换模型或关闭接地翻译功能。本次将自动回退到普通模式。")
                    # To prevent retrying a known-to-fail feature, we can turn it off for this batch
                    use_grounding = False 
                    # We can retry immediately without waiting or rotating key, since it's a feature issue
                    continue

                if max_retries != 0 and attempt >= max_retries:
                    logging.error(f"批次 {batch_index + 1} 已达到最大重试次数 ({max_retries})，将使用原文填充")
                    return batch
                
                self._rotate_key()
                if retry_interval > 0:
                    time.sleep(retry_interval)
    
    def _parse_response(self, response_text: str | None, expected_length: int) -> list[str] | None:
        if not response_text: 
            logging.error("AI未返回任何文本内容")
            return None
        try:
            data = json.loads(response_text)
            
            final_list = None
            if isinstance(data, list):
                final_list = data
            elif isinstance(data, dict):
                # Handle cases where the model wraps the list in a dictionary, e.g., {"translations": [...]}
                for value in data.values():
                    if isinstance(value, list):
                        final_list = value
                        break
            
            if final_list is None: 
                logging.warning(f"AI响应JSON中找不到列表。响应内容: {response_text[:200]}...")
                return None
                
            if all(isinstance(item, str) for item in final_list):
                if len(final_list) == expected_length:
                    return final_list
                else:
                    logging.warning(f"AI响应长度不匹配！预期: {expected_length}, 得到: {len(final_list)}")
            else:
                logging.warning("AI响应列表中的元素不全是字符串")
            return None
        except (json.JSONDecodeError, AttributeError) as e:
            logging.error(f"解析AI的JSON响应失败: {e}")
            logging.debug(f"无法解析的响应内容: {response_text[:500]}")
            return None