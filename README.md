# Modpack Localizer Pro (整合包汉化工坊)

<div align="center">

**[English](#english-version) | [简体中文](#-简体中文版)**

</div>

---

## 🌎 简介

**一款专业的 Minecraft 整合包汉化工作台。它将强大的 AI 翻译、社区资源整合与精细的手动校对、项目存读档功能深度结合，为整合包作者和玩家提供从一键自动化到完整项目管理的全流程本地化体验。**

<p align="center">
  <img width="852" alt="应用主界面" src="https://github.com/user-attachments/assets/dc267e88-7e56-4242-b750-babfca545a2a" />
</p>

## 📸 功能展示 (Feature Showcase)

<div align="center">

| 手动翻译工作台 (Manual Translation Workbench) | 社区词典查询 (Community Dictionary Search) |
| :----------------------------------------------------------: | :----------------------------------------------------------: |
| *专业的三栏式布局，方便您按模组对上千条文本进行高效的审查、编辑和校对。* | *强大的原文/译文双向模糊搜索，快速找到您需要的参考翻译。* |
| <img width="1102" alt="手动翻译工作台" src="https://github.com/user-attachments/assets/81e8a99e-cdd3-4442-8bd8-649da76b7675" /> | <img width="802" alt="社区词典查询" src="https://github.com/user-attachments/assets/e78dee9a-92d8-44c2-b3f3-20cc744e81da" /> |

</div>

## ✨ 功能特性

- **工作台模式**: 新增“手动校对”模式，提供专业的“主-从-编辑器”三栏式布局，让您对每一条翻译进行精细审查和修改。
- **项目存读档**: 在手动模式下，可随时将工作进度保存为 `.sav` 项目文件，之后通过主菜单“工具”->“加载项目”恢复工作，防止心血白费。
- **全局词典查询**: 从主菜单或手动工作台中随时启动独立词典查询工具，支持原文/译文双向智能模糊搜索。
- **🚀 智能翻译引擎**: 集成 Google Gemini API，提供高质量、可配置的 AI 翻译服务。
- **🧩 多格式兼容**: 自动检测并处理模组中的 `.json` 和 `.lang` 语言文件，并采用 `.json` 优先的策略处理冲突。
- **📚 社区包叠加**: 支持加载多个社区汉化包，并按优先级顺序智能合并，充分利用已有翻译成果。
- **🛠️ AI 参数调优**: 可自定义 Prompt、AI 模型、并发线程数、重试次数等高级参数。
- **⚙️ 灵活的资源包设置**: 轻松配置汉化包所支持的游戏版本、描述和自定义图标。
- **🖥️ 现代化图形界面**: 基于 `ttkbootstrap` 构建，提供清晰、美观、跨平台的图形用户界面。
- **📄 专业日志系统**: 自动生成详细的日志文件 (`ModpackLocalizer.log`)，便于开发者和用户排查问题。

## 🚀 如何使用

1.  从 **[Releases (发行版) 页面](https://github.com/blibilijojo/Modpack-Localizer/releases)** 下载最新的已打包版本。
2.  解压并运行主程序。
3.  在 **`AI 服务`** 选项卡中，填入您的 Google Gemini API 密钥。
4.  在 **`一键汉化`** 选项卡中，设置您的 `Mods 文件夹` 和 `输出文件夹`。
5.  (可选) 添加您已有的社区汉化包，并通过“上移/下移”调整优先级。
6.  在 **`工作模式`** 中，选择“AI 自动翻译”（全自动）或“手动校对和翻译”（启动工作台）。
7.  点击主界面的 **“--- 从头扫描并开始汉化 ---”** 按钮，开始您的工作流！

## 📄 许可证

本项目采用 [MIT 许可证](./LICENSE) 授权。

---
---

# English Version

## 🌎 Introduction

**A professional workbench for Minecraft modpack localization. It deeply integrates powerful AI translation and community resources with fine-grained manual proofreading and project management (save/load), providing a full-circle localization experience for both modpack creators and players.**

<p align="center">
  <img width="852" alt="Main Application UI" src="https://github.com/user-attachments/assets/dc267e88-7e56-4242-b750-babfca545a2a" />
</p>

## 📸 Feature Showcase

<div align="center">

| Manual Translation Workbench                                 | Community Dictionary Search                                    |
| :----------------------------------------------------------: | :----------------------------------------------------------: |
| *A professional three-pane layout for efficiently reviewing, editing, and proofreading thousands of entries, sorted by mod.* | *Powerful, fuzzy, bidirectional search to quickly find the reference translations you need.* |
| <img width="1102" alt="Manual Translation Workbench" src="https://github.com/user-attachments/assets/81e8a99e-cdd3-4442-8bd8-649da76b7675" /> | <img width="802" alt="Community Dictionary Search" src="https://github.com/user-attachments/assets/e78dee9a-92d8-44c2-b3f3-20cc744e81da" /> |

</div>

## ✨ Features

- **Workbench Mode**: A new "Manual Proofreading" mode provides a professional three-pane layout (Master-Detail-Editor) for meticulous review and modification of every translation entry.
- **Project Save/Load**: In manual mode, save your entire workflow (including un-translated items) as a `.sav` project file. Reload it anytime from the "Tools" menu to resume your work.
- **Global Dictionary Search**: Launch a standalone dictionary tool anytime. It supports fuzzy search for both English-to-Chinese and Chinese-to-English lookups and is integrated into the workbench.
- **🚀 Intelligent Translation Engine**: Integrates with the Google Gemini API to provide high-quality, configurable AI translation.
- **🧩 Multi-Format Support**: Automatically detects and processes `.json` and `.lang` language files from mods, with a `.json`-first strategy for resolving conflicts.
- **📚 Community Pack Overlay**: Supports loading multiple community translation packs and intelligently merges them based on priority.
- **🛠️ AI Parameter Tuning**: Allows customization of advanced parameters such as prompts, AI models, concurrent threads, and retry attempts.
- **⚙️ Flexible Resource Pack Settings**: Easily configure the target game version, description, and icon for the generated resource pack.
- **🖥️ Modern GUI**: Built with `ttkbootstrap` to provide a clean, beautiful, and cross-platform graphical user interface.
- **📄 Professional Logging System**: Automatically generates a detailed log file (`ModpackLocalizer.log`) for easy troubleshooting.

## 🚀 How to Use

1.  Download the latest packaged version from the **[Releases Page](https://github.com/blibilijojo/Modpack-Localizer/releases)**.
2.  Extract and run the main application.
3.  In the **`AI Service`** tab, enter your Google Gemini API Key(s).
4.  In the **`Translate`** tab (Chinese: `一键汉化`), set your `Mods Folder` and `Output Folder`.
5.  (Optional) Add any existing community translation packs and adjust their priority using the "Move Up/Down" buttons.
6.  In the **`Work Mode`** section, choose "AI Auto-Translate" for a fully automated process or "Manual Proofreading" to launch the workbench.
7.  Click the main **"--- Start Scan & Localize ---"** button and let the magic happen!

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
