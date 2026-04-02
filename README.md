# Modpack Localizer

[![Latest Release](https://img.shields.io/github/v/release/blibilijojo/Modpack-Localizer)](https://github.com/blibilijojo/Modpack-Localizer/releases/latest)

Minecraft 整合包本地化工具，面向中文翻译场景，提供从语言提取、词典决策、AI 补全到资源包构建的完整图形化工作流。

## 项目定位

`Modpack Localizer` 是一个桌面 GUI 应用（`tkinter + ttkbootstrap`），用于处理 Minecraft 模组与任务系统文本的汉化工作。  
项目目标是把重复性很高的翻译流程标准化，同时保留人工校对与可追溯的编辑体验。

适用场景：

- 批量处理 `mods` 目录里的语言文件（`en_us.json` / `en_us.lang`）
- 处理任务系统文件（FTB Quests / Better Questing）
- 借助个人词典、社区词典与 AI 服务加速翻译
- 输出可直接使用的资源包（文件夹或 zip）

## 当前主要能力

- 多项目标签页工作区，支持会话恢复
- 三类流程入口：
  - 模组汉化
  - 模组搜索（Modrinth / CurseForge）后下载并进入汉化
  - 任务汉化（FTB Quests / Better Questing）
- 翻译工作台：
  - 命名空间维度查看与编辑
  - 查找替换、撤销重做
  - 项目存档/读档（`.sav`）
- 翻译来源整合：
  - 模组自带中文
  - 个人词典
  - 第三方汉化包
  - 社区词典（`Dict-Sqlite.db`）
  - AI 翻译补全
- 资源包构建：
  - 保持模板文件结构和键顺序
  - 支持 `pack.mcmeta` 描述模板占位符
  - 输出 zip 或目录
- 工程化能力：
  - 自动更新检查
  - 日志与错误记录
  - GitHub 下载/上传与 PR 工作流辅助界面

## 技术栈

- Python 3
- tkinter / ttkbootstrap
- openai（兼容 OpenAI API 的服务接入）
- requests
- sqlite3（词典读取）
- ftb-snbt-lib（任务文件处理）

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 启动程序

```bash
python main.py
```

### 3) 首次建议配置

在程序设置中优先检查：

- AI 服务（接口地址、模型、密钥）
- 输出目录
- 社区词典路径（如需）
- CurseForge API Key（如需使用 CurseForge 搜索）

## 典型使用流程

### 模组汉化

1. 选择 `模组汉化`
2. 设置 `Mods 文件夹` 和 `输出文件夹`
3. 执行提取与翻译决策
4. 在工作台校对
5. 选择预案并生成资源包

### 模组搜索汉化

1. 选择 `模组搜索`
2. 在 Modrinth / CurseForge 搜索并选版本
3. 下载 jar 后自动进入汉化流程
4. 校对并生成资源包

### 任务汉化

1. 选择 `任务汉化`
2. 指定实例目录
3. 提取任务文本并进入工作台
4. 完成后回写任务文件并产出语言数据

## 项目结构（当前）

```text
Modpack-Localizer/
├─ core/        # 提取、翻译决策、构建、工作流编排
├─ gui/         # 主界面、工作台、设置面板、GitHub 相关 UI
├─ services/    # AI 翻译、GitHub 服务、文本修正服务
├─ utils/       # 配置、日志、会话、更新、重试等工具
├─ main.py      # 程序入口
└─ updater.py   # 更新器
```

## 版本

- 程序界面版本号从 `_version.py` 读取（应用内为动态来源，不需要改 README）
- 文档显示使用 GitHub 最新发布徽章（顶部 `Latest Release`），自动跟随最新 Release

## 贡献与反馈

- Issue: <https://github.com/blibilijojo/Modpack-Localizer/issues>
- Repository: <https://github.com/blibilijojo/Modpack-Localizer>

欢迎通过 Issue / PR 提交 bug、改进建议或功能补充。

## 许可证

MIT License，详见 `LICENSE`。
