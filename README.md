# Modpack Localizer Pro (整合包汉化工坊)

<div align="center">

**[English](#english-version) | [简体中文](#-简体中文版)**

</div>

---

## 🌎 简介

**Modpack Localizer Pro** 是一款专业的 Minecraft 整合包汉化工具，旨在通过 AI 翻译和社区资源叠加，为整合包作者和玩家提供一键式的本地化解决方案。它能够智能处理模组中的 `.json` 和 `.lang` 语言文件，并允许用户深度自定义 AI 翻译的各项参数。

<p align="center">
  <!-- 强烈建议您截一张软件运行的图片，上传到图床（例如 https://imgur.com/），然后把链接替换到下面 -->
  <img src="[https://i.imgur.com/your_screenshot_url.png](https://github.com/user-attachments/assets/70b5f5d1-1773-405d-aa87-18459b23fce1)" alt="应用截图" width="700"/>
</p>

## ✨ 功能特性

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
6.  点击主界面的 **“--- 开始智能汉化更新 ---”** 按钮，等待流程完成！

## 📄 许可证

本项目采用 [MIT 许可证](./LICENSE) 授权。

---
---

## English Version

## 🌎 Introduction

**Modpack Localizer Pro** is a professional localization tool for Minecraft modpacks, designed to provide a one-click localization solution for modpack creators and players through AI translation and community resource overlays. It intelligently handles both `.json` and `.lang` language files from mods and allows users to deeply customize various AI translation parameters.

<p align="center">
  <img src="[https://i.imgur.com/your_screenshot_url.png](https://github.com/user-attachments/assets/70b5f5d1-1773-405d-aa87-18459b23fce1)" alt="Application Screenshot" width="700"/>
</p>

## ✨ Features

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
4.  In the **`Translate`** tab, set your `Mods Folder` and `Output Folder`.
5.  (Optional) Add any existing community translation packs and adjust their priority using the "Move Up/Down" buttons.
6.  Click the main **"--- Start Smart Localization ---"** button and wait for the process to complete!

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
