import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading

class GitHubSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        self._create_variables()
        
        self._create_widgets()
    
    def _create_variables(self):
        self.repo_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.sync_with_upstream_var = tk.BooleanVar(value=True)
        self.show_token_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")
        
        self._load_config()
        self._bind_events()
    
    def _bind_events(self):
        self.repo_var.trace_add("write", lambda *args: self._save_settings())
        self.token_var.trace_add("write", lambda *args: self._save_settings())
        self.sync_with_upstream_var.trace_add("write", lambda *args: self._save_settings())
    
    def _load_config(self):
        self.repo_var.set(self.config.get('github_repo', ''))
        self.token_var.set(self.config.get('github_token', ''))
        self.sync_with_upstream_var.set(self.config.get('github_sync_with_upstream', True))
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self._create_basic_settings(main_frame)
    
    def _create_basic_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="汉化仓库上传设置", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)
        
        self._create_entry(frame, "复刻仓库地址:", self.repo_var, 0)
        
        token_frame = ttk.Frame(frame)
        token_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        token_frame.columnconfigure(1, weight=1)
        
        ttk.Label(token_frame, text="GitHub访问令牌:").grid(row=0, column=0, sticky="w", padx=5)
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="*")
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.token_entry.after_idle(self.token_entry.selection_clear)
        
        self.show_token_btn = ttk.Checkbutton(token_frame, text="显示令牌", variable=self.show_token_var, command=self._toggle_token_visibility)
        self.show_token_btn.grid(row=0, column=2, sticky="w", padx=5)
        
        advanced_frame = tk_ttk.LabelFrame(parent, text="高级选项", padding="10")
        advanced_frame.pack(fill="x", pady=(0, 10), padx=5)
        
        ttk.Checkbutton(advanced_frame, text="上传前同步原仓库", variable=self.sync_with_upstream_var).pack(anchor="w", pady=5, padx=5)
        
        self._create_buttons(parent)
    
    def _create_entry(self, parent, label_text, var, row):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=8)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=8)
        entry.after_idle(entry.selection_clear)
    
    def _create_buttons(self, parent):
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", pady=(15, 0))
        
        self.test_btn = ttk.Button(btn_frame, text="测试认证", command=self._test_authentication, bootstyle="primary")
        self.test_btn.pack(side="right", padx=5)
        
        self.status_label = ttk.Label(parent, textvariable=self.status_var, bootstyle="secondary")
        self.status_label.pack(fill="x", pady=(10, 0))
    
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
                
                parsed_repo = repo
                url_pattern = r'https?://github\.com/([^/]+)/([^/]+)(?:\.git)?/?$'
                match = re.match(url_pattern, repo)
                if match:
                    parsed_repo = f"{match.group(1)}/{match.group(2)}"
                
                api_url = f"https://api.github.com/repos/{parsed_repo}"
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
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
    
    def _save_settings(self):
        github_config = {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'github_sync_with_upstream': self.sync_with_upstream_var.get()
        }
        
        self.config.update(github_config)
        
        self.save_callback(github_config)
    
    def get_config(self):
        return {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'github_sync_with_upstream': self.sync_with_upstream_var.get()
        }
