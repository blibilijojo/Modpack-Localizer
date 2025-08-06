# services/gemini_translator.py

import openai
import logging
import json
import time
from itertools import cycle
import threading
from utils.retry_logic import professional_retry

class GeminiTranslator:
    def __init__(self, api_keys: list[str], api_endpoint: str | None = None):
        if not api_keys or not any(api_keys):
            raise ValueError("至少需要一个有效的API密钥")
        
        self.api_endpoint = api_endpoint.strip() if api_endpoint else None
        
        self.api_keys_iterable = api_keys
        # --- MODIFIED: Initialize the cycle here ---
        self.api_keys_cycle = cycle(self.api_keys_iterable)
        self.current_api_key = next(self.api_keys_cycle)
        self._key_rotation_lock = threading.Lock()

        self.retry_decorator = professional_retry(
            initial_delay=2.0,
            on_failure_callback=self._rotate_key
        )
        
        logging.info(f"翻译器已初始化 (OpenAI 兼容模式)。API服务器: {self.api_endpoint or 'Google官方'}, 密钥数量: {len(self.api_keys_iterable)}")

    # --- MODIFIED: This now correctly handles the exhaustion of the cycle ---
    def _rotate_key(self):
        """Rotates to the next API key, recreating the cycle if it's exhausted."""
        with self._key_rotation_lock:
            try:
                self.current_api_key = next(self.api_keys_cycle)
                logging.warning(f"线程 {threading.get_ident()} 正在轮换到下一个密钥: ...{self.current_api_key[-4:]}")
            except StopIteration:
                logging.warning("所有API密钥已轮换一遍，正在重置循环。")
                # Re-create the cycle to start over from the beginning
                self.api_keys_cycle = cycle(self.api_keys_iterable)
                self.current_api_key = next(self.api_keys_cycle)
                logging.info(f"已重置到第一个密钥: ...{self.current_api_key[-4:]}")
        return True # Always returns True because it can now cycle infinitely

    def _get_client(self, timeout=120.0):
        if self.api_endpoint:
            return openai.OpenAI(base_url=self.api_endpoint, api_key=self.current_api_key, timeout=timeout)
        else:
            return openai.OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="non_empty_dummy_value",
                default_query={"key": self.current_api_key},
                timeout=timeout
            )

    def fetch_models(self) -> list[str]:
        logging.info(f"正在获取模型列表...")
        # This function's logic remains robust.
        initial_key = self.current_api_key
        for _ in range(len(self.api_keys_iterable) * 2): # Try each key twice
            try:
                client = self._get_client()
                models_response = client.models.list()
                
                def get_model_weight(model_name: str) -> int:
                    name = model_name.lower()
                    if "gemini-1.5-pro" in name: return 9
                    if "gemini-1.5-flash" in name: return 8
                    return 0
                
                model_list = models_response.data if hasattr(models_response, 'data') else models_response.models
                sorted_models = sorted([m.id.replace("models/", "") for m in model_list], key=lambda x: (-get_model_weight(x), x))
                logging.info(f"成功获取并排序了 {len(sorted_models)} 个模型")
                return sorted_models
            except Exception as e:
                logging.error(f"使用密钥 ...{self.current_api_key[-4:]} 获取模型列表失败: {e}")
                self._rotate_key()
                if self.current_api_key == initial_key: # Full cycle done
                    break
        logging.error("所有API密钥均无法获取模型列表")
        return []

    def translate_batch(self, batch_info: tuple) -> list[str]:
        @self.retry_decorator
        def _do_translation(batch_info_tuple: tuple) -> list[str]:
            (batch_index_inner, batch_inner, model_name, prompt_template, 
             _, _, use_grounding) = batch_info_tuple
            
            thread_id = threading.get_ident()
            logging.info(f"线程 {thread_id} 开始翻译批次 {batch_index_inner + 1}...")
            
            effective_model_name = f"models/{model_name}" if not self.api_endpoint else model_name
            client = self._get_client()
            prompt_content = prompt_template.format(input_texts=json.dumps(batch_inner, ensure_ascii=False))
            
            request_params = {
                "model": effective_model_name,
                "messages": [{"role": "user", "content": prompt_content}],
                "response_format": {"type": "json_object"}
            }
            
            if use_grounding:
                request_params["tools"] = [{"type": "google_search_retrieval"}]
                request_params["tool_choice"] = "auto"
                logging.info(f"批次 {batch_index_inner + 1} 已启用接地翻译模式")

            response = client.chat.completions.create(**request_params)
            response_text = response.choices[0].message.content
            translated_batch = self._parse_response(response_text, len(batch_inner))
            
            if translated_batch:
                logging.info(f"线程 {thread_id} 成功完成批次 {batch_index_inner + 1}")
                return translated_batch
            else:
                raise ValueError("AI响应解析或验证失败，将触发重试")

        return _do_translation(batch_info)

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