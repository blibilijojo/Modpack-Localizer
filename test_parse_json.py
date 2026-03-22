import re

def _parse_json_with_unicode_only(content):
    """解析JSON文件，只进行unicode编码转义，不进行其他JSON转义
    
    Args:
        content: JSON文件内容
        
    Returns:
        dict: 解析后的键值对
    """
    result = {}
    JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
    
    for match in JSON_KEY_VALUE_PATTERN.finditer(content):
        key = match.group(1)
        value = match.group(2)
        
        # 处理 Unicode 转义序列（如\u963f），但保留\n等转义字符
        # 先将\n、\t等常见转义字符暂时替换为占位符
        temp_value = value.replace('\\n', '__NEWLINE__')
        temp_value = temp_value.replace('\\t', '__TAB__')
        temp_value = temp_value.replace('\\r', '__CARRIAGE__')
        # 处理 Unicode 转义序列
        temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
        # 恢复占位符为原始转义字符
        temp_value = temp_value.replace('__NEWLINE__', '\\n')
        temp_value = temp_value.replace('__TAB__', '\\t')
        temp_value = temp_value.replace('__CARRIAGE__', '\\r')
        # 处理引号，将 \" 替换为 "
        temp_value = temp_value.replace('\\"', '"')
        
        # 跳过 _comment 键
        if key == '_comment':
            continue
            
        result[key] = temp_value
    
    return result

# 读取jojo_zh_cn.json文件
with open('jojo_zh_cn.json', 'r', encoding='utf-8-sig') as f:
    content = f.read()

# 解析JSON
data = _parse_json_with_unicode_only(content)
print(f'Total entries: {len(data)}')

# 检查hamonSkill.sendo_overdrive.desc条目
if 'hamonSkill.sendo_overdrive.desc' in data:
    value = data['hamonSkill.sendo_overdrive.desc']
    print(f'Key: hamonSkill.sendo_overdrive.desc')
    print(f'Value: {repr(value)}')
    print(f'Value decoded: {value}')
    print(f'Value length: {len(value)}')
    # 检查是否包含换行符
    if '\\n' in value:
        print('Contains \\n')
        parts = value.split('\\n')
        print(f'Number of parts: {len(parts)}')
        for i, part in enumerate(parts):
            print(f'Part {i}: {repr(part)}')
else:
    print('Key not found')

# 检查所有包含\\n的条目
print('\nEntries with \\n:')
for key, value in data.items():
    if '\\n' in value:
        print(f'Key: {key}')
        print(f'Value: {repr(value[:100])}')
        break