from __future__ import annotations
import json
import logging


class AIResponseNonStringValueError(ValueError):
    pass


def preprocess_response(response_text: str) -> str:
    processed_text = response_text.strip()
    if processed_text.startswith('```json'):
        processed_text = processed_text[7:]
    if processed_text.startswith('```'):
        processed_text = processed_text[3:]
    if processed_text.endswith('```'):
        processed_text = processed_text[:-3]
    return processed_text


def is_error_response(processed_text: str) -> bool:
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


def extract_json(processed_text: str) -> str:
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


def extract_translation_value(value, key: str, _tail_once) -> str | None:
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


def parse_json_and_build_result(
    json_str: str,
    original_batch: list[str],
    expected_length: int,
    *,
    full_ai_response: str | None = None,
) -> list[str] | None:
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
                extracted = extract_translation_value(value, key, _tail_once)
                if extracted is not None:
                    reconstructed_list[index] = extracted
        except (ValueError, TypeError):
            logging.warning(
                "AI返回了无效的键'%s'，已忽略。%s", key, _tail_once()
            )

    return reconstructed_list


def parse_response(response_text: str | None, original_batch: list[str]) -> list[str | None] | None:
    if not response_text:
        logging.error("AI未返回任何文本内容")
        return None

    expected_length = len(original_batch)

    try:
        processed_text = preprocess_response(response_text)

        json_str = extract_json(processed_text)
        if not json_str:
            if is_error_response(processed_text):
                logging.warning(f"AI返回了错误信息而不是翻译结果: {processed_text[:200]}")
                return None
            preview = processed_text[:800] + ("…" if len(processed_text) > 800 else "")
            logging.error(
                "AI响应中找不到有效的JSON对象（常见原因：输出被 max_tokens 截断、或模型未输出完整 JSON）。"
                "响应预览: %s",
                preview,
            )
            return None

        return parse_json_and_build_result(
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
