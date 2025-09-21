# Modpack Localizer Pro (整合包汉化工坊)


</div>

🌎 **简介**

一款专业的 Minecraft 整合包汉化工作台。它将强大的 AI 翻译、社区资源整合与精细的手动校对、项目存读档功能深度结合，为整合包作者和汉化者提供从一键自动化到完整项目管理的全流程本地化体验。

<p align="center">
  <img width="814" alt="应用主界面" src="https://github.com/user-attachments/assets/068ee4e3-270e-45d7-9936-14f22b6ebe11" />
</p>

📸 **核心功能展示 (Feature Showcase)**

<div align="center">

| 交互式翻译工作台 (Interactive Translation Workbench) | 社区词典查询 (Community Dictionary Search) |
| :---: | :---: |
| 专业的三栏式布局，方便您按模组对上千条文本进行高效的审查、编辑和校对。 | 强大的原文/译文双向模糊搜索，快速找到您需要的参考翻译。 |
| <img width="1202" alt="交互式翻译工作台" src="https://github.com/user-attachments/assets/6894888e-36f8-41e4-a66f-b50f16a2d577" /> | <img width="802" alt="社区词典查询" src="https://github.com/user-attachments/assets/6d5130c1-ef48-4a24-866d-097baad6e032" /> |

| 专业任务汉化 (Quest Localization) | 灵活的资源包设置 (Flexible Pack Settings) |
| :---: | :---: |
| 自动检测并处理 FTB Quests 和 Better Questing 任务文件，实现无损汉化。 | 通过预案系统和动态占位符，轻松管理和生成满足不同需求的资源包。 |
| <img width="814" alt="任务汉化界面" src="https://github.com/user-attachments/assets/e536ce0b-e65e-49c0-9e8b-f933d022782b" /> | <img width="1202" alt="资源包设置" src="https://github.com/user-attachments/assets/a42d533c-7deb-4fee-b125-a0c7ffb469e1" /> |

</div>

✨ **详细特性 (Detailed Features)**

*   **双工作流设计**:
    *   **模组汉化**: 传统模式，扫描所有模组，生成一个完整的汉化资源包。
    *   **任务汉化**: 专业模式，专门处理 **FTB Quests (.snbt)** 和 **Better Questing (.json)** 的任务文件，实现无损汉化并自动生成语言文件。

*   **智能翻译决策引擎**:
    *   自动按 **个人词典 > 模组自带 > 第三方汉化包 > 社区词典** 的优先级顺序填充译文，最大限度地利用高质量的人工翻译资源。

*   **强大的交互式翻译工作台**:
    *   提供“主-从-编辑器”三栏式专业布局，操作直观高效。
    *   **一键 AI 翻译**，快速为所有未翻译条目填充内容。
    *   支持**项目存读档 (`.sav`)**，随时保存和恢复您的工作进度。
    *   内置**撤销/重做**功能，放心大胆地进行修改。
    *   便捷的快捷键（`Enter` / `Ctrl+Enter`）支持，实现条目间的快速跳转。

*   **全面的词典支持**:
    *   **个人词典**: 可随时将满意的翻译存入个人词典，实现知识的积累与复用，拥有最高匹配优先级。
    *   **社区词典**: 支持加载社区维护的 `Dict-Sqlite.db` 词典文件，并提供独立的图形化查询工具。

*   **灵活的资源包生成**:
    *   支持为不同 Minecraft 版本生成对应的 `pack_format`。
    *   通过**动态占位符**（如 `{timestamp}`, `{ai_count}`, `{human_percent}`）自动生成包含统计信息的简介和文件名。
    *   强大的**预案管理系统**，允许您保存多套资源包配置方案。

*   **稳健的 AI 服务**:
    *   集成 Google Gemini API，提供高质量的翻译。
    *   支持**多密钥轮换**和**自动冷却机制**，有效应对 API 速率限制。
    *   可自定义 Prompt、模型、并发线程数等高级参数。

*   **便捷的全局工具**:
    *   图形化的**个人词典编辑器**。
    *   **自动更新检查**，始终保持程序最新。
    *   专业详细的日志系统 (`ModpackLocalizer.log`)，便于排查问题。

🚀 **如何使用 (How to Use)**

1.  从 **[Releases (发行版) 页面](https://github.com/blibilijojo/Modpack-Localizer/releases/latest)** 下载最新的 `Modpack-Localizer-Pro-vX.X.X.exe` 文件。
2.  程序为单文件绿色版，双击即可运行。
3.  在 **AI 服务** 选项卡中，填入您的 Google Gemini API 密钥（支持每行一个，填入多个）。
4.  根据您的需求，选择以下工作流之一：

    #### A) 模组汉化流程
    1.  在 **模组汉化** 选项卡中，设置您的 `Mods 文件夹` 和 `输出文件夹`。
    2.  (可选) 添加社区词典文件和任何第三方汉化包。
    3.  点击 **"开始汉化流程"** 按钮。
    4.  在弹出的**翻译工作台**中完成翻译和校对。
    5.  点击工作台右下角的 **"完成并生成资源包"**。
    6.  在弹出的对话框中选择一个**生成预案**，即可在输出文件夹中找到您的汉化包。

    #### B) 任务汉化流程
    1.  切换到 **任务汉化** 选项卡。
    2.  设置一个简短的英文**整合包名称**。
    3.  点击 **"浏览并自动检测..."**，选择您的 `.minecraft` 实例文件夹。
    4.  程序会自动发现任务文件，此时点击 **"提取文本并打开工作台"**。
    5.  在弹出的**翻译工作台**中完成翻译和校对。
    6.  点击工作台右下角的 **"完成并生成任务文件"**。程序会自动汉化并覆盖原任务文件（同时创建备份），并生成所需的语言文件。

❤️ **鸣谢与版权 (Acknowledgements & Copyright)**

本项目的实现离不开以下优秀开源项目和社区提供的宝贵数据资源，在此表示衷心的感谢！

*   **[Minecraft-Mod-Language-Package](https://github.com/CFPAOrg/Minecraft-Mod-Language-Package)** by CFPAOrg
    *   该项目是社区词典数据的核心数据来源。它收集并维护了海量高质量的模组汉化文件，为本工具的词典功能提供了坚实的数据基础。
*   **[i18n-Dict-Extender](https://github.com/VM-Chinese-translate-group/i18n-Dict-Extender)** by VM-Chinese-translate-group
    *   该项目是一个强大的词典聚合应用，它将来自多个社区（如 CFPA）的翻译成果高效地编译成本项目所使用的 `Dict-Sqlite.db` 数据库格式。
    *   **版权声明**: 本项目使用的社区词典数据 `Dict-Sqlite.db` 源自于 `i18n-Dict-Extender` 项目的构建产物。根据其上游声明，该数据遵循 **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** 协议。

📄 **许可证 (License)**

本项目自身的源代码采用 **[MIT 许可证](LICENSE)** 授权。