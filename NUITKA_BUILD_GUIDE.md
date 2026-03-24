# Nuitka 构建指南

本指南介绍如何使用 Nuitka 编译您的 Python 项目为可执行文件。

## 什么是 Nuitka？

Nuitka 是一个 Python 编译器，可以将 Python 代码转换为 C++ 代码，然后编译成原生可执行文件。相比 PyInstaller，它有以下优势：

- **更好的性能**：编译后的代码运行更快
- **更好的兼容性**：支持更多 Python 特性
- **代码保护**：源代码被编译成 C++，更难反编译
- **跨平台**：支持 Windows、macOS 和 Linux

## 已创建的工作流文件

### 1. `nuitka-build.yml` - 多平台构建
- 支持 Windows、Linux、macOS
- 自动上传构建产物到 GitHub Actions
- 适合测试跨平台兼容性

### 2. `nuitka-windows-release.yml` - Windows 发布版本
- 专门针对 Windows 平台优化
- 包含产品信息和版本信息
- 自动创建 GitHub Release

### 3. `README-Nuitka-Examples.yml` - 配置示例
- 包含各种 Nuitka 配置示例
- 可作为参考文档使用

## 使用方法

### 基本使用

1. **推送到 Git 仓库**
   ```bash
   git add .github/workflows/nuitka-*.yml
   git commit -m "Add Nuitka build workflows"
   git push
   ```

2. **触发构建**
   - **自动触发**: 创建以 `v` 开头的标签 (例如 `v1.0.0`)
   - **手动触发**: 在 GitHub Actions 页面手动运行工作流

3. **获取构建产物**
   - 在 GitHub Actions 页面找到对应的构建任务
   - 下载 Artifacts 中的可执行文件

### 本地测试

如果您想在本地测试 Nuitka 构建，可以安装 Nuitka：

```bash
pip install nuitka
```

然后使用以下命令构建：

```bash
# 基本构建
python -m nuitka --standalone --enable-plugin=tk-inter main.py

# 带优化的完整构建
python -m nuitka --standalone \
  --enable-plugin=tk-inter \
  --include-package=gui \
  --include-package=services \
  --include-package=utils \
  --include-package=core \
  --product-name="Modpack-Localizer-Pro" \
  --product-version="1.0.0" \
  --windows-icon-from-ico=gui/resources/icon.ico \
  main.py
```

## 配置说明

### 核心参数

- **`script-name`**: 主程序入口文件 (例如 `main.py`)
- **`mode`**: 构建模式
  - `standalone`: 独立可执行文件 (推荐)
  - `app`: 应用程序包 (macOS 使用)
  - `module`: Python 模块
- **`enable-plugins`**: 启用的插件
  - `tk-inter`: TkInter GUI 支持
  - `pyside6`: PySide6 支持
  - `pyqt6`: PyQt6 支持

### 产品信息

```yaml
product-name: Modpack-Localizer-Pro
product-version: ${{ github.ref_name }}
company-name: Modpack-Localizer
file-description: Modpack Localizer Application
copyright: Modpack-Localizer
```

### 包含包和数据

```yaml
include-package: gui
include-package: services
include-package: utils
include-package: core

include-data-file: |
  requirements.txt=requirements.txt

include-data-dir: |
  assets=assets
  locales=locales
```

### Windows 特定选项

```yaml
windows-icon-from-ico: gui/resources/icon.ico
windows-uac-admin: false
```

## 常见问题

### Q: 构建失败怎么办？

A: 检查以下几点：
1. 确保所有依赖都已安装 (`pip install -r requirements.txt`)
2. 查看 Nuitka 的错误输出，通常会指出缺少哪些模块
3. 使用 `include-package` 或 `nuitka-args` 包含缺失的包

### Q: 如何减小可执行文件体积？

A: 使用以下方法：
1. 排除不需要的包：`--nofollow-imports --follow-import-to=<package>`
2. 启用优化：`--optimize-all --no-debug-output`
3. 使用 `--python-flag=no_site` 禁用 site 模块

### Q: 如何处理数据文件？

A: 使用 `include-data-file` 和 `include-data-dir` 选项：
```yaml
include-data-file: |
  config.json=config.json
include-data-dir: |
  assets=assets
```

### Q: 构建的 exe 文件在哪里？

A: 构建产物在 `build/main.dist/` 目录中。在 GitHub Actions 中，它们会被上传为 Artifacts。

## 与 PyInstaller 的对比

| 特性 | Nuitka | PyInstaller |
|------|--------|-------------|
| 性能 | 更快 (编译为 C++) | 一般 |
| 兼容性 | 更好 | 好 |
| 代码保护 | 强 (编译为 C++) | 弱 (打包) |
| 构建速度 | 较慢 | 较快 |
| 配置复杂度 | 中等 | 简单 |

## 下一步

1. 根据您的需要修改工作流配置
2. 在 GitHub Actions 中测试构建
3. 如有问题，查看 Nuitka 官方文档：https://nuitka.net/doc/

## 许可证

Nuitka 本身是 Apache 2.0 许可证。商业功能需要购买许可证。
