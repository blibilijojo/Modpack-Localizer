from services.punctuation_corrector import punctuation_corrector

# 测试场景1：译文包含英文引号
print("测试场景1：译文包含英文引号")
en_text = 'Hello "world"!'
zh_text = '你好 "世界"!'
corrected_text = punctuation_corrector.correct_punctuation(en_text, zh_text)
print(f"原文: {en_text