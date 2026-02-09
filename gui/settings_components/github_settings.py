import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading

class GitHubSettings(tk_ttk.LabelFrame):
    def __init__(self, parent, config, save_callback):
        super().__init__(parent, text="汉化仓库上传设置", padding=15)
        self.config = config
        self.save_callback = save_callback
        
        # 先初始化变量，再创建组件
        self.repo_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.sync_with_upstream_var = tk.BooleanVar(value=True)
        self.show_token_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")
        
        # 先加载配置，再创建组件
        self._load_config()
        
        self._create_widgets()
        
        # 将组件添加到父容器
        self.pack(fill="both", expand=True)
    
    def _create_widgets(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        
        # 仓库地址
        ttk.Label(container, text="复刻仓库地址:").grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.repo_entry = ttk.Entry(container, textvariable=self.repo_var, width=50, takefocus=False)
        self.repo_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=8, columnspan=2)
        # 防止自动选中文本
        self.repo_entry.after_idle(self.repo_entry.selection_clear)
        
        # GitHub令牌
        ttk.Label(container, text="GitHub访问令牌:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.token_entry = ttk.Entry(container, textvariable=self.token_var, show="*", width=50, takefocus=False)
        self.token_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=8)
        # 防止自动选中文本
        self.token_entry.after_idle(self.token_entry.selection_clear)
        
        # 显示/隐藏令牌按钮
        self.show_token_btn = ttk.Checkbutton(container, text="显示令牌", variable=self.show_token_var, command=self._toggle_token_visibility)
        self.show_token_btn.grid(row=1, column=2, sticky="w", padx=5, pady=8)
        


        # 高级选项
        advanced_frame = ttk.LabelFrame(container, text="高级选项", padding=10)
        advanced_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=10)
        advanced_frame.columnconfigure(1, weight=1)
        
        # 同步原仓库选项
        ttk.Checkbutton(advanced_frame, text="上传前同步原仓库", variable=self.sync_with_upstream_var).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        
        # 添加变量追踪，实现自动保存
        def on_repo_change(*args):
            print("Repo changed:", self.repo_var.get())
            self._save_settings()
        
        def on_token_change(*args):
            print("Token changed:", self.token_var.get())
            self._save_settings()
        
        def on_sync_change(*args):
            print("Sync changed:", self.sync_with_upstream_var.get())
            self._save_settings()
        
        self.repo_var.trace_add("write", on_repo_change)
        self.token_var.trace_add("write", on_token_change)
        self.sync_with_upstream_var.trace_add("write", on_sync_change)





        # 测试按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(15, 0))
        
        self.test_btn = ttk.Button(btn_frame, text="测试认证", command=self._test_authentication, bootstyle="primary")
        self.test_btn.pack(side="right", padx=5)
        
        # 状态标签
        self.status_label = ttk.Label(self, textvariable=self.status_var, bootstyle="secondary")
        self.status_label.pack(fill="x", pady=(10, 0))
    
    def _load_config(self):
        self.repo_var.set(self.config.get('github_repo', ''))
        self.token_var.set(self.config.get('github_token', ''))
        self.sync_with_upstream_var.set(self.config.get('github_sync_with_upstream', True))
    
    def _toggle_token_visibility(self):
        if self.show_token_var.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")
    
    def _test_authentication(self):
        repo = self.repo_var.get().strip()
        token = self.token_var.get().strip()
        
        if not repo or not token:
            self.status_var.set("请先填写仓库地址和访问令牌")
            return
        
        self.status_var.set("正在测试认证...")
        self.test_btn.config(state="disabled")
        
        def test_task():
            try:
                import requests
                import re
                
                # 解析仓库地址
                parsed_repo = repo
                url_pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$'
                match = re.match(url_pattern, repo)
                if match:
                    parsed_repo = f"{match.group(1)}/{match.group(2)}"
                
                # 构建API URL
                api_url = f"https://api.github.com/repos/{parsed_repo}"
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                # 发送请求
                response = requests.get(api_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    repo_data = response.json()
                    self.status_var.set(f"认证成功！仓库: {repo_data['name']}")
                else:
                    self.status_var.set(f"认证失败: {response.status_code} - {response.json().get('message', '未知错误')}")
                    
            except Exception as e:
                self.status_var.set(f"测试错误: {str(e)}")
            finally:
                self.test_btn.config(state="normal")
        
        threading.Thread(target=test_task, daemon=True).start()
    
    def _fetch_branches(self):
        """从GitHub获取仓库分支"""
        repo = self.repo_var.get().strip()
        token = self.token_var.get().strip()
        
        if not repo or not token:
            self.status_var.set("请先填写仓库地址和访问令牌")
            return
        
        self.status_var.set("正在获取分支...")
        
        def fetch_task():
            try:
                import requests
                import re
                
                # 解析仓库地址
                parsed_repo = repo
                url_pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$'
                match = re.match(url_pattern, repo)
                if match:
                    parsed_repo = f"{match.group(1)}/{match.group(2)}"
                
                # 构建API URL
                api_url = f"https://api.github.com/repos/{parsed_repo}/branches"
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                # 发送请求
                response = requests.get(api_url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    branches_data = response.json()
                    branches = [branch['name'] for branch in branches_data]
                    
                    # 更新分支下拉框
                    self.branch_combo['values'] = branches
                    
                    # 如果当前分支不在列表中，选择第一个分支
                    current_branch = self.branch_var.get()
                    if current_branch not in branches and branches:
                        self.branch_var.set(branches[0])
                    
                    # 自动保存设置，确保分支信息持久化
                    self._save_settings()
                    
                    self.status_var.set(f"成功获取 {len(branches)} 个分支并保存设置")
                else:
                    self.status_var.set(f"获取分支失败: {response.status_code} - {response.json().get('message', '未知错误')}")
                    
            except Exception as e:
                self.status_var.set(f"获取分支错误: {str(e)}")
        
        threading.Thread(target=fetch_task, daemon=True).start()
    
    def _save_settings(self):
        print("_save_settings called")
        
        github_config = {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'github_sync_with_upstream': self.sync_with_upstream_var.get()
        }
        
        print("GitHub config:", github_config)
        
        self.config.update(github_config)
        print("Config updated")
        
        self.save_callback(github_config)
        print("Save callback called")
        
        self.status_var.set("设置已保存")
        print("Status updated")
    
    def get_config(self):
        return {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'github_sync_with_upstream': self.sync_with_upstream_var.get()
        }
