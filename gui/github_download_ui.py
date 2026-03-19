import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading
import re
from pathlib import Path

class GitHubDownloadUI(tk.Frame):
    def __init__(self, parent, main_window_instance, github_config=None):
        super().__init__(parent)
        self.parent = parent
        self.main_window = main_window_instance
        self.github_config = github_config or {}
        
        # 用于存储项目信息的字典，键是item ID，值是项目信息
        self.project_info_map = {}
        
        # 初始化 UI
        self._create_widgets()
    
    def _create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # 创建输入表单框架
        form_frame = ttk.LabelFrame(main_frame, text="GitHub汉化仓库下载")
        form_frame.pack(fill="both", expand=True, pady=(0, 15), padx=15, ipady=15)
        
        # 配置网格列权重
        form_frame.columnconfigure(0, weight=0, minsize=120)
        form_frame.columnconfigure(1, weight=1, minsize=450)
        form_frame.columnconfigure(2, weight=0, minsize=100)
        

        
        # 项目列表
        ttk.Label(form_frame, text="项目列表:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.project_list = ttk.Treeview(form_frame, columns=("project", "namespace", "version", "pr"), show="headings", height=10)
        self.project_list.heading("project", text="项目名称")
        self.project_list.heading("namespace", text="命名空间")
        self.project_list.heading("version", text="版本")
        self.project_list.heading("pr", text="PR")
        self.project_list.column("project", width=150, anchor="w")
        self.project_list.column("namespace", width=120, anchor="w")
        self.project_list.column("version", width=80, anchor="center")
        self.project_list.column("pr", width=200, anchor="w")
        self.project_list.grid(row=1, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(form_frame, orient="vertical", command=self.project_list.yview)
        scrollbar.grid(row=1, column=3, sticky="ns", pady=8)
        self.project_list.configure(yscrollcommand=scrollbar.set)
        
        # 获取项目按钮
        self.get_projects_btn = ttk.Button(form_frame, text="获取项目", command=self._get_projects, bootstyle="primary-outline")
        self.get_projects_btn.grid(row=2, column=2, sticky="e", padx=5, pady=8)
        
        # 状态标签
        self.status_var = tk.StringVar(value="请填写下载信息")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, bootstyle="secondary")
        self.status_label.pack(fill="x", pady=(0, 15))
        
        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 0))
        
        # 下载按钮
        self.download_btn = ttk.Button(btn_frame, text="下载并创建标签页", command=self._on_download, bootstyle="success-outline", width=20)
        self.download_btn.pack(side="right", padx=5)
    
    def _get_versions(self):
        """从GitHub仓库获取所有版本号"""
        # 验证配置
        if not self.github_config.get('repo') or not self.github_config.get('token'):
            self.status_var.set("请先在设置中配置GitHub仓库地址和访问令牌")
            return
        
        self.status_var.set("正在获取版本号...")
        self.get_versions_btn.config(state="disabled")
        
        def get_versions_task():
            try:
                from services.github_service import GitHubService
                from utils import config_manager
                
                # 初始化GitHub服务
                github_service = GitHubService(
                    self.github_config['repo'],
                    self.github_config['token']
                )
                
                # 获取projects目录内容
                projects_path = 'projects'
                endpoint = f'/repos/{github_service.repo}/contents/{projects_path}'
                projects_content = github_service._make_request('GET', endpoint)
                
                if not projects_content:
                    self.status_var.set("未找到projects目录或无法访问")
                    return
                
                # 提取版本号（只保留目录，过滤掉占位符和示例）
                versions = []
                for item in projects_content:
                    if item.get('type') == 'dir':
                        version_name = item.get('name')
                        # 过滤掉占位符和示例目录
                        if version_name not in ['.placeholder', 'packer-example']:
                            versions.append(version_name)
                
                if not versions:
                    self.status_var.set("未找到版本号目录")
                    return
                
                # 更新下拉选择框的选项
                def update_version_combo():
                    if not self.winfo_exists():
                        return
                    
                    # 更新下拉选择框的选项
                    self.version_combo['values'] = versions
                    
                    # 如果当前版本号不在列表中，选择第一个版本号
                    current_version = self.version_var.get()
                    if current_version not in versions and versions:
                        self.version_var.set(versions[0])
                    
                    # 持久化保存版本号和版本列表
                    config = config_manager.load_config()
                    config['last_used_version'] = self.version_var.get()
                    config['github_versions'] = versions
                    config_manager.save_config(config)
                    
                    self.status_var.set(f"成功获取 {len(versions)} 个版本号")
                
                self.after(0, update_version_combo)
                
            except Exception as e:
                import logging
                logging.error(f"获取版本号失败: {str(e)}")
                self.status_var.set(f"获取版本号失败: {str(e)}")
            finally:
                if self.winfo_exists():
                    self.get_versions_btn.config(state="normal")
        
        # 在后台线程中执行
        threading.Thread(target=get_versions_task, daemon=True).start()
    
    def _get_projects(self):
        """从GitHub仓库获取项目列表"""
        # 验证配置
        if not self.github_config.get('repo') or not self.github_config.get('token'):
            self.status_var.set("请先在设置中配置GitHub仓库地址和访问令牌")
            return
        
        self.status_var.set("正在获取项目列表...")
        self.get_projects_btn.config(state="disabled")
        
        def get_projects_task():
            try:
                from services.github_service import GitHubService
                
                # 初始化GitHub服务
                github_service = GitHubService(
                    self.github_config['repo'],
                    self.github_config['token']
                )
                
                # 获取项目列表（不指定版本，获取所有版本）
                success, projects, message = github_service.get_projects()
                
                def update_project_list():
                    if not self.winfo_exists():
                        return
                    
                    # 清空项目列表
                    for item in self.project_list.get_children():
                        self.project_list.delete(item)
                    
                    if success:
                        # 添加项目到列表
                        for project in projects:
                            # 构建PR信息
                            pr_info = f"#{project.get('pr_number', '')} - {project.get('pr_title', '')[:30]}..." if project.get('pr_number') else ""
                            # 插入项目到列表，不使用tags属性
                            item_id = self.project_list.insert("", "end", values=(
                                project['project_name'],
                                project['namespace'],
                                project['version'],
                                pr_info
                            ))
                            # 将项目信息存储到字典中
                            self.project_info_map[item_id] = project
                        self.status_var.set(f"成功获取 {len(projects)} 个项目")
                    else:
                        self.status_var.set(f"获取项目列表失败: {message}")
                
                self.after(0, update_project_list)
                
            except Exception as e:
                import logging
                logging.error(f"获取项目列表失败: {str(e)}")
                self.status_var.set(f"获取项目列表失败: {str(e)}")
            finally:
                if self.winfo_exists():
                    self.get_projects_btn.config(state="normal")
        
        # 在后台线程中执行
        threading.Thread(target=get_projects_task, daemon=True).start()
    
    def _on_download(self):
        """下载按钮点击事件"""
        # 验证配置
        if not self.github_config.get('repo') or not self.github_config.get('token'):
            self.status_var.set("请先在设置中配置GitHub仓库地址和访问令牌")
            return
        
        # 检查是否有选中的项目
        selection = self.project_list.selection()
        if not selection:
            self.status_var.set("请选择一个要下载的项目")
            return
        
        # 获取选中的项目信息
        selected_item = selection[0]
        project_info = self.project_info_map.get(selected_item)
        if not project_info:
            self.status_var.set("未找到项目信息")
            return
        
        # 更新按钮状态为正在下载
        original_btn_text = self.download_btn.cget("text")
        self.download_btn.config(text="正在下载", state="disabled")
        self.status_var.set("正在下载项目...")
        
        # 在后台线程中执行下载
        def download_task():
            try:
                from services.github_service import GitHubService
                import json
                import logging
                
                logging.info('[GitHub UI] 开始下载项目: %s', project_info.get('project_name', '未知项目'))
                
                # 初始化GitHub服务
                github_service = GitHubService(
                    self.github_config['repo'],
                    self.github_config['token']
                )
                
                # 下载zh_cn.json文件
                zh_cn_path = project_info['path']
                logging.info('[GitHub UI] 开始下载中文翻译文件: %s', zh_cn_path)
                success, zh_cn_content, message = github_service.download_file(zh_cn_path, project_info.get('pr_branch'))
                if not success:
                    logging.error('[GitHub UI] 下载中文翻译文件失败: %s', message)
                    self.status_var.set(f"下载中文翻译文件失败: {message}")
                    return
                
                logging.info('[GitHub UI] 成功下载中文翻译文件: %s, 大小: %d 字符', zh_cn_path, len(zh_cn_content))
                
                # 下载en_us.json文件
                en_us_path = zh_cn_path.replace('zh_cn.json', 'en_us.json')
                logging.info('[GitHub UI] 开始下载英文原文文件: %s', en_us_path)
                success, en_us_content, message = github_service.download_file(en_us_path, project_info.get('pr_branch'))
                if not success:
                    logging.error('[GitHub UI] 下载英文原文文件失败: %s', message)
                    self.status_var.set(f"下载英文原文文件失败: {message}")
                    return
                
                logging.info('[GitHub UI] 成功下载英文原文文件: %s, 大小: %d 字符', en_us_path, len(en_us_content))
                
                # 解析JSON文件
                try:
                    zh_cn_data = json.loads(zh_cn_content)
                    logging.info('[GitHub UI] 解析中文翻译文件成功，包含 %d 个键', len(zh_cn_data))
                except Exception as e:
                    logging.error('[GitHub UI] 解析中文翻译文件失败: %s', str(e))
                    self.status_var.set(f"解析中文翻译文件失败: {str(e)}")
                    return
                
                try:
                    en_us_data = json.loads(en_us_content)
                    logging.info('[GitHub UI] 解析英文原文文件成功，包含 %d 个键', len(en_us_data))
                except Exception as e:
                    logging.error('[GitHub UI] 解析英文原文文件失败: %s', str(e))
                    self.status_var.set(f"解析英文原文文件失败: {str(e)}")
                    return
                
                # 构建翻译数据结构
                namespace = project_info.get('namespace', 'unknown')
                logging.info('[GitHub UI] 项目命名空间: %s', namespace)
                
                # 执行翻译决策（参照模组汉化的实现）
                workbench_data = {}
                items = []
                
                # 从原始英文文件中提取有序键
                def get_ordered_keys(content):
                    keys = []
                    # 使用更通用的正则表达式解析JSON文件，保持原始顺序
                    # 匹配所有类型的键值对，包括字符串、数字、布尔值、对象等
                    JSON_KEY_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:')
                    for match in JSON_KEY_PATTERN.finditer(content):
                        key = match.group(1)
                        keys.append(key)
                    return keys
                
                ordered_keys = get_ordered_keys(en_us_content)
                
                # 确保所有英文词典中的键都被包含
                all_keys = set(en_us_data.keys())
                ordered_keys_set = set(ordered_keys)
                missing_keys = all_keys - ordered_keys_set
                
                # 将缺失的键添加到有序键列表末尾
                ordered_keys.extend(list(missing_keys))
                
                # 统计键的来源
                total_entries = 0
                source_counts = {}
                
                for key in ordered_keys:
                    # 获取英文原文并确保为字符串类型
                    en_text = en_us_data.get(key, key)
                    en_text = str(en_text) if en_text is not None else key
                    # 获取中文翻译
                    zh_text = zh_cn_data.get(key, '')
                    
                    # 确定翻译来源
                    source = None
                    if zh_text:
                        source = "GitHub下载"
                    else:
                        source = "待翻译"
                    
                    # 构建条目
                    item_entry = {
                        'key': key,
                        'en': en_text,
                        'zh': zh_text,
                        'source': source
                    }
                    
                    # 统计来源
                    if source not in source_counts:
                        source_counts[source] = 0
                    source_counts[source] += 1
                    total_entries += 1
                    
                    items.append(item_entry)
                
                # 记录翻译决策贡献分析
                logging.info('[GitHub UI] --- 翻译决策贡献分析 ---')
                logging.info('[GitHub UI] 总条目数: %d', total_entries)
                for source, count in sorted(source_counts.items()):
                    percentage = (count / total_entries) * 100 if total_entries > 0 else 0
                    logging.info('[GitHub UI]   ▷ %s: %d 条 (%.2f%%)', source, count, percentage)
                logging.info('[GitHub UI] --------------------------')
                
                # 构建TranslationWorkbench期望的格式
                workbench_data[namespace] = {
                    'items': items,
                    'jar_name': project_info.get('project_name', 'unknown'),
                    'mod_name': project_info.get('project_name', 'unknown'),
                    'namespace': namespace,
                    'game_version': project_info.get('version', 'unknown'),
                    'display_name': project_info.get('project_name', 'unknown')
                }
                
                # 构建原始英文文件内容
                raw_english_files = {}
                raw_english_files[namespace] = en_us_content
                
                # 在当前标签页中显示翻译工作台
                def show_workbench():
                    if not self.winfo_exists():
                        return
                    
                    # 获取当前标签页
                    current_tab_id = self.main_window.notebook.select()
                    if current_tab_id in self.main_window.project_tabs:
                        project_tab = self.main_window.project_tabs[current_tab_id]
                        
                        # 设置项目信息
                        project_tab.project_name = project_info.get('project_name', 'unknown')
                        project_tab.project_type = "mod"
                        project_tab.project_info = {
                            'mod_name': project_info.get('project_name', 'unknown'),
                            'namespace': namespace,
                            'game_version': project_info.get('version', 'unknown')
                        }
                        
                        # 更新标签页标题
                        self.main_window.update_tab_title(current_tab_id, project_info.get('project_name', 'unknown'))
                        
                        # 显示工作区
                        project_tab._show_workbench_view(
                            workbench_data=workbench_data,
                            namespace_formats={},
                            raw_english_files=raw_english_files,
                            current_settings={},
                            project_path=None,
                            finish_button_text="完成",
                            save_session_after=False
                        )
                        
                        # 显示成功消息
                        success_msg = f"成功下载项目: {project_info.get('project_name', 'unknown')}"
                        self.status_var.set(success_msg)
                        logging.info('[GitHub UI] %s', success_msg)
                
                self.after(0, show_workbench)
                
            except Exception as e:
                import traceback
                import logging
                error_msg = f"执行下载时发生错误：{str(e)}"
                logging.error('[GitHub UI] %s', error_msg)
                traceback.print_exc()
                self.status_var.set(f"下载错误: {error_msg}")
            finally:
                # 恢复按钮状态
                if self.winfo_exists():
                    self.download_btn.config(text=original_btn_text, state="normal")
                    logging.info('[GitHub UI] 下载任务完成，恢复按钮状态')
        
        threading.Thread(target=download_task, daemon=True).start()
