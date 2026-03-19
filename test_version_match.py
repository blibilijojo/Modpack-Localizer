#!/usr/bin/env python3
# 测试版本匹配功能

from core.extractor import Extractor

# 创建提取器实例
extractor = Extractor()

# 测试数据
test_cases = [
    # 基本测试
    ("1.20.1", "forge", ["1.12.2", "1.16-fabric", "1.16", "1.18-fabric", "1.18", "1.19", "1.20-fabric", "1.20", "1.21-fabric", "1.21"], "1.20"),
    # 测试fabric加载器
    ("1.20.1", "fabric", ["1.12.2", "1.16-fabric", "1.16", "1.18-fabric", "1.18", "1.19", "1.20-fabric", "1.20", "1.21-fabric", "1.21"], "1.20-fabric"),
    # 测试新版本（不在列表中）
    ("1.22", "forge", ["1.12.2", "1.16-fabric", "1.16", "1.18-fabric", "1.18", "1.19", "1.20-fabric", "1.20", "1.21-fabric", "1.21"], "1.21"),
    # 测试旧版本（不在列表中）
    ("1.15", "forge", ["1.12.2", "1.16-fabric", "1.16", "1.18-fabric", "1.18", "1.19", "1.20-fabric", "1.20", "1.21-fabric", "1.21"], "1.16"),
    # 测试精确匹配
    ("1.18", "fabric", ["1.12.2", "1.16-fabric", "1.16", "1.18-fabric", "1.18", "1.19", "1.20-fabric", "1.20", "1.21-fabric", "1.21"], "1.18-fabric"),
]

# 运行测试
print("开始测试版本匹配功能...")
print("=" * 80)

for i, (game_version, loaders, github_versions, expected) in enumerate(test_cases):
    result = extractor._match_github_version(game_version, loaders, github_versions)
    status = "✓" if result == expected else "✗"
    print(f"测试 {i+1}: {status}")
    print(f"  游戏版本: {game_version}")
    print(f"  加载器: {loaders}")
    print(f"  预期结果: {expected}")
    print(f"  实际结果: {result}")
    print()

print("=" * 80)
print("测试完成！")
