import re

# 测试正则表达式
pattern = re.compile(r'\\.')
test_str = r'\n'
print('Test string:', repr(test_str))
print('Test string actual:', test_str)
match = pattern.search(test_str)
if match:
    print('Match:', repr(match.group()))
else:
    print('No match')

# 测试JSON键值对模式
json_pattern = re.compile(r'"([^"]+)":\s*"((?:\\.|[^\\"])*)"', re.DOTALL)
test_json = r'"key":"test\nvalue"'
print('\nJSON test string:', repr(test_json))
print('JSON test string actual:', test_json)
matches = json_pattern.finditer(test_json)
for match in matches:
    print('JSON match found:')
    print('Key:', match.group(1))
    print('Value:', match.group(2))