import json
import re

# 读取文件
with open('e:\\py\\我的世界\\Modpack-Localizer\\en_us.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 递归计算所有字符串值的单词数
total_words = 0
string_values = []

# 递归遍历所有值
def process_value(value):
    global total_words
    if isinstance(value, dict):
        for v in value.values():
            process_value(v)
    elif isinstance(value, list):
        for v in value:
            process_value(v)
    elif isinstance(value, str):
        # 计算单词数（简单按空格分割）
        words = len(value.split())
        total_words += words
        string_values.append(value)

process_value(data)

# 计算平均值和其他统计信息
avg_words_per_string = total_words / len(string_values) if string_values else 0

# 计算不同长度范围的字符串数量
short_strings = len([s for s in string_values if len(s.split()) <= 5])
medium_strings = len([s for s in string_values if 6 <= len(s.split()) <= 20])
long_strings = len([s for s in string_values if len(s.split()) > 20])

# 打印统计信息
print(f"总字符串数量: {len(string_values)}")
print(f"总单词数: {total_words}")
print(f"平均每字符串单词数: {avg_words_per_string:.2f}")
print(f"短字符串 (<=5个单词): {short_strings} ({short_strings/len(string_values)*100:.1f}%)")
print(f"中字符串 (6-20个单词): {medium_strings} ({medium_strings/len(string_values)*100:.1f}%)")
print(f"长字符串 (>20个单词): {long_strings} ({long_strings/len(string_values)*100:.1f}%)")

# 计算AI翻译批次建议
total_items = len(string_values)

# 建议每批次单词数（基于常见AI模型的上下文窗口）
# 例如，GPT-3.5-turbo支持约16k tokens，考虑到中英文翻译，每批次建议1000-2000个单词
print(f"\n基于文件分析的AI翻译批次建议：")
print(f"每批次单词数建议：2000")
print(f"预计批次数量：{total_words // 2000 + 1}")
