import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading

class ExternalServicesSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        self._create_variables()
        
        self._create_widgets()
    
    def _create_variables(self):
        # GitHub设置
        self.repo_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.show_token_var = tk.BooleanVar(value=False)
        self.github_status_var = tk.StringVar(value="")
        
        # CurseForge设置
        self.cf_api_key_var = tk.StringVar()
        self.show_cf_key_var = tk.BooleanVar(value=False)
        
        self._load_config()
        self._bind_events()
    
    def _bind_events(self):
        self.repo_var.trace_add("write", lambda *args: self._save_github_settings())
        self.token_var.trace_add("write", lambda *args: self._save_github_settings())
        self.cf_api_key_var.trace_add("write", lambda *args: self._save_cf_settings())
    
    def _load_config(self):
        self.repo_var.set(self.config.get('github_repo', ''))
        self.token_var.set(self.config.get('github_token', ''))
        self.cf_api_key_var.set(self.config.get('curseforge_api_key', ''))
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self._create_github_settings(main_frame)
        self._create_curseforge_settings(main_frame)
    
    def _create_github_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="GitHub 汉化仓库", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)
        
        # 仓库地址
        ttk.Label(frame, text="仓库地址:").grid(row=0, column=0, sticky="w", padx=5, pady=8)
        repo_entry = ttk.Entry(frame, textvariable=self.repo_var)
        repo_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=8)
        repo_entry.after_idle(repo_entry.selection_clear)
        
        # 访问令牌
        token_frame = ttk.Frame(frame)
        token_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        token_frame.columnconfigure(1, weight=1)
        
        ttk.Label(token_frame, text="访问令牌:").grid(row=0, column=0, sticky="w", padx=5)
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="*")
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.token_entry.after_idle(self.token_entry.selection_clear)
        
        self.show_token_btn = ttk.Checkbutton(token_frame, text="显示", variable=self.show_token_var, command=self._toggle_token_visibility)
        self.show_token_btn.grid(row=0, column=2, sticky="w", padx=5)
        
        # 测试按钮和状态
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        
        self.test_btn = ttk.Button(btn_frame, text="测试连接", command=self._test_github_auth, bootstyle="primary-outline")
        self.test_btn.pack(side="right", padx=5)
        
        self.github_status_label = ttk.Label(frame, textvariable=self.github_status_var, bootstyle="secondary")
        self.github_status_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
    
    def _create_curseforge_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="CurseForge API", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)
        
        info_label = ttk.Label(frame, 
            text="用于获取模组信息、从 CurseForge 平台搜索和下载模组\n官方版本已内置密钥；自行构建请自行输入。", 
            bootstyle="secondary")
        info_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        # API密钥
        ttk.Label(frame, text="API密钥:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.cf_key_entry = ttk.Entry(frame, textvariable=self.cf_api_key_var, show="*")
        self.cf_key_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.cf_key_entry.after_idle(self.cf_key_entry.selection_clear)
        
        self.show_cf_key_btn = ttk.Checkbutton(frame, text="显示", variable=self.show_cf_key_var, command=self._toggle_cf_key_visibility)
        self.show_cf_key_btn.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        
        # 帮助信息
        help_frame = tk_ttk.LabelFrame(parent, text="获取CurseForge API密钥", padding="10")
        help_frame.pack(fill="x", pady=(0, 10), padx=5)
        
        help_text = (
            "1. 访问 https://console.curseforge.com 注册账号\n"
            "2. 在 API Keys 页面创建新的API密钥\n"
            "3. 复制密钥并粘贴到上方输入框中"
        )
        help_label = ttk.Label(help_frame, text=help_text, bootstyle="secondary")
        help_label.pack(anchor="w")
    
    def _toggle_token_visibility(self):
        if self.show_token_var.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")
    
    def _toggle_cf_key_visibility(self):
        if self.show_cf_key_var.get():
            self.cf_key_entry.config(show="")
        else:
            self.cf_key_entry.config(show="*")
    
    def _test_github_auth(self):
        repo = self.repo_var.get().strip()
        token = self.token_var.get().strip()
        
        if not repo or not token:
            self.github_status_var.set("请先填写仓库地址和访问令牌")
            return
        
        self.github_status_var.set("正在测试连接...")
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
                    self.github_status_var.set(f"连接成功！仓库: {repo_data['name']}")
                else:
                    self.github_status_var.set(f"连接失败: {response.status_code} - {response.json().get('message', '未知错误')}")
                    
            except Exception as e:
                self.github_status_var.set(f"测试错误: {str(e)}")
            finally:
                self.test_btn.config(state="normal")
        
        threading.Thread(target=test_task, daemon=True).start()
    
    def _save_github_settings(self):
        github_config = {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip()
        }
        self.config.update(github_config)
        self.save_callback(github_config)
    
    def _save_cf_settings(self):
        api_key = self.cf_api_key_var.get().strip()
        
        # 检查是否为内置密钥
        is_builtin = False
        try:
            from utils.builtin_secrets import get_builtin_curseforge_key
            if get_builtin_curseforge_key() and api_key == get_builtin_curseforge_key():
                is_builtin = True
        except ImportError:
            pass
        
        # 如果是内置密钥，不触发保存
        if is_builtin:
            return
        
        cf_config = {
            'curseforge_api_key': api_key
        }
        self.config.update(cf_config)
        self.save_callback(cf_config)
    
    def get_config(self):
        return {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'curseforge_api_key': self.cf_api_key_var.get().strip()
        }
