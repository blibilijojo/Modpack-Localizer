# Modpack Localizer Pro (整合包汉化工坊)

<p align="center">
  <img src="https://via.placeholder.com/400x200?text=Modpack+Localizer+Pro" alt="Modpack Localizer Pro Logo" width="400" height="200">
</p>

<p align="center">
  <strong>专业的 Minecraft 整合包汉化工作台</strong>
</p>

<p align="center">
  <a href="https://github.com/blibilijojo/Modpack-Localizer/releases/latest">
    <img src="https://img.shields.io/github/v/release/blibilijojo/Modpack-Localizer" alt="Latest Release">
  </a>
  <a href="https://github.com/blibilijojo/Modpack-Localizer/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/blibilijojo/Modpack-Localizer" alt="License">
  </a>
  <a href="https://github.com/blibilijojo/Modpack-Localizer/issues">
    <img src="https://img.shields.io/github/issues/blibilijojo/Modpack-Localizer" alt="Issues">
  </a>
</p>

## 📋 项目概述

Modpack Localizer Pro 是一款专为 Minecraft 整合包作者和汉化者设计的专业汉化工作台。它集智能 AI 翻译、丰富的社区资源整合以及精细的手动校对功能于一体，提供从一键自动化翻译到完整项目管理的全流程本地化解决方案。

无论是处理单个模组还是大型整合包，无论是模组文本还是复杂的任务系统，Modpack Localizer Pro 都能轻松应对，让汉化工作变得更加简单、高效。

## ✨ 核心功能

### 🎯 双工作流设计

- **模组汉化**: 传统模式，扫描所有模组，生成完整的汉化资源包
- **任务汉化**: 专业模式，专门处理 **FTB Quests (.snbt)** 和 **Better Questing (.json)** 任务文件，实现无损汉化并自动生成语言文件

### 🧠 智能翻译决策引擎

- 按优先级顺序填充译文：**模组自带 > 个人词典 > 第三方汉化包 > 社区词典**
- 最大限度利用高质量人工翻译资源，减少重复工作
- 智能冲突解决机制，确保翻译质量

### 💻 交互式翻译工作台

- 三栏式专业布局（主-从-编辑器），操作直观高效
- **一键 AI 翻译**，快速填充未翻译条目
- 支持**项目存读档 (.sav)**，随时保存和恢复工作进度
- 内置**撤销/重做**功能，放心修改
- 便捷快捷键支持（`Enter` / `Ctrl+Enter`），实现条目间快速跳转
- 实时统计翻译进度，清晰展示翻译完成情况

<p align="center">
  <img src="https://via.placeholder.com/1200x800?text=翻译工作台截图" alt="翻译工作台截图" width="1200" height="800">
</p>

### 📁 多标签页项目管理

- 支持同时打开多个汉化项目，自由切换
- 自动保存会话状态，下次启动时恢复未关闭的标签页
- 每个项目标签页独立管理，互不干扰

### 📚 全面的词典支持

- **个人词典**: 随时保存满意的翻译，实现知识积累与复用
- **社区词典**: 支持加载社区维护的 `Dict-Sqlite.db` 词典文件
- 内置词典编辑器，方便管理和维护
- 图形化词典查询工具，支持原文/译文双向模糊搜索

<p align="center">
  <img src="https://via.placeholder.com/800x600?text=词典查询工具截图" alt="词典查询工具截图" width="800" height="600">
</p>

### 📦 灵活的资源包生成

- 支持为不同 Minecraft 版本生成对应的 `pack_format`
- 通过**动态占位符**（如 `{timestamp}`, `{ai_count}`, `{human_percent}`）自动生成统计信息
- 强大的**预案管理系统**，允许保存多套资源包配置方案
- 支持直接生成 ZIP 文件或文件夹形式的资源包

### 🤖 稳健的 AI 服务

- 支持所有**兼容 OpenAI API**的服务提供商
- **多密钥轮换**和**自动冷却机制**，有效应对 API 速率限制
- 可自定义 API 端点、Prompt、模型、并发线程数等高级参数
- 智能批量翻译，支持自定义批次大小和超时设置

### 🔧 便捷的全局工具

- 图形化的**个人词典编辑器**
- **自动更新检查**，始终保持程序最新
- 专业详细的日志系统 (`ModpackLocalizer.log`)
- 全局查找替换功能，支持正则表达式

## 🚀 快速开始

### 环境要求

- Python 3.9 或更高版本
- Windows 10/11 操作系统
- 至少 2GB 可用内存
- 稳定的网络连接（用于 AI 翻译和更新检查）

### 安装步骤

1. **下载项目**
   - 从 [GitHub Releases](https://github.com/blibilijojo/Modpack-Localizer/releases/latest) 下载最新版本的发布包
   - 或克隆仓库：
     ```bash
     git clone https://github.com/blibilijojo/Modpack-Localizer.git
     cd Modpack-Localizer
     ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **运行程序**
   ```bash
   python main.py
   ```

4. **首次配置**
   - 程序启动后，在设置面板中配置您的兼容 OpenAI API 密钥
   - 支持多个密钥，可用换行或逗号分隔

## 📖 使用指南

### 工作流选择

程序支持两种主要的汉化工作流，您可以根据需求选择：

#### A) 模组汉化流程

1. 在主界面选择 **模组汉化** 选项
2. 设置您的 `Mods 文件夹` 和 `输出文件夹`
3. 点击 **"开始处理"** 按钮，程序将扫描所有模组并提取文本
4. 在弹出的**翻译工作台**中完成翻译和校对
5. 点击工作台右下角的 **"完成并生成资源包"**
6. 在弹出的对话框中选择一个**生成预案**，即可在输出文件夹中找到您的汉化包

#### B) 任务汉化流程

1. 在主界面选择 **任务汉化** 选项
2. 设置一个简短的英文**整合包名称**
3. 点击 **"浏览..."**，选择您的 `.minecraft` 实例文件夹
4. 程序会自动发现任务文件，点击 **"开始处理"** 提取文本
5. 在弹出的**翻译工作台**中完成翻译和校对
6. 点击工作台右下角的 **"完成"**，程序会自动汉化并覆盖原任务文件（同时创建备份），并生成所需的语言文件

### 高级功能

- **项目存读档**: 在翻译工作台中，随时保存当前项目为 `.sav` 文件，方便后续继续编辑
- **AI 辅助翻译**: 点击 **"工具 > AI 翻译所有待译项"** 使用 AI 批量翻译未翻译的文本
- **词典管理**: 在主菜单 **"工具 > 管理个人词典"** 中管理您的个人词典
- **查找替换**: 使用快捷键 `Ctrl+F` 或点击 **"编辑 > 查找和替换"** 打开查找替换对话框

## 🛠️ 技术栈

| 类别 | 技术/框架 | 用途 |
|------|-----------|------|
| 开发语言 | Python 3 | 主要开发语言 |
| GUI 框架 | tkinter + ttkbootstrap | 图形用户界面 |
| AI 翻译 | openai Python库 | 兼容 OpenAI API 的翻译服务 |
| 项目管理 | JSON | 配置和项目文件 |
| 资源处理 | Python 标准库 | 文件和资源处理 |
| 日志系统 | Python logging | 程序日志记录 |
| 错误处理 | 自定义错误处理器 | 异常捕获和日志记录 |
| 依赖管理 | pip | 第三方库管理 |

## 📁 项目结构

```
Modpack-Localizer/
├── core/             # 核心功能模块
│   ├── data_aggregator.py   # 数据聚合器
│   ├── decision_engine.py   # 翻译决策引擎
│   ├── orchestrator.py      # 工作流协调器
│   ├── pack_builder.py      # 资源包生成器
│   ├── quest_converter.py   # 任务文件转换器
│   ├── workflow.py          # 工作流管理
│   └── models.py            # 数据模型
├── gui/              # 图形用户界面
│   ├── main_window.py       # 主窗口
│   ├── translation_workbench.py  # 翻译工作台
│   ├── tab_settings_unified.py   # 统一设置面板
│   ├── custom_widgets.py    # 自定义组件
│   └── dialogs.py           # 对话框组件
├── services/         # 外部服务
│   └── ai_translator.py     # AI 翻译服务
├── utils/            # 工具函数
│   ├── config_manager.py    # 配置管理
│   ├── dictionary_searcher.py  # 词典搜索
│   ├── error_logger.py      # 错误日志记录
│   └── update_checker.py    # 更新检查
├── logs/             # 程序日志文件夹
├── error_logs/       # 错误日志文件夹
├── main.py           # 程序入口
├── README.md         # 项目说明
├── requirements.txt  # 依赖列表
├── _version.py       # 版本信息
└── config.example.json  # 配置文件模板
```

## ⚙️ 配置说明

### 主要配置项

| 配置项 | 说明 |
|--------|------|
| `api_keys` | 兼容 OpenAI API 的密钥列表 |
| `api_endpoint` | 自定义 API 服务器地址（可选） |
| `model` | 默认使用的 AI 模型 |
| `mods_dir` | 默认 Mods 文件夹路径 |
| `output_dir` | 默认输出文件夹路径 |
| `community_dict_path` | 社区词典文件路径 |
| `pack_settings_presets` | 资源包生成预案配置 |
| `ai_batch_size` | AI 翻译批次大小 |
| `ai_max_threads` | AI 翻译最大并发线程数 |

### 配置文件位置

配置文件位于程序运行目录下的 `config.json`，首次运行时会自动创建。您可以通过设置面板修改配置，也可以直接编辑该文件。

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！如果您有任何建议或发现了 bug，请到 GitHub 仓库提交。

### 开发环境设置

1. 克隆仓库：`git clone https://github.com/blibilijojo/Modpack-Localizer.git`
2. 安装依赖：`pip install -r requirements.txt`
3. 运行程序：`python main.py`

### 代码规范

- 遵循 PEP 8 代码风格
- 使用类型提示
- 添加适当的注释
- 提交前运行代码检查

### 提交流程

1. Fork 仓库
2. 创建功能分支：`git checkout -b feature/AmazingFeature`
3. 提交更改：`git commit -m 'Add some AmazingFeature'`
4. 推送到分支：`git push origin feature/AmazingFeature`
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证授权，详情请查看 [LICENSE](LICENSE) 文件。

### 第三方资源

- **[Minecraft-Mod-Language-Package](https://github.com/CFPAOrg/Minecraft-Mod-Language-Package)** by CFPAOrg - 社区词典数据来源
- **[i18n-Dict-Extender](https://github.com/VM-Chinese-translate-group/i18n-Dict-Extender)** by VM-Chinese-translate-group - 词典聚合应用

## 📞 联系方式

- GitHub Issues: https://github.com/blibilijojo/Modpack-Localizer/issues
- 项目主页: https://github.com/blibilijojo/Modpack-Localizer

## 🙏 致谢

感谢所有为项目做出贡献的开发者和用户！

## 📝 免责声明

本工具仅供个人学习和非商业用途使用。使用本工具进行汉化时，请遵守相关模组和资源的许可证协议。

---

**Modpack Localizer Pro** - 让 Minecraft 整合包汉化更简单、更高效！ 🎉