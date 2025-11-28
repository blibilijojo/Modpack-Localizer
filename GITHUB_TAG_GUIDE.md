# GitHub标签推送指南

本指南将帮助您了解如何通过推送标签来触发项目的GitHub Actions工作流程。

## 工作流程概述

项目的GitHub Actions工作流程（`.github/workflows/build-release.yml`）配置为在推送以"v"开头的标签时自动触发。当标签被推送时，工作流程会：

1. 检查代码并设置Python环境
2. 安装依赖
3. 构建更新程序（updater.exe）
4. 构建主程序（Modpack-Localizer-Pro.exe）
5. 从标签获取发布说明
6. 创建GitHub Release并上传构建的可执行文件

## 当前版本信息

- 当前版本：`2.2.0`（定义在`_version.py`文件中）
- Git分支：`main`
- 远程仓库：`https://github.com/blibilijojo/Modpack-Localizer.git`

## 推送标签步骤

### 1. （可选）更新版本号

如果您需要更新项目版本，请修改`_version.py`文件中的版本号：

```python
__version__ = "2.3.0"  # 将版本号更新为新值
```

然后提交更改：

```bash
git add _version.py
git commit -m "Bump version to 2.3.0"
git push origin main
```

### 2. 创建并推送标签

使用以下命令创建并推送标签：

```bash
# 创建标签（使用v前缀）
git tag -a v2.2.0 -m "版本2.2.0发布说明"

# 推送标签到远程仓库
git push origin v2.2.0
```

**注意**：标签名称必须以"v"开头，否则不会触发工作流程。

### 3. 查看工作流程执行状态

推送标签后，您可以在GitHub仓库的"Actions"标签页中查看工作流程的执行状态。

## 标签管理命令

### 查看本地标签

```bash
git tag
```

### 查看远程标签

```bash
git ls-remote --tags origin
```

### 删除本地标签

```bash
git tag -d v2.2.0
```

### 删除远程标签

```bash
git push --delete origin v2.2.0
```

## 最佳实践

1. 确保标签版本与`_version.py`文件中的版本号一致
2. 在标签说明中包含详细的发布说明
3. 推送标签前确保代码已通过所有测试
4. 仅在准备发布新版本时推送标签

通过遵循以上步骤，您可以成功触发GitHub Actions工作流程，自动构建和发布项目。