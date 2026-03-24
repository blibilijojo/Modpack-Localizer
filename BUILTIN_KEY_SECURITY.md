# 内置 CurseForge API 密钥安全说明

## 概述

为了防止 CurseForge API 密钥泄露，项目实现了内置密钥保护机制。当通过 GitHub Actions 打包时，可以将 `CURSEFORGE_API_KEY` 作为 GitHub Secret 注入到编译后的 exe 文件中，并且该密钥不会被写入配置文件。

## 工作原理

### 1. 构建时注入
在 GitHub Actions 工作流中，通过 `environment-variables` 将 Secret 注入到编译环境：

```yaml
environment-variables: |
  CURSEFORGE_API_KEY=${{ secrets.CURSEFORGE_API_KEY }}
```

### 2. 运行时保护
- **加载时**：程序启动时自动从环境变量读取内置密钥，并注入到配置中
- **保存时**：检测到当前使用的密钥与内置密钥相同时，自动阻止写入配置文件

### 3. 核心文件
- `utils/builtin_secrets.py` - 内置密钥管理模块
- `utils/config_manager.py` - 配置加载/保存时处理密钥保护
- `gui/settings_components/curseforge_settings.py` - UI 层保护
- `gui/settings_components/external_services_settings.py` - 外部服务设置保护

## 配置 GitHub Secrets

1. 进入 GitHub 仓库页面
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. 添加以下 Secret：
   - **Name**: `CURSEFORGE_API_KEY`
   - **Value**: 你的 CurseForge API 密钥（从 https://console.curseforge.com 获取）

## 用户行为

### 对于普通用户（无内置密钥）
- 需要手动输入自己的 CurseForge API 密钥
- 密钥会正常保存到 `config.json`

### 对于使用官方构建的用户（有内置密钥）
- 程序自动使用内置的 API 密钥
- 在设置界面查看时，显示的是内置密钥（但不会显示完整内容）
- **即使修改设置，内置密钥也不会被覆盖或写入配置文件**
- 配置文件中的 `curseforge_api_key` 字段始终为空

## 安全优势

1. **防止泄露**：即使用户分享配置文件，也不会泄露内置 API 密钥
2. **透明使用**：用户无需配置即可使用 CurseForge 功能
3. **防篡改**：用户无法通过修改配置文件来窃取内置密钥
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
