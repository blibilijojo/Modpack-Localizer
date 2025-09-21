import openai
import logging
import json
import time
import threading
import queue
from itertools import cycle
from utils.error_logger import log_ai_error
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
class GeminiTranslator:
    def __init__(self, api_keys: list[str], api_endpoint: str | None = None):
        self.api_endpoint = api_endpoint.strip() if api_endpoint else None
        self.key_manager = KeyManager(api_keys)
        self.all_keys = api_keys
        logging.info(f"翻译器已初始化 (并发模式)。API服务器: {self.api_endpoint or 'Google官方'}")
    def _get_client(self, api_key: str, timeout=120.0):
        if self.api_endpoint:
            return openai.OpenAI(base_url=self.api_endpoint, api_key=api_key, timeout=timeout)
        else:
            return openai.OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="non_empty_dummy_value",
                default_query={"key": api_key},
                timeout=timeout
            )
    def fetch_models(self) -> list[str]:
        logging.info(f"正在获取模型列表...")
        for key in cycle(self.all_keys):
            try:
                client = self._get_client(key)
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
                logging.error(f"使用密钥 ...{key[-4:]} 获取模型列表失败: {e}")
        logging.error("所有API密钥均无法获取模型列表")
        return []
    def translate_batch(self, batch_info: tuple) -> list[str]:
        (batch_index_inner, batch_inner, model_name, prompt_template) = batch_info
        attempt = 0
        while True:
            api_key = self.key_manager.get_key()
            logging.debug(f"线程 {threading.get_ident()} (批次 {batch_index_inner + 1}) 尝试 #{attempt + 1} 使用密钥 ...{api_key[-4:]}")
            try:
                effective_model_name = f"models/{model_name}" if not self.api_endpoint else model_name
                client = self._get_client(api_key)
                input_dict = dict(enumerate(batch_inner))
                prompt_content = prompt_template.replace('{input_data_json}', json.dumps(input_dict, ensure_ascii=False))
                request_params = {"model": effective_model_name, "messages": [{"role": "user", "content": prompt_content}]}
                response = client.chat.completions.create(**request_params)
                response_text = response.choices[0].message.content
                translated_batch = self._parse_response(response_text, batch_inner)
                if translated_batch:
                    logging.info(f"线程 {threading.get_ident()} 成功完成批次 {batch_index_inner + 1}")
                    self.key_manager.release_key(api_key)
                    return translated_batch
                else:
                    log_ai_error(prompt_content, response_text)
                    raise ValueError("AI响应解析或验证失败")
            except Exception as e:
                attempt += 1
                error_str = str(e).lower()
                cooldown_duration = 2.0 * (2 ** min(attempt, 8))
                if any(phrase in error_str for phrase in ["rate limit", "too many requests", "429", "quota exceeded"]):
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇速率限制。")
                    cooldown_duration = 60
                elif isinstance(e, ValueError):
                     logging.warning(f"批次 {batch_index_inner + 1} 遭遇内容格式错误。")
                     cooldown_duration = 10
                else:
                    logging.warning(f"批次 {batch_index_inner + 1} 遭遇临时错误: {e}")
                self.key_manager.penalize_key(api_key, cooldown_duration)
                logging.info(f"批次 {batch_index_inner + 1} 将在获取到新密钥后重试。")
    def _parse_response(self, response_text: str | None, original_batch: list[str]) -> list[str] | None:
        if not response_text: 
            logging.error("AI未返回任何文本内容")
            return None
        expected_length = len(original_batch)
        try:
            start_index = response_text.find('{')
            end_index = response_text.rfind('}')
            if start_index == -1 or end_index == -1 or start_index >= end_index:
                logging.error(f"AI响应中找不到有效的JSON对象。响应: {response_text}")
                return None
            json_str = response_text[start_index : end_index + 1]
            data = json.loads(json_str)
            if not isinstance(data, dict):
                logging.warning(f"AI响应解析出的内容不是一个字典对象。内容: {data}")
                return None
            if len(data) != expected_length:
                logging.warning(f"AI响应条目数量不匹配！预期: {expected_length}, 实际: {len(data)}。将触发重试。")
                return None
            reconstructed_list = [None] * expected_length
            for key, value in data.items():
                try:
                    index = int(key)
                    if 0 <= index < expected_length:
                        if isinstance(value, str):
                            reconstructed_list[index] = value
                        else:
                             logging.warning(f"AI为键'{key}'返回了非字符串类型的值，将使用原文回填。")
                             return None
                except (ValueError, TypeError):
                    logging.warning(f"AI返回了无效的键'{key}'，已忽略。")
            if any(item is None for item in reconstructed_list):
                logging.warning(f"AI响应解析后存在未填充项（可能由无效或重复的键导致）。将触发重试。")
                return None
            return reconstructed_list
        except json.JSONDecodeError as e:
            logging.error(f"解析AI的JSON响应失败: {e}. 尝试解析的字符串是: '{json_str}'")
            return None
        except Exception as e:
            logging.error(f"解析AI响应时发生未知错误: {e}")
            return None