import logging
import tkinter as tk
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
import threading

logger = logging.getLogger(__name__)

class ExternalServicesSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        self._create_variables()
        
        self._create_widgets()
    
    def _create_variables(self):
        # GitHub 设置
        self.repo_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.show_token_var = tk.BooleanVar(value=False)
        self.github_status_var = tk.StringVar(value="")
        # 跨设备项目同步中继（Cloudflare Workers）
        self.relay_url_var = tk.StringVar()
        self.relay_status_var = tk.StringVar(value="")
        # 同步时间设置
        self.sync_download_interval_var = tk.StringVar(value="5")
        self.sync_upload_interval_var = tk.StringVar(value="20")
        
        self._load_config()
        self._bind_events()
    
    def _bind_events(self):
        self.repo_var.trace_add("write", lambda *args: self._save_github_settings())
        self.token_var.trace_add("write", lambda *args: self._save_github_settings())
        self.relay_url_var.trace_add("write", lambda *args: self._save_relay_settings())
        self.sync_download_interval_var.trace_add("write", lambda *args: self._save_relay_settings())
        self.sync_upload_interval_var.trace_add("write", lambda *args: self._save_relay_settings())
    
    def _load_config(self):
        self.repo_var.set(self.config.get('github_repo', ''))
        self.token_var.set(self.config.get('github_token', ''))
        self.relay_url_var.set(self.config.get('project_sync_relay_url', ''))
        self.sync_download_interval_var.set(str(self.config.get('sync_download_interval', 5)))
        self.sync_upload_interval_var.set(str(self.config.get('sync_upload_interval', 20)))
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self._create_github_settings(main_frame)
        self._create_project_sync_relay_settings(main_frame)
    
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

    def _create_project_sync_relay_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="跨设备项目同步（中继）", padding="10")
        frame.pack(fill="x", pady=(0, 10), padx=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="中继站点根地址:",
        ).grid(row=0, column=0, sticky="nw", padx=5, pady=8)
        hint = (
            "填写你部署的 Cloudflare Workers 中继服务根 URL，"
            "例如 https://relay.your-domain.com\n"
            "后续「单标签项目」同步将使用该地址；当前版本仅检测连接。"
        )
        relay_entry = ttk.Entry(frame, textvariable=self.relay_url_var)
        relay_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=8)
        relay_entry.after_idle(relay_entry.selection_clear)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="e", pady=5)
        self.relay_test_btn = ttk.Button(
            btn_frame,
            text="检测中继连接",
            command=self._test_relay_connection,
            bootstyle="primary-outline",
        )
        self.relay_test_btn.pack(side="right", padx=5)

        self.relay_status_label = ttk.Label(
            frame,
            textvariable=self.relay_status_var,
            bootstyle="secondary",
            wraplength=640,
            justify="left",
        )
        self.relay_status_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # 同步时间设置
        ttk.Label(frame, text="下载同步间隔 (秒):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        download_entry = ttk.Entry(frame, textvariable=self.sync_download_interval_var, width=10)
        download_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(frame, text="上传同步间隔 (秒):").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        upload_entry = ttk.Entry(frame, textvariable=self.sync_upload_interval_var, width=10)
        upload_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        try:
            from gui import custom_widgets
            custom_widgets.ToolTip(relay_entry, hint)
        except Exception:
            pass
    
    def _toggle_token_visibility(self):
        if self.show_token_var.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")
    
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

    def _test_relay_connection(self):
        raw = self.relay_url_var.get().strip()
        if not raw:
            self.relay_status_var.set("请先填写中继站点根地址")
            return

        self.relay_status_var.set("正在检测中继…")
        self.relay_test_btn.config(state="disabled")

        def task():
            try:
                from utils import project_sync_relay

                logger.info(
                    "[ExternalServices] 检测中继连接 raw_input=%r",
                    (raw or "")[:400],
                )
                _ok, msg = project_sync_relay.probe_project_sync_relay(raw)
                logger.info(
                    "[ExternalServices] 中继检测结果 ok=%s msg=%s",
                    _ok,
                    (msg or "")[:500],
                )
                self.relay_status_var.set(msg)
            except Exception as e:
                self.relay_status_var.set(f"检测出错：{e}")
            finally:
                self.relay_test_btn.config(state="normal")

        threading.Thread(target=task, daemon=True).start()

    def _save_relay_settings(self):
        try:
            download_interval = int(self.sync_download_interval_var.get().strip())
            upload_interval = int(self.sync_upload_interval_var.get().strip())
        except ValueError:
            download_interval = 5
            upload_interval = 20
        
        relay_cfg = {
            "project_sync_relay_url": self.relay_url_var.get().strip(),
            "sync_download_interval": download_interval,
            "sync_upload_interval": upload_interval
        }
        self.config.update(relay_cfg)
        self.save_callback(relay_cfg)
    
    def _save_github_settings(self):
        github_config = {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip()
        }
        self.config.update(github_config)
        self.save_callback(github_config)
    
    def get_config(self):
        try:
            download_interval = int(self.sync_download_interval_var.get().strip())
            upload_interval = int(self.sync_upload_interval_var.get().strip())
        except ValueError:
            download_interval = 5
            upload_interval = 20
        
        return {
            'github_repo': self.repo_var.get().strip(),
            'github_token': self.token_var.get().strip(),
            'project_sync_relay_url': self.relay_url_var.get().strip(),
            'sync_download_interval': download_interval,
            'sync_upload_interval': upload_interval
        }
