import re
from typing import Dict, List, Tuple

JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
LANG_KEY_VALUE_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)


def extract_json_key_value_pairs(content: str) -> List[Tuple[str, str, int, int, str]]:
    """
    从JSON内容中提取键值对信息
    
    Args:
        content: JSON内容字符串
        
    Returns:
        键值对信息列表，每个元素为 (key, original_value, start, end, full_match)
    """
    key_info = []
    for match in JSON_KEY_VALUE_PATTERN.finditer(content):
        key = match.group(1)
        original_value = match.group(2)
        start, end = match.span()
        key_info.append((key, original_value, start, end, match.group(0)))
    return key_info


def extract_lang_key_value_pairs(content: str) -> List[Tuple[str, str, int, int, str, str]]:
    """
    从lang内容中提取键值对信息
    
    Args:
        content: lang内容字符串
        
    Returns:
        键值对信息列表，每个元素为 (key, original_value, start, end, full_match, indent)
    """
    key_info = []
    for match in LANG_KEY_VALUE_PATTERN.finditer(content):
        key = match.group(1)
        original_value = match.group(2)
        start, end = match.span()
        
        line_start = content.rfind('\n', 0, start)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        
        indent = content[line_start:start].split('\n')[-1]
        
        key_info.append((key, original_value, start, end, match.group(0), indent))
    return key_info


def build_json_file_with_translations(
    template_content: str,
    translations: Dict[str, str]
) -> str:
    """
    基于模板和翻译构建JSON语言文件
    
    Args:
        template_content: 原始JSON模板内容
        translations: 翻译键值对
        
    Returns:
        构建好的JSON内容
    """
    key_info = extract_json_key_value_pairs(template_content)
    key_info.sort(key=lambda x: x[2])
    
    output = []
    current_pos = 0
    comment_counter = 0
    
    for key, original_value, start, end, full_match in key_info:
        output.append(template_content[current_pos:start])
        
        if key == '_comment':
            comment_counter += 1
            translated_key = f'_comment_{comment_counter}'
            if translated_key in translations:
                translated_value = translations[translated_key].replace('"', '\\"')
                output.append(f'"{key}":"{translated_value}"')
            else:
                output.append(full_match)
        elif key in translations:
            translated_value = translations[key].replace('"', '\\"')
            output.append(f'"{key}":"{translated_value}"')
        else:
            output.append(full_match)
        
        current_pos = end
    
    output.append(template_content[current_pos:])
    result = ''.join(output)
    return result.replace('\r\n', '\n').replace('\r', '\n')


def build_lang_file_with_translations(
    template_content: str,
    translations: Dict[str, str]
) -> str:
    """
    基于模板和翻译构建lang语言文件
    
    Args:
        template_content: 原始lang模板内容
        translations: 翻译键值对
        
    Returns:
        构建好的lang内容
    """
    key_info = extract_lang_key_value_pairs(template_content)
    key_info.sort(key=lambda x: x[2])
    
    output = []
    current_pos = 0
    comment_counter = 0
    
    for key, original_value, start, end, full_match, indent in key_info:
        output.append(template_content[current_pos:start])
        
        if key == '_comment':
            comment_counter += 1
            translated_key = f'_comment_{comment_counter}'
            if translated_key in translations:
                translated_value = translations[translated_key]
                translated_value = translated_value.replace('"', '\\"')
                output.append(f'{indent}{key} = {translated_value}')
            else:
                output.append(full_match)
        elif key in translations:
            translated_value = translations[key]
            translated_value = translated_value.replace('"', '\\"')
            output.append(f'{indent}{key} = {translated_value}')
        else:
            output.append(full_match)
        
        current_pos = end
    
    output.append(template_content[current_pos:])
    result = ''.join(output)
    return result.replace('\r\n', '\n').replace('\r', '\n')


def extract_from_json_text(content: str) -> Dict[str, str]:
    """
    从JSON文本内容中提取语言数据
    
    Args:
        content: JSON文本内容
        
    Returns:
        提取的键值对字典
    """
    data = {}
    comment_counter = 0
    
    for match in JSON_KEY_VALUE_PATTERN.finditer(content):
        key = match.group(1)
        value = match.group(2)
        
        temp_value = value.replace('\\n', '__NEWLINE__')
        temp_value = temp_value.replace('\\t', '__TAB__')
        temp_value = temp_value.replace('\\r', '__CARRIAGE__')
        
        temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
        
        temp_value = temp_value.replace('__NEWLINE__', '\\n')
        temp_value = temp_value.replace('__TAB__', '\\t')
        temp_value = temp_value.replace('__CARRIAGE__', '\\r')
        
        temp_value = temp_value.replace('\\"', '"')
        
        if key == '_comment':
            comment_counter += 1
            data[f'_comment_{comment_counter}'] = temp_value
        else:
            data[key] = temp_value
    
    return data


def extract_from_lang_text(content: str) -> Dict[str, str]:
    """
    从lang文本内容中提取语言数据
    
    Args:
        content: lang文本内容
        
    Returns:
        提取的键值对字典
    """
    data = {}
    comment_counter = 0
    
    for match in LANG_KEY_VALUE_PATTERN.finditer(content):
        key = match.group(1)
        value = match.group(2).strip()
        
        if key == '_comment':
            comment_counter += 1
            data[f'_comment_{comment_counter}'] = value
        else:
            data[key] = value
    
    return data
