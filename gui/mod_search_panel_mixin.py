from __future__ import annotations
import threading
import logging
import re
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from utils import config_manager
from utils.api_urls import MODRINTH_API_BASE, CURSEFORGE_API_BASE
from gui import ui_utils
from gui.dialogs import DownloadProgressDialog


class ModSearchMixin:
    """ProjectTab 的模组搜索/下载功能 Mixin。"""

    def _setup_new_mod_search_project(self):
        from gui.project_type_config import get_project_type_config
        self._setup_generic_project(get_project_type_config("modsearch"))

    def _show_mod_search_view(self):
        """显示模组搜索界面"""
        self._clear_content_frame()
        if not self.log_pane_visible:
            self._toggle_log_pane()
        
        # 创建主容器
        main_container = ttk.Frame(self.content_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 使用网格布局管理主容器
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=0)
        main_container.rowconfigure(1, weight=1)
        
        # 搜索和筛选区域
        search_frame = ttk.LabelFrame(main_container, text="搜索")
        search_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        
        # 搜索输入框
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_input_frame, text="搜索关键词:", width=10).pack(side="left", padx=5, pady=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_input_frame, textvariable=self.search_var, width=60)
        search_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        search_entry.bind("<Return>", lambda e: self.start_mod_search())
        
        # 筛选选项
        filter_frame = ttk.Frame(search_frame)
        filter_frame.pack(fill="x")
        
        ttk.Label(filter_frame, text="平台:", width=10).pack(side="left", padx=5, pady=5)
        self.platform_var = tk.StringVar(value="CurseForge")
        platform_combo = ttk.Combobox(filter_frame, textvariable=self.platform_var, values=["Modrinth", "CurseForge"], state="readonly", width=15)
        platform_combo.pack(side="left", padx=5, pady=5)
        platform_combo.bind("<<ComboboxSelected>>", lambda e: platform_combo.selection_clear())

        ttk.Label(filter_frame, text="游戏版本:", width=10).pack(side="left", padx=5, pady=5)
        self.game_version_var = tk.StringVar(value="全部")
        game_versions = [
            "全部", "1.21", "1.20.4", "1.20.2", "1.20.1", "1.20", "1.19.4",
            "1.19.3", "1.19.2", "1.19.1", "1.19", "1.18.2", "1.18.1", "1.18",
            "1.17.1", "1.17", "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1", "1.16",
            "1.15.2", "1.15.1", "1.15", "1.14.4", "1.14.3", "1.14.2", "1.14.1", "1.14",
            "1.13.2", "1.13.1", "1.13", "1.12.2", "1.12.1", "1.12", "1.11.2", "1.11.1", "1.11",
            "1.10.2", "1.10.1", "1.10", "1.9.4", "1.9.3", "1.9.2", "1.9.1", "1.9",
            "1.8.9", "1.8.8", "1.8.7", "1.8.6", "1.8.5", "1.8.4", "1.8.3", "1.8.2", "1.8.1", "1.8"
        ]
        game_version_combo = ttk.Combobox(filter_frame, textvariable=self.game_version_var, values=game_versions, state="readonly", width=15)
        game_version_combo.pack(side="left", padx=5, pady=5)
        game_version_combo.bind("<<ComboboxSelected>>", lambda e: game_version_combo.selection_clear())

        ttk.Label(filter_frame, text="加载器:", width=10).pack(side="left", padx=5, pady=5)
        self.mod_loader_var = tk.StringVar(value="全部")
        mod_loader_combo = ttk.Combobox(filter_frame, textvariable=self.mod_loader_var, values=["全部", "fabric", "forge", "quilt"], state="readonly", width=15)
        mod_loader_combo.pack(side="left", padx=5, pady=5)
        mod_loader_combo.bind("<<ComboboxSelected>>", lambda e: mod_loader_combo.selection_clear())
        
        ttk.Button(filter_frame, text="搜索", command=self.start_mod_search, bootstyle="primary").pack(side="right", padx=5, pady=5)
        
        # 模组列表区域（左侧）
        results_frame = ttk.LabelFrame(main_container, text="模组列表")
        results_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10), padx=(0, 5))
        
        # 模组列表
        self.results_tree = ttk.Treeview(results_frame, columns=("title", "author", "downloads"), show="headings")
        self.results_tree.heading("title", text="模组名称")
        self.results_tree.heading("author", text="作者")
        self.results_tree.heading("downloads", text="下载量")
        self.results_tree.column("title", width=200)
        self.results_tree.column("author", width=100)
        self.results_tree.column("downloads", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.results_tree.pack(fill="both", expand=True)
        
        # 右侧按钮
        results_button_frame = ttk.Frame(results_frame)
        results_button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(results_button_frame, text="查看文件列表", command=self.view_files, bootstyle="outline").pack(side="left", padx=5)
        ttk.Button(results_button_frame, text="打开模组页面", command=self.open_mod_page, bootstyle="outline").pack(side="left", padx=5)
        ttk.Button(results_button_frame, text="下载并汉化", command=self.download_and_localize, bootstyle="success").pack(side="right", padx=5)
        
        # 文件列表区域（右侧）
        files_label_frame = ttk.LabelFrame(main_container, text="文件列表")
        files_label_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 10), padx=(5, 0))
        
        # 文件列表
        self.files_tree = ttk.Treeview(files_label_frame, columns=("name", "mod_version", "game_version", "size", "date"), show="headings")
        self.files_tree.heading("name", text="文件名")
        self.files_tree.heading("mod_version", text="模组版本")
        self.files_tree.heading("game_version", text="游戏版本")
        self.files_tree.heading("size", text="大小")
        self.files_tree.heading("date", text="上传日期")
        self.files_tree.column("name", width=200)
        self.files_tree.column("mod_version", width=80)
        self.files_tree.column("game_version", width=80)
        self.files_tree.column("size", width=80, anchor="center")
        self.files_tree.column("date", width=120)
        
        files_scrollbar = ttk.Scrollbar(files_label_frame, orient="vertical", command=self.files_tree.yview)
        self.files_tree.configure(yscroll=files_scrollbar.set)
        files_scrollbar.pack(side="right", fill="y")
        self.files_tree.pack(fill="both", expand=True)
        
        # 结果变量
        self.all_results = []
        self.current_mod = None
        self.current_files = []

    def start_mod_search(self):
        """启动搜索"""
        query = self.search_var.get().strip()
        if not query:
            messagebox.showinfo("提示", "请输入搜索关键词。")
            return
        
        platform = self.platform_var.get()
        game_version = self.game_version_var.get()
        mod_loader = self.mod_loader_var.get()
        
        # 清空结果
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # 更新状态
        self.status_var.set(f"正在搜索{platform}...")
        self.log_message(f"开始搜索: {query} (平台: {platform})", "INFO")
        
        # 在后台线程中执行搜索
        if platform == "Modrinth":
            thread = threading.Thread(target=self.search_modrinth, args=(query, game_version, mod_loader), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        else:
            thread = threading.Thread(target=self.search_curseforge, args=(query, game_version, mod_loader), daemon=True)
            self.add_background_thread(thread)
            thread.start()

    def search_modrinth(self, query, game_version=None, mod_loader=None):
        """执行Modrinth搜索请求"""
        try:
            import requests
            params = {
                "query": query,
                "limit": 50,
                "index": "relevance"
            }
            
            # 添加筛选参数
            if game_version and game_version != "全部":
                params["filters"] = f"versions={game_version}"
            if mod_loader and mod_loader != "全部":
                if "filters" in params:
                    params["filters"] += f",categories={mod_loader}"
                else:
                    params["filters"] = f"categories={mod_loader}"
            
            # 发送API请求
            response = requests.get(f"{MODRINTH_API_BASE}/search", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # 处理结果
            results = []
            for hit in data.get("hits", []):
                mod_data = {
                    "project_id": hit.get("project_id"),
                    "title": hit.get("title"),
                    "author": hit.get("author"),
                    "description": hit.get("description"),
                    "downloads": hit.get("downloads", 0),
                    "follows": hit.get("follows", 0),
                    "license": hit.get("license"),
                    "slug": hit.get("slug"),
                    "versions": [],
                    "platform": "Modrinth"
                }
                results.append(mod_data)
            
            self.all_results = results
            self.root.after(0, self.update_results)
        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))

    def search_curseforge(self, query, game_version=None, mod_loader=None):
        """执行CurseForge搜索请求"""
        try:
            import requests
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                self.root.after(0, lambda: messagebox.showwarning("警告", "请先在设置中配置CurseForge API密钥"))
                self.root.after(0, lambda: self.status_var.set("未配置API密钥"))
                return

            # 构建API请求URL
            base_urls = [
                CURSEFORGE_API_BASE
            ]
            
            # 构建查询参数
            import urllib.parse
            params = {
                "gameId": 432,
                "sortField": 2,
                "sortOrder": "desc",
                "pageSize": 50,
                "classId": 6  # Mod 分类
            }
            
            # 添加游戏版本筛选
            if game_version and game_version != "全部":
                params["gameVersion"] = game_version
            
            # 添加加载器筛选
            if mod_loader and mod_loader != "全部":
                mod_loader_map = {
                    "forge": 1,
                    "fabric": 4,
                    "quilt": 5
                }
                if mod_loader in mod_loader_map:
                    params["modLoaderType"] = mod_loader_map[mod_loader]
            
            # 添加搜索关键词
            if query:
                params["searchFilter"] = query
            
            # 发送API请求，尝试多个源
            response = None
            for base_url in base_urls:
                try:
                    address = f"{base_url}/v1/mods/search"
                    headers = {
                        "x-api-key": api_key,
                        "Content-Type": "application/json"
                    }
                    
                    # 打印请求信息以便调试
                    self.log_message(f"尝试CurseForge API请求: {address}?{urllib.parse.urlencode(params)}", "INFO")
                    
                    response = requests.get(address, params=params, headers=headers, timeout=15)
                    
                    # 打印响应状态码
                    self.log_message(f"CurseForge API响应状态: {response.status_code}", "INFO")
                    if response.status_code == 200:
                        break
                    else:
                        self.log_message(f"CurseForge API错误: {response.text}", "ERROR")
                except Exception as e:
                    self.log_message(f"尝试{base_url}失败: {str(e)}", "WARNING")
                    continue
            
            if not response or response.status_code != 200:
                raise Exception("无法连接到CurseForge API，请检查网络连接或稍后再试")
            
            data = response.json()
            
            # 处理结果
            results = []
            for mod in data.get("data", []):
                # 解析作者信息
                author_name = "未知"
                if mod.get("authors"):
                    author_name = mod.get("authors")[0].get("name", "未知")
                
                # 解析许可证信息
                license_name = None
                if mod.get("license"):
                    license_name = mod.get("license").get("name")
                
                # 构建模组数据
                mod_data = {
                    "project_id": mod.get("id"),
                    "title": mod.get("name"),
                    "author": author_name,
                    "description": mod.get("summary"),
                    "downloads": mod.get("downloadCount", 0),
                    "follows": mod.get("popularityScore", 0),
                    "license": license_name,
                    "slug": mod.get("slug"),
                    "versions": [],
                    "platform": "CurseForge"
                }
                results.append(mod_data)
            
            self.all_results = results
            self.root.after(0, self.update_results)
        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))

    def update_results(self):
        """更新搜索结果"""
        # 清空结果
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # 添加结果
        for mod in self.all_results:
            self.results_tree.insert("", "end", values=(mod["title"], mod["author"], mod["downloads"]), tags=(mod["project_id"],))
        
        # 更新状态
        self.status_var.set(f"搜索完成，找到 {len(self.all_results)} 个结果")
        self.log_message(f"搜索完成，找到 {len(self.all_results)} 个结果", "SUCCESS")

    def view_files(self):
        """查看模组文件"""
        selected_items = self.results_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个模组。")
            return
        
        # 获取选中的模组
        item = selected_items[0]
        tags = self.results_tree.item(item, "tags")
        if not tags:
            messagebox.showinfo("错误", "无法获取模组ID。")
            return
        
        project_id = tags[0]
        mod = next((m for m in self.all_results if str(m["project_id"]) == project_id), None)
        if not mod:
            messagebox.showinfo("错误", "无法找到选中的模组。")
            return

        self.current_mod = mod
        self.status_var.set("正在获取文件列表...")
        self.log_message(f"获取模组文件: {mod['title']}", "INFO")
        
        # 在后台线程中获取文件
        if mod.get("platform") == "Modrinth":
            thread = threading.Thread(target=self.get_mod_files, args=(project_id,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        else:
            thread = threading.Thread(target=self.get_curseforge_files, args=(project_id,), daemon=True)
            self.add_background_thread(thread)
            thread.start()

    def get_mod_files(self, project_id):
        """获取Modrinth模组文件"""
        try:
            import requests
            # 一次性获取所有文件，设置较大的limit值去除50个的上限
            url = f"{MODRINTH_API_BASE}/project/{project_id}/version"
            params = {"limit": 10000, "offset": 0}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            files = response.json()
            
            # 添加平台信息
            for file_info in files:
                file_info["platform"] = "Modrinth"
            
            # 根据选择的游戏版本过滤
            selected_version = self.game_version_var.get()
            if selected_version and selected_version != "全部":
                filtered_files = []
                for file_info in files:
                    game_versions = file_info.get("game_versions", [])
                    if selected_version in game_versions:
                        filtered_files.append(file_info)
                files = filtered_files
            
            self.current_files = files
            self.root.after(0, self.update_files_list)
        except Exception as e:
            error_msg = f"获取文件失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))

    def get_curseforge_files(self, project_id):
        """获取CurseForge模组文件"""
        try:
            import requests
            import threading
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                self.root.after(0, lambda: messagebox.showwarning("警告", "请先在设置中配置CurseForge API密钥"))
                self.root.after(0, lambda: self.status_var.set("未配置API密钥"))
                return

            # 构建API请求URL，尝试多个源
            base_urls = [
                CURSEFORGE_API_BASE
            ]
            
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # 首先获取总文件数
            total_files = None
            base_url = base_urls[0]
            address = f"{base_url}/v1/mods/{project_id}/files?index=0&limit=1"
            response = requests.get(address, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                pagination = data.get("pagination", {})
                total_files = pagination.get("totalCount", 0)
                self.log_message(f"开始获取 {total_files} 个文件", "INFO")
            else:
                raise Exception(f"获取总文件数失败: {response.text}")
            
            # 多线程并行获取所有文件
            all_files = []
            limit = 50  # CurseForge API 最大每页限制
            total_pages = (total_files + limit - 1) // limit  # 计算总页数
            lock = threading.Lock()
            threads = []
            
            def fetch_page(page):
                offset = page * limit
                try:
                    page_address = f"{base_url}/v1/mods/{project_id}/files?index={offset}&limit={limit}"
                    page_response = requests.get(page_address, headers=headers, timeout=15)
                    if page_response.status_code == 200:
                        page_data = page_response.json()
                        page_files = page_data.get("data", [])
                        with lock:
                            all_files.extend(page_files)
                    else:
                        self.log_message(f"获取文件失败: {page_response.text}", "ERROR")
                except Exception as e:
                    self.log_message(f"获取文件异常: {str(e)}", "ERROR")
            
            # 启动线程
            self.log_message(f"启动 {total_pages} 个线程并行获取文件", "INFO")
            for page in range(total_pages):
                thread = threading.Thread(target=fetch_page, args=(page,))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            self.log_message(f"文件获取完成，共获取 {len(all_files)} 个文件", "INFO")
            
            if len(all_files) == 0:
                raise Exception("无法获取文件列表，请检查网络连接或稍后再试")
            
            files = all_files
            
            # 转换为与Modrinth类似的格式
            formatted_files = []
            for file_info in files:
                # 构建下载URL
                download_url = file_info.get("downloadUrl")
                if not download_url:
                    # 如果没有直接的下载URL，构建一个备用URL
                    file_id = file_info.get("id")
                    file_name = file_info.get("fileName")
                    if file_id and file_name:
                        download_url = f"https://edge.forgecdn.net/files/{str(file_id)[:4]}/{str(file_id)[4:]}/{file_name}"
                
                # 添加镜像源下载链接
                download_urls = [download_url]
                mirror_url = None
                if download_url:
                    # 添加镜像源
                    mirror_url = download_url.replace("https://edge.forgecdn.net", "https://cdn.mod.gg")
                    download_urls.append(mirror_url)
                
                # 构建文件信息
                formatted_file = {
                    "id": file_info.get("id"),
                    "version_number": file_info.get("displayName"),
                    "game_versions": file_info.get("gameVersions", []),
                    "date_published": file_info.get("fileDate"),
                    "files": [{
                        "primary": True,
                        "filename": file_info.get("fileName"),
                        "size": file_info.get("fileLength"),
                        "url": download_url,
                        "mirror_url": mirror_url
                    }],
                    "platform": "CurseForge"
                }
                formatted_files.append(formatted_file)
            
            # 按发布日期排序，最新的在前
            formatted_files.sort(key=lambda x: x.get("date_published", ""), reverse=True)
            
            # 根据选择的游戏版本过滤
            selected_version = self.game_version_var.get()
            if selected_version and selected_version != "全部":
                filtered_files = []
                for file_info in formatted_files:
                    game_versions = file_info.get("game_versions", [])
                    if selected_version in game_versions:
                        filtered_files.append(file_info)
                formatted_files = filtered_files
            
            self.current_files = formatted_files
            self.root.after(0, self.update_files_list)
        except Exception as e:
            error_msg = f"获取文件失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))

    def update_files_list(self):
        """更新文件列表"""
        # 清空文件列表
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        # 添加文件
        for file_info in self.current_files:
            file_name = ""
            file_size = 0
            for asset in file_info.get("files", []):
                if asset.get("primary"):
                    file_name = asset.get("filename")
                    file_size = asset.get("size", 0)
                    break
            
            mod_version = file_info.get("version_number", "")
            game_versions = file_info.get("game_versions", [])
            game_version = ", ".join(game_versions) if game_versions else ""
            date = file_info.get("date_published", "")
            
            # 格式化大小
            size_str = self._format_file_size(file_size)
            
            # 格式化日期
            date_str = date[:10] if date else ""
            
            self.files_tree.insert("", "end", values=(file_name, mod_version, game_version, size_str, date_str), tags=(file_info.get("id"),))
        
        # 更新状态
        self.status_var.set(f"获取完成，找到 {len(self.current_files)} 个文件")
        self.log_message(f"获取完成，找到 {len(self.current_files)} 个文件", "SUCCESS")

    def _format_file_size(self, size):
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def open_mod_page(self):
        """打开模组页面"""
        selected_items = self.results_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个模组。")
            return
        
        # 获取选中的模组
        item = selected_items[0]
        tags = self.results_tree.item(item, "tags")
        if not tags:
            return
        
        project_id = tags[0]
        mod = next((m for m in self.all_results if str(m["project_id"]) == project_id), None)
        if not mod:
            return

        # 打开模组页面
        if mod.get("platform") == "Modrinth":
            url = f"https://modrinth.com/mod/{mod['slug']}"
        else:
            url = f"https://www.curseforge.com/minecraft/mc-mods/{mod['slug']}"
        webbrowser.open(url)

    def download_and_localize(self):
        """下载并本地化"""
        selected_items = self.files_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个文件。")
            return
        
        # 获取选中的文件
        item = selected_items[0]
        tags = self.files_tree.item(item, "tags")
        if not tags:
            return
        
        file_id = tags[0]
        file_info = next((f for f in self.current_files if str(f["id"]) == file_id), None)
        if not file_info:
            return
        
        # 获取下载URL
        download_url = None
        file_name = None
        for asset in file_info.get("files", []):
            if asset.get("primary"):
                download_url = asset.get("url")
                file_name = asset.get("filename")
                break
        
        if not download_url:
            messagebox.showinfo("错误", "无法获取下载链接。")
            return
        
        # 更新状态
        self.status_var.set("正在下载文件...")
        self.log_message(f"开始下载: {file_name}", "INFO")
        
        # 在后台线程中下载文件
        thread = threading.Thread(target=self.download_file, args=(download_url, file_name, file_info), daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def download_file(self, url, file_name, file_info):
        """下载文件"""
        try:
            import requests
            import os
            from pathlib import Path
            
            # 获取JAR下载目录和汉化包输出目录
            jar_dir = self.project_info.get('jar_dir')
            output_dir = self.project_info.get('output_dir')
            if not jar_dir:
                error_msg = "JAR下载目录未设置"
                self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
                self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
                self.root.after(0, lambda: self.status_var.set("错误"))
                return

            # 确保JAR下载目录存在
            jar_path = Path(jar_dir)
            jar_path.mkdir(parents=True, exist_ok=True)

            # 下载文件到JAR目录
            file_path = jar_path / file_name
            self.log_message(f"正在下载到: {file_path}", "INFO")
            
            # 准备下载链接列表
            download_urls = [url]
            
            # 检查是否有镜像链接
            if file_info and file_info.get('files'):
                mirror_url = file_info['files'][0].get('mirror_url')
                if mirror_url:
                    download_urls.append(mirror_url)
            
            # 尝试从多个链接下载
            success = False
            for download_url in download_urls:
                try:
                    self.log_message(f"尝试从: {download_url} 下载", "INFO")
                    response = requests.get(download_url, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    # 获取文件大小
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    # 写入文件
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                
                                # 更新下载进度
                                if total_size > 0:
                                    progress = int((downloaded_size / total_size) * 100)
                                    self.root.after(0, lambda p=progress: self.status_var.set(f"下载中... {p}%"))
                    
                    # 下载成功
                    success = True
                    break
                except Exception as e:
                    self.log_message(f"从 {download_url} 下载失败: {str(e)}", "WARNING")
                    continue
            
            if not success:
                raise Exception("所有下载链接都失败了，请稍后再试")
            
            # 下载完成
            self.root.after(0, lambda: self.status_var.set("下载完成，准备汉化流程..."))
            self.root.after(0, lambda: self.log_message(f"下载完成: {file_name}", "SUCCESS"))
            
            # 开始汉化流程
            self.root.after(0, lambda: self.start_localization_process(file_path, file_info))
        except requests.exceptions.RequestException as e:
            error_msg = f"下载失败: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
        except Exception as e:
            error_msg = f"发生错误: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
            self.root.after(0, lambda: self.log_message(f"错误: {error_msg}", "ERROR"))
            self.root.after(0, lambda: self.status_var.set("错误"))
