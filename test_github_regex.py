import re

# 测试github_service.py中的正则表达式
JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)

# 测试字符串
test_str = r'"hamonSkill.sendo_overdrive.desc":"对墙壁或地面施放此攻击，可产生波纹能量波，对区域内的生物和玩家造成伤害。\n作用于地面时，可产生一道狭窄的波纹；若蓄力更久，则会产生范围效果。"'

print('Test string:', test_str)
print('Test string actual:', test_str)

matches = JSON_KEY_VALUE_PATTERN.finditer(test_str)
for match in matches:
    print('Match found:')
    print('Key:', match.group(1))
    print('Value:', match.group(2))
    print('Value repr:', repr(match.group(2)))

# 测试实际的JSON文件内容
with open('jojo_zh_cn.json', 'r', encoding='utf-8-sig') as f:
    content = f.read()
    matches = JSON_KEY_VALUE_PATTERN.finditer(content)
    for match in matches:
        key = match.group(1)
        if key == 'hamonSkill.sendo_overdrive.desc':
            value = match.group(2)
            print('\nFrom file:')
            print('Key:', key)
            print('Value:', repr(value))
            print('Value decoded:', value)
            break