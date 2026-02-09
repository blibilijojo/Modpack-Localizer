import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading
from pathlib import Path

class GitHubUploadUI(tk.Frame):
    def __init__(self, parent, workbench_instance, default_namespace="", default_file_format="json", github_config=None):
        super().__init__(parent)
        self.parent = parent
        self.workbench = workbench_instance
        self.default_namespace = default_namespace
        self.default_file_format = default_file_format
        self.github_config = github_config or {}
        
        # 从配置中加载最后使用的版本号和版本列表
        from utils import config_manager
        config = config_manager.load_config()
        self.last_used_version = config.get('last_used_version', '1.21')
        self.saved_versions = config.get('github_versions', [])
        
        # 初始化UI
        self._create_widgets()
        
    def _create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # 创建输入表单框架
        form_frame = ttk.LabelFrame(main_frame, text="GitHub汉化仓库上传", padding=15)
        form_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # 配置网格列权重
        form_frame.columnconfigure(0, weight=0, minsize=120)
        form_frame.columnconfigure(1, weight=1, minsize=450)
        form_frame.columnconfigure(2, weight=0, minsize=100)
        
        # 版本号输入（改为下拉选择形式）
        ttk.Label(form_frame, text="版本号:").grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.version_var = tk.StringVar(value=self.last_used_version)
        self.version_combo = ttk.Combobox(form_frame, textvariable=self.version_var, width=60, state="readonly")
        if self.saved_versions:
            self.version_combo['values'] = self.saved_versions
        # 绑定ComboboxSelected事件，取消自动选中
        self.version_combo.bind("<<ComboboxSelected>>", lambda e: self.version_combo.selection_clear())
        self.version_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=8)
        # 获取版本按钮
        self.get_versions_btn = ttk.Button(form_frame, text="获取版本", command=self._get_versions, bootstyle="primary-outline")
        self.get_versions_btn.grid(row=0, column=2, sticky="e", padx=5, pady=8)
        
        # 项目名称输入
        ttk.Label(form_frame, text="项目名称:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.project_name_var = tk.StringVar(value="")  # 默认为空
        ttk.Entry(form_frame, textvariable=self.project_name_var, width=50).grid(row=1, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        
        # 命名空间显示
        ttk.Label(form_frame, text="命名空间:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
        self.namespace_var = tk.StringVar(value=self.default_namespace)
        namespace_entry = ttk.Entry(form_frame, textvariable=self.namespace_var, width=50, state="disabled")
        namespace_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        # 设置禁用输入框的样式
        style = ttk.Style()
        style.configure("Disabled.TEntry", foreground="#666666", background="#f0f0f0")
        namespace_entry.configure(style="Disabled.TEntry")
        
        # 分支名称输入
        ttk.Label(form_frame, text="分支名称:").grid(row=3, column=0, sticky="w", padx=5, pady=8)
        self.branch_var = tk.StringVar(value=self.default_namespace)
        ttk.Entry(form_frame, textvariable=self.branch_var, width=50).grid(row=3, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        
        # 文件格式显示
        ttk.Label(form_frame, text="文件格式:").grid(row=4, column=0, sticky="w", padx=5, pady=8)
        self.file_format_var = tk.StringVar(value=self.default_file_format.upper())
        format_entry = ttk.Entry(form_frame, textvariable=self.file_format_var, width=50, state="disabled")
        format_entry.grid(row=4, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        format_entry.configure(style="Disabled.TEntry")
        
        # 高级选项
        advanced_frame = ttk.LabelFrame(form_frame, text="高级选项", padding=10)
        advanced_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        advanced_frame.columnconfigure(1, weight=1)
        
        # 显示上传路径
        self.path_var = tk.StringVar(value="")
        ttk.Label(advanced_frame, text="上传路径:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        path_entry = ttk.Entry(advanced_frame, textvariable=self.path_var, width=60, state="disabled")
        path_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        path_entry.configure(style="Disabled.TEntry")
        
        # 推送到源仓库选项
        self.push_to_upstream_var = tk.BooleanVar(value=self.github_config.get('push_to_upstream', False))
        ttk.Checkbutton(advanced_frame, text="推送到源仓库", variable=self.push_to_upstream_var).grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=5)
        
        # PR标题配置项
        self.pr_title_var = tk.StringVar(value="")
        ttk.Label(advanced_frame, text="PR标题:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        pr_title_entry = ttk.Entry(advanced_frame, textvariable=self.pr_title_var, width=60)
        pr_title_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5, columnspan=2)
        
        # 更新路径显示
        self._update_path_display()
        
        # 绑定变量变化事件，更新路径显示
        def on_version_change(*args):
            self._update_path_display()
            # 持久化保存版本号
            from utils import config_manager
            config = config_manager.load_config()
            config['last_used_version'] = self.version_var.get()
            config_manager.save_config(config)
        
        self.version_var.trace_add("write", on_version_change)
        self.project_name_var.trace_add("write", lambda *args: self._update_path_display())
        self.namespace_var.trace_add("write", lambda *args: self._update_path_display())
    
        # 状态标签
        self.status_var = tk.StringVar(value="请填写上传信息")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, bootstyle="secondary")
        self.status_label.pack(fill="x", pady=(0, 15))
        
        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 0))
        
        # 同步原仓库按钮
        self.sync_btn = ttk.Button(btn_frame, text="检测并同步原仓库", command=self._on_sync, bootstyle="info-outline", width=15)
        self.sync_btn.pack(side="left", padx=5)
        
        # 上传按钮
        self.upload_btn = ttk.Button(btn_frame, text="开始上传", command=self._on_upload, bootstyle="success-outline", width=12)
        self.upload_btn.pack(side="right", padx=5)
    
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
    
    def _update_path_display(self):
        # 构建路径
        version = self.version_var.get().strip()
        project_name = self.project_name_var.get().strip() or self.default_namespace
        namespace = self.namespace_var.get().strip()
        path = f"projects/{version}/assets/{project_name}/{namespace}/lang"
        self.path_var.set(path)
    
    def _on_upload(self):
        """上传按钮点击事件"""
        version = self.version_var.get().strip()
        project_name = self.project_name_var.get().strip()
        namespace = self.namespace_var.get().strip()
        branch = self.branch_var.get().strip()
        
        # 检查是否有选中的模组
        has_selected_mod = False
        if hasattr(self.workbench, 'ns_tree'):
            selection = self.workbench.ns_tree.selection()
            if selection:
                has_selected_mod = True
        
        if not has_selected_mod:
            from gui import ui_utils
            ui_utils.show_error("未选择模组", "请先选择一个要上传的模组", parent=self.workbench)
            return
        elif not version:
            self.status_var.set("请填写版本号")
            return
        elif not project_name:
            self.status_var.set("请填写项目名称")
            return
        elif not namespace:
            self.status_var.set("命名空间不能为空")
            return
        elif not branch:
            self.status_var.set("请填写分支名称")
            return
        
        # 构建上传配置
        upload_config = {
            'version': version,
            'project_name': project_name,
            'namespace': namespace,
            'branch': branch,
            'file_format': self.default_file_format
        }
        
        # 更新按钮状态为正在上传
        original_btn_text = self.upload_btn.cget("text")
        self.upload_btn.config(text="正在上传", state="disabled")
        self.status_var.set("正在上传...")
        
        # 在后台线程中执行上传
        def upload_task():
            try:
                from services.github_service import GitHubService
                
                # 使用对话框中设置的分支名称
                branch = upload_config['branch']
                
                # 获取当前选中模组的英文全名
                mod_display_name = upload_config['project_name']
                # 尝试从workbench中获取更详细的模组信息
                if hasattr(self.workbench, 'ns_tree'):
                    selection = self.workbench.ns_tree.selection()
                    if selection:
                        current_mod = selection[0]
                        if hasattr(self.workbench, 'translation_data') and current_mod in self.workbench.translation_data:
                            mod_data = self.workbench.translation_data[current_mod]
                            if 'display_name' in mod_data:
                                mod_display_name = mod_data['display_name']
                
                # 初始化GitHub服务
                github_service = GitHubService(
                    self.github_config['repo'], 
                    self.github_config['token'], 
                    branch,
                    pull_before_push=self.github_config.get('pull_before_push', True),
                    push_to_upstream=self.push_to_upstream_var.get(),
                    upstream_branch=self.github_config.get('upstream_branch', 'main'),
                    upstream_repo='CFPAOrg/Minecraft-Mod-Language-Package'  # 源仓库地址
                )
                
                # 检查是否需要同步原仓库
                if self.github_config.get('github_sync_with_upstream', True):
                    self.status_var.set("正在检查并同步原仓库...")
                    sync_success, sync_message = github_service.sync_with_upstream()
                    if not sync_success:
                        # 同步失败，显示错误信息但继续执行上传
                        logging.warning(f'同步原仓库失败: {sync_message}')
                        self.status_var.set(f"同步原仓库失败: {sync_message}，继续执行上传")
                    else:
                        self.status_var.set(f"同步原仓库成功: {sync_message}")
                # 设置PR标题
                if self.pr_title_var.get().strip():
                    # 如果用户手动填写了PR标题，直接使用
                    github_service.pr_title = self.pr_title_var.get().strip()
                else:
                    # 否则使用默认格式：模组英文全名 + 简述
                    default_description = '更新汉化资源包'
                    github_service.pr_title = f'{mod_display_name} {default_description}'
                
                # 构建上传数据
                final_lookup = {}
                latest_data = self.workbench.translation_data
                for ns, data in latest_data.items():
                    for item in data.get('items', []):
                        if item.get('zh', '').strip():
                            if upload_config['namespace'] not in final_lookup:
                                final_lookup[upload_config['namespace']] = {}
                            final_lookup[upload_config['namespace']][item['key']] = item['zh']
                
                final_translations = dict(final_lookup)
                
                # 执行上传
                # 获取原始英文文件内容，用于保持JSON格式一致
                raw_english_files = getattr(self.workbench, 'raw_english_files', {})
                
                success, message = github_service.upload_translations(
                    final_translations, 
                    upload_config['version'], 
                    self.github_config.get('commit_message', '提交'),
                    project_name=upload_config['project_name'],
                    namespace=upload_config['namespace'],
                    file_format=upload_config['file_format'],
                    raw_english_files=raw_english_files
                )
                
                # 显示结果 - 使用状态栏提示
                if success:
                    self.status_var.set("上传成功")
                    # 在工作区状态栏显示成功消息
                    if hasattr(self.workbench, 'status_label'):
                        self.workbench.status_label.config(text=f"上传成功: {message}")
                else:
                    self.status_var.set("上传失败")
                    # 在工作区状态栏显示失败消息
                    if hasattr(self.workbench, 'status_label'):
                        self.workbench.status_label.config(text=f"上传失败: {message}")
                    
            except Exception as e:
                import traceback
                import logging
                error_msg = f"执行上传时发生错误：{str(e)}"
                logging.error(error_msg)
                traceback.print_exc()
                self.status_var.set("上传错误")
                # 在工作区状态栏显示错误消息
                if hasattr(self.workbench, 'status_label'):
                    self.workbench.status_label.config(text=f"上传错误: {error_msg}")
            finally:
                # 恢复按钮状态
                self.upload_btn.config(text=original_btn_text, state="normal")
        
        threading.Thread(target=upload_task, daemon=True).start()
    
    def update_namespace_and_branch(self, namespace):
        """更新命名空间和分支"""
        # 更新命名空间
        self.namespace_var.set(namespace)
        # 更新分支名称，使用命名空间作为默认值
        self.branch_var.set(namespace)
        # 更新路径显示
        self._update_path_display()
    
    def _on_sync(self):
        """手动同步原仓库按钮点击事件"""
        # 检查GitHub配置
        if not self.github_config.get('repo'):
            self.status_var.set("请先在设置中配置GitHub仓库地址")
            return
        if not self.github_config.get('token'):
            self.status_var.set("请先在设置中配置GitHub访问令牌")
            return
        
        # 禁用按钮，防止重复点击
        original_btn_text = self.sync_btn.cget("text")
        self.sync_btn.config(text="正在同步...", state="disabled")
        self.status_var.set("正在检测并同步原仓库...")
        
        def sync_task():
            try:
                from services.github_service import GitHubService
                
                # 初始化GitHub服务
                github_service = GitHubService(
                    self.github_config['repo'], 
                    self.github_config['token'], 
                    branch='main',  # 使用默认分支进行同步
                    upstream_repo='CFPAOrg/Minecraft-Mod-Language-Package'  # 源仓库地址
                )
                
                # 执行同步操作
                sync_success, sync_message = github_service.sync_with_upstream()
                
                if sync_success:
                    self.status_var.set(f"同步原仓库成功: {sync_message}")
                    # 在工作区状态栏显示成功消息
                    if hasattr(self.workbench, 'status_label'):
                        self.workbench.status_label.config(text=f"同步原仓库成功: {sync_message}")
                else:
                    self.status_var.set(f"同步原仓库失败: {sync_message}")
                    # 在工作区状态栏显示失败消息
                    if hasattr(self.workbench, 'status_label'):
                        self.workbench.status_label.config(text=f"同步原仓库失败: {sync_message}")
                    
            except Exception as e:
                import traceback
                import logging
                error_msg = f"执行同步操作时发生错误：{str(e)}"
                logging.error(error_msg)
                traceback.print_exc()
                self.status_var.set(f"同步操作错误: {error_msg}")
                # 在工作区状态栏显示错误消息
                if hasattr(self.workbench, 'status_label'):
                    self.workbench.status_label.config(text=f"同步操作错误: {error_msg}")
            finally:
                # 恢复按钮状态
                self.sync_btn.config(text=original_btn_text, state="normal")
        
        import threading
        threading.Thread(target=sync_task, daemon=True).start()
    
    def _on_cancel(self):
        """取消按钮点击事件"""
        # 调用workbench的方法切换回翻译工作台模式
        self.workbench._toggle_github_upload_mode(False)
