# 内置 CurseForge API 密钥安全说明

## 概述

为了防止 CurseForge API 密钥泄露，项目采用了**纯内置密钥机制**。当通过 GitHub Actions 打包时，将 `CURSEFORGE_API_KEY` 作为 GitHub Secret 硬编码到编译后的 exe 文件中。**设置界面中已移除 CurseForge 配置项**，用户无法通过界面修改密钥。

## 工作原理

### 1. 构建时注入
在 GitHub Actions 工作流中，通过 PowerShell 脚本将 Secret 写入 `utils/builtin_secrets.py` 文件：

```yaml
- name: Generate builtin_secrets with API key
  run: |
    $apiKey = $env:CURSEFORGE_API_KEY
    # 生成包含密钥的 builtin_secrets.py 文件
```

### 2. 运行时使用
- **加载时**：程序启动时从 `utils/builtin_secrets` 模块读取内置密钥
- **使用时**：直接从内存中的常量获取密钥
- **不保存**：密钥永远不会写入配置文件

### 3. 核心文件
- `utils/builtin_secrets.py` - 内置密钥管理模块（构建时生成）
- `utils/config_manager.py` - 配置加载时注入密钥
- `core/extractor.py` - 使用密钥访问 CurseForge API

## 配置 GitHub Secrets

1. 进入 GitHub 仓库页面
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. 添加以下 Secret：
   - **Name**: `CURSEFORGE_API_KEY`
   - **Value**: 你的 CurseForge API 密钥（从 https://console.curseforge.com 获取）

## 用户行为

### 对于使用官方构建的用户（有内置密钥）
- **无需任何配置**，程序自动使用内置的 API 密钥
- **设置界面中没有 CurseForge 配置项**
- 配置文件中的 `curseforge_api_key` 字段始终为空
- 完全透明，用户无感知使用

### 对于自行构建的用户
- 需要自行设置 `CURSEFORGE_API_KEY` 环境变量或修改 `builtin_secrets.py`
- 或者输入自己的 CurseForge API 密钥到配置文件中

## 安全优势

1. **绝对防止泄露**：
   - 设置界面已移除，用户无法看到或修改密钥
   - 配置文件永远不会包含密钥
   - 即使用户分享配置文件，也不会泄露内置 API 密钥

2. **透明使用**：用户无需配置即可使用 CurseForge 功能

3. **防篡改**：
   - 用户无法通过修改配置文件来窃取内置密钥
   - 需要反编译 exe 才能提取密钥

4. **可追溯**：如果密钥泄露，可以追溯到具体的构建版本

## 注意事项

- 内置密钥仅在读入内存时使用，不会持久化存储
- 如果用户输入自己的密钥，会覆盖内置密钥并正常保存
- 反编译 exe 文件仍然可能提取出密钥，因此建议：
  - 定期轮换 API 密钥
  - 监控 API 使用情况
  - 如发现泄露立即在 CurseForge 控制台撤销密钥

## 紧急处理（如果密钥已泄露）

如果内置密钥已经意外写入配置文件并泄露：

1. **立即在 CurseForge 控制台撤销该 API 密钥**
   - 访问 https://console.curseforge.com
   - 删除已泄露的 API 密钥

2. **生成新的 API 密钥**
   - 在 CurseForge 控制台创建新的 API 密钥
   - 更新 GitHub Secrets 中的 `CURSEFORGE_API_KEY`

3. **重新构建并发布新版本**
   - 触发新的 GitHub Actions 构建
   - 通知用户更新到新版本

4. **清理已泄露的配置文件**
   - 如果 `config.json` 中包含了密钥，手动编辑删除 `curseforge_api_key` 字段
   - 或使用新版本打开程序，它会自动清除泄露的密钥

## 开发调试

在本地开发时，可以通过环境变量设置测试密钥：

```powershell
$env:CURSEFORGE_API_KEY="your_test_key_here"
python main.py
```
