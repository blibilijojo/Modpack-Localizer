import re
import json

# 模拟extractor.py中的提取逻辑
JSON_KEY_VALUE_PATTERN = re.compile(r'"([^"]+)":\s*"((?:\\.|[^\\"])*)"', re.DOTALL)

def extract_from_text(content: str, file_format: str):
    """从文本内容中提取语言数据"""
    data = {}
    comment_counter = 0
    if file_format == 'json':
        # 始终使用正则表达式解析JSON文件
        for match in JSON_KEY_VALUE_PATTERN.finditer(content):
            key = match.group(1)
            value = match.group(2)
            # 处理Unicode转义序列（如\u963f），但保留\n等转义字符
            import re
            # 先将\n、\t等常见转义字符暂时替换为占位符
            temp_value = value.replace('\\n', '__NEWLINE__')
            temp_value = temp_value.replace('\\t', '__TAB__')
            temp_value = temp_value.replace('\\r', '__CARRIAGE__')
            # 处理Unicode转义序列
            temp_value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), temp_value)
            # 恢复占位符为原始转义字符
            temp_value = temp_value.replace('__NEWLINE__', '\\n')
            temp_value = temp_value.replace('__TAB__', '\\t')
            temp_value = temp_value.replace('__CARRIAGE__', '\\r')
            # 处理引号，将 \" 替换为 "
            temp_value = temp_value.replace('\\"', '"')
            # 忽略_comment条目
            if key != '_comment':
                data[key] = temp_value
    return data

# 读取jojo_zh_cn.json文件
with open('jojo_zh_cn.json', 'r', encoding='utf-8-sig') as f:
    content = f.read()

# 提取数据
data = extract_from_text(content, 'json')
print(f'Total entries extracted: {len(data)}')

# 检查hamonSkill.sendo_overdrive.desc条目
if 'hamonSkill.sendo_overdrive.desc' in data:
    value = data['hamonSkill.sendo_overdrive.desc']
    print(f'Key: hamonSkill.sendo_overdrive.desc')
    print(f'Value: {repr(value)}')
    print(f'Value decoded: {value}')
else:
    print('Key hamonSkill.sendo_overdrive.desc not found')

# 检查是否包含换行符
for key, value in data.items():
    if '\\n' in value:
        print(f'\nFound entry with \\n:')
        print(f'Key: {key}')
        print(f'Value: {repr(value[:100])}')
        break