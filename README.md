# Modpack Localizer

[![Latest Release](https://img.shields.io/github/v/release/blibilijojo/Modpack-Localizer)](https://github.com/blibilijojo/Modpack-Localizer/releases/latest)

面向 **Minecraft 整合包 / 模组** 中文本地化场景的桌面工具：从 `mods` 或任务文件中抽取英文文本，按词典与规则做第一轮决策，在图形工作台中校对，并可调用 **兼容 OpenAI API** 的服务批量补译或润色，最后生成可直接使用的 **资源包**（目录或 zip）。

当前界面版本号由 [`_version.py`](_version.py) 提供（例如 `2.7.0`）；通过 Git 标签触发发布构建时，工作流会覆写该文件以与标签一致。

**AI 生成声明：** 本仓库中的部分文档、说明文字或代码在编写与维护过程中使用了生成式人工智能工具辅助；相关内容均须经人工审阅与实测验证，不构成对特定结果或适用场景的保证。使用本软件或引用本仓库内容时，请自行评估风险，并遵守相关法律法规及所接入服务（含 AI 接口）的用户协议。

---

## 功能概览

### 工作区与项目类型

- **多标签页**：每个标签页一个独立项目；关闭程序前会在 [`.session_cache/`](utils/session_manager.py) 下做增量会话缓存，便于下次恢复工作台状态（含懒加载摘要）。
- **模组汉化 (`mod`)**：指定 `mods` 目录与输出目录，执行「提取 → 翻译决策 → 工作台」。
- **模组搜索 (`modsearch`)**：在 **Modrinth / CurseForge** 搜索模组、选择版本并下载 jar，再进入与「模组汉化」相同的后续流程（下载目录等由界面与配置项 `jar_dir` 等配合）。
- **任务汉化 (`quest`)**：在 Minecraft **实例目录** 下自动探测：
  - **FTB Quests**：`config/ftbquests/quests/**/*.snbt`
  - **Better Questing**：`config/betterquesting/DefaultQuests.json`  
  抽取文本后进入工作台，完成后回写任务侧数据（依赖 `ftb-snbt-lib`）。
- **获取我的 GitHub 汉化 PR (`github`)**：配合设置中的仓库与 Token，拉取与你相关的汉化 PR 工作流（见「外部服务」）。

### 翻译与数据流

1. **提取**（[`core/extractor.py`](core/extractor.py)）：扫描 jar/zip 内语言文件（如 `en_us.json`、`en_us.lang`），合并命名空间；可选加载第三方汉化 zip、查询模组元数据（CurseForge / Modrinth，带请求重试）；支持指纹与扫描进度回调。
2. **翻译决策**（[`core/translator.py`](core/translator.py)）：对每条键按固定优先级匹配译文：  
   **原文复制（已像中文则保留）→ 模组自带中文 → 个人词典（按 Key / 按原文）→ 第三方汉化包 → 社区词典（按 Key / 按原文，多版本冲突时择优）**。未命中则标记为待翻译。
3. **工作台**（[`gui/translation_workbench.py`](gui/translation_workbench.py)）：按命名空间浏览与编辑；查找替换、撤销重做、词典搜索、个人词典编辑；可发起 **AI 批量翻译**（`AITranslator`，多密钥队列与冷却）。
4. **综合处理**（[`gui/enhanced_comprehensive_processing.py`](gui/enhanced_comprehensive_processing.py) 等）：支持多种 **翻译模式**（如基础翻译 / 混合 / 润色等），与工作台协同批量更新条目。
5. **资源包构建**（[`core/builder.py`](core/builder.py)）：按模板保持键顺序与结构，生成 `pack.mcmeta`（支持描述模板占位符与统计占位符，见 [`core/orchestrator.py`](core/orchestrator.py) 中默认描述模板），输出文件夹或 zip（`pack_as_zip`）。

### 词典与配置

- **个人词典**：SQLite，默认与可执行文件同目录或当前工作目录下的 `Dict-User.db`（表 `by_key` / `by_origin_name`），由 [`utils/config_manager.py`](utils/config_manager.py) 初始化与读写。
- **社区词典**：在「翻译资源」中指定目录，程序读取该目录下 **`Dict-Sqlite.db`**（只读连接），见 [`core/dictionary_manager.py`](core/dictionary_manager.py)。可配置是否启用按 Key / 按原文匹配及过滤条件（`community_dict_filter` 等）。
- **全局配置**：`config.json`，与 `Dict-User.db` 同基准目录（[`config_manager.APP_DATA_PATH`](utils/config_manager.py)）。首次运行写入默认值；内置 **Minecraft 汉化向** 的 AI 提示词在代码中维护（不再使用配置文件里的旧 `prompt` 字段）。
- **设置窗口**（[`gui/settings_window.py`](gui/settings_window.py)）分页：**通用**、**AI**、**翻译资源**、**外部服务（GitHub）**、**资源包/预案**、**高级**（日志级别、保留天数、GitHub 代理列表等）。

### 其它工程能力

- **日志**：`concurrent-log-handler`、可配置级别与保留策略；未捕获异常写入错误日志（[`utils/error_logger.py`](utils/error_logger.py)）。
- **程序更新**：[`utils/update_checker.py`](utils/update_checker.py) 对比 GitHub Release，下载名为 **`Modpack-Localizer-Pro*.exe`** 的资源；[`updater.py`](updater.py) 在主进程退出后替换 exe 并重启（依赖 `psutil`）。
- **主题**：入口固定为 **ttkbootstrap `litera`**（[`main.py`](main.py)），不再提供运行时主题切换。

---

## 环境要求

- **Python**：本地开发建议 **3.11**（与 [`.github/workflows/nuitka-windows-release.yml`](.github/workflows/nuitka-windows-release.yml) 一致）。
- **操作系统**：GUI 基于 tkinter；发布产物为 **Windows x64 单文件 exe**（Nuitka）。

---

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

### 依赖一览（`requirements.txt`）

| 包 | 用途 |
|----|------|
| `ttkbootstrap` | 界面主题与组件 |
| `requests` | HTTP（API、更新、平台元数据等） |
| `packaging` | 版本解析（词典冲突、更新检查等） |
| `psutil` | 更新器等待/结束主进程 |
| `openai` | 兼容 OpenAI API 的 AI 翻译客户端 |
| `concurrent-log-handler` | 多进程安全日志 |
| `ftb-snbt-lib` | FTB 任务 SNBT 读写 |

---

## 仓库结构（按职责）

```text
Modpack-Localizer/
├── main.py                 # 入口：主题、全局异常钩子、主窗口
├── updater.py              # 独立更新进程：换 exe 并自删除
├── _version.py             # 应用版本字符串
├── requirements.txt
├── core/                   # 领域核心
│   ├── workflow.py         # 提取 / 决策 / 构建 编排
│   ├── extractor.py        # 从 mods 与汉化包抽取语言数据
│   ├── translator.py       # 非 AI 的翻译决策与优先级
│   ├── builder.py          # 资源包输出
│   ├── orchestrator.py     # GUI 侧三阶段流程与 pack 元数据统计
│   ├── dictionary_manager.py
│   ├── quest_converter.py  # 任务格式转换
│   ├── models.py / exceptions.py
│   └── ...
├── gui/                    # 界面
│   ├── main_window.py      # 多标签、项目类型、会话恢复
│   ├── translation_workbench.py
│   ├── settings_window.py + settings_components/
│   ├── quest_workflow_manager.py
│   ├── github_*_ui.py      # GitHub 下载/上传相关
│   ├── enhanced_comprehensive_processing.py
│   └── ...
├── services/
│   ├── ai_translator.py    # OpenAI 兼容 API、多密钥、批量 JSON 翻译
│   ├── github_service.py
│   ├── punctuation_corrector.py / space_remover.py
│   └── ...
├── utils/
│   ├── config_manager.py   # config.json、用户词典、默认配置与迁移
│   ├── session_manager.py  # .session_cache
│   ├── update_checker.py
│   ├── download_manager.py / mod_scan_cache.py / ...
│   └── builtin_secrets.py  # 构建时可注入的内置密钥（见下文）
├── examples/               # 示例脚本（如多线程示例）
└── .github/workflows/      # Nuitka Windows Release（标签 v*）
```

---

## 典型使用流程

### 模组汉化

1. 新建标签页，选择 **模组汉化**，设置 **Mods 文件夹** 与 **输出文件夹**（亦可在设置里配置默认输出目录与 zip）。
2. 在「翻译资源」中配置 **社区词典目录**（放置 `Dict-Sqlite.db`）和可选 **第三方汉化包路径列表**（`community_pack_paths`）。
3. 运行提取与决策，进入 **翻译工作台** 校对；需要时用 **AI 翻译** 或 **综合处理** 补全「待翻译」条目。
4. 选择资源包预案（格式版本、描述模板、图标等），**完成并生成资源包**。

### 模组搜索

1. 选择 **模组搜索**，配置 jar 下载目录与输出目录，在搜索界面选择平台与版本并下载。
2. 下载完成后自动或手动进入与模组汉化相同的提取与工作台流程（具体以界面引导为准）。

### 任务汉化

1. 选择 **任务汉化**，指向 **游戏实例根目录**（含 `config` 的标准布局）。
2. 自动识别 FTB Quests 或 Better Questing，抽取文本后进入工作台；完成后按提示完成回写与产物输出。

### GitHub 汉化协作

1. 在 **设置 → 外部服务** 填写 **仓库地址** 与 **Personal Access Token**（`github_repo` / `github_token`）。
2. 新建项目类型 **获取我的 GitHub 汉化 PR**，按界面步骤拉取或处理 PR 相关工作流。

---

## 构建与发布（维护者）

- 推送 **`v*`** 标签会触发 **Nuitka** 构建，生成 **`Modpack-Localizer-Pro.exe`** 并随 Release 上传。
- 可选在 GitHub Actions 中配置 Secret **`CURSEFORGE_API_KEY`**，构建时生成带内置 CurseForge 密钥的 `utils/builtin_secrets.py`（密钥不写入用户 `config.json`）。细节见 [`BUILTIN_KEY_SECURITY.md`](BUILTIN_KEY_SECURITY.md)。

---

## 常见问题

- **配置文件与词典在哪？** 源码运行时一般在**当前工作目录**；单文件打包后一般在 **exe 所在目录**（与 `get_app_data_path()` 行为一致）。
- **会话缓存能删吗？** 可以删除项目根下 **`.session_cache`** 以清空自动恢复数据（下次启动将不再有上次未保存标签的恢复内容）。
- **CurseForge API：** 官方构建可能已内置密钥；自行从源码运行时若需平台查询，可在 `config.json` 中配置 `curseforge_api_key`（勿将密钥提交到 Git）。

---

## 相关链接与交流

- **Issue**：<https://github.com/blibilijojo/Modpack-Localizer/issues>  
- **仓库**：<https://github.com/blibilijojo/Modpack-Localizer>  
- **软件及模组汉化交流 QQ 群**：`123742027`

## 许可证

MIT License（若仓库根目录提供 `LICENSE` 文件，以该文件全文为准）。
