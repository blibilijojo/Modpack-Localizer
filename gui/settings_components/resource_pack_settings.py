import tkinter as tk
from tkinter import filedialog, messagebox, ttk as tk_ttk
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets
from gui.dialogs import DownloadProgressDialog
import threading
import sqlite3
from core.term_database import TermDatabase
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import os
import time
import math
import re
from collections import deque

class ResourcePackSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 创建变量
        self._create_variables()
        
        # 创建UI
        self._create_widgets()
    
    def _create_variables(self):
        # 资源包设置
        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_path", ""))
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.community_dict_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建资源包设置
        self._create_resource_pack_settings(main_frame)
        
        # 创建社区包列表
        self._create_community_packs_list(main_frame)
    
    def _create_resource_pack_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="资源包设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        
        dict_path_frame = ttk.Frame(frame)
        dict_path_frame.pack(fill="x", pady=5)
        dict_label = ttk.Label(dict_path_frame, text="社区词典文件:", width=15)
        dict_label.pack(side="left")
        custom_widgets.ToolTip(dict_label, "可选。一个包含补充翻译的 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var, takefocus=False)
        dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        # 防止自动选中文本
        dict_entry.after_idle(dict_entry.selection_clear)
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_file(self.community_dict_var, [("SQLite 数据库", "*.db"), ("所有文件", "*.*")]), bootstyle="primary-outline")
        browse_btn.pack(side="left")
        self.download_dict_button = ttk.Button(dict_path_frame, text="检查/更新", command=self._check_and_update_dict_async, bootstyle="info")
        self.download_dict_button.pack(side="left", padx=(5, 5))
    
    def _create_community_packs_list(self, parent):
        packs_frame = tk_ttk.LabelFrame(parent, text="第三方汉化包列表 (优先级由上至下)", padding="10")
        packs_frame.pack(fill="both", expand=True, pady=(10, 0))
        list_container = ttk.Frame(packs_frame)
        list_container.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical")
        self.packs_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, selectmode="extended", height=4)
        scrollbar.config(command=self.packs_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.packs_listbox.pack(side="left", fill="both", expand=True)
        for path in self.config.get("community_pack_paths", []): 
            self.packs_listbox.insert(tk.END, path)
        
        list_btn_frame = ttk.Frame(packs_frame)
        list_btn_frame.pack(fill="x", pady=(5,0))
        add_btn = ttk.Button(list_btn_frame, text="添加", command=self._add_packs, bootstyle="success-outline", width=8)
        add_btn.pack(side="left", padx=2)
        remove_btn = ttk.Button(list_btn_frame, text="移除", command=self._remove_packs, bootstyle="danger-outline", width=8)
        remove_btn.pack(side="left", padx=2)
        spacer = ttk.Frame(list_btn_frame)
        spacer.pack(side="left", fill="x", expand=True)
        up_btn = ttk.Button(list_btn_frame, text="上移", command=lambda: self._move_pack(-1), bootstyle="info-outline", width=8)
        up_btn.pack(side="left", padx=2)
        down_btn = ttk.Button(list_btn_frame, text="下移", command=lambda: self._move_pack(1), bootstyle="info-outline", width=8)
        down_btn.pack(side="left", padx=2)
    
    def _add_packs(self):
        paths = filedialog.askopenfilenames(title="选择一个或多个第三方汉化包", filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")] )
        for path in paths:
            if path not in self.packs_listbox.get(0, tk.END): 
                self.packs_listbox.insert(tk.END, path)
        self.save_callback()
    
    def _remove_packs(self):
        selected_indices = self.packs_listbox.curselection()
        for i in reversed(selected_indices): 
            self.packs_listbox.delete(i)
        self.save_callback()
    
    def _move_pack(self, direction):
        indices = self.packs_listbox.curselection()
        if not indices: return
        for i in sorted(list(indices), reverse=(direction < 0)):
            if 0 <= i + direction < self.packs_listbox.size():
                text = self.packs_listbox.get(i)
                self.packs_listbox.delete(i)
                self.packs_listbox.insert(i + direction, text)
                self.packs_listbox.selection_set(i + direction)
        self.save_callback()
    
    def _check_and_update_dict_async(self):
        self.download_dict_button.config(state="disabled", text="检查中...")
        threading.Thread(target=self._dict_update_worker, daemon=True).start()
    
    def _dict_update_worker(self):
        import requests
        import logging
        from pathlib import Path
        from utils import config_manager
        from gui.dialogs import DownloadProgressDialog
        
        try:
            # 获取远程词典信息
            remote_info = self._get_remote_dict_info()
            if not remote_info:
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "无法获取远程词典信息，请检查网络连接。"))
                return
            
            # 获取本地词典路径
            community_dict_path = self.community_dict_var.get()
            local_path = Path(community_dict_path) if community_dict_path else None
            
            # 检查本地词典版本
            local_version = config_manager.load_config().get("last_dict_version", "0.0.0")
            remote_version = remote_info.get("version", "0.0.0")
            
            # 比较版本
            if local_path and local_path.exists():
                if local_version == remote_version:
                    if self.parent.winfo_exists():
                        self.parent.after(0, lambda: ui_utils.show_info("检查完成", "社区词典已是最新版本。"))
                    return
            
            # 需要更新或下载
            if not local_path:
                # 没有设置本地路径，提示用户
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "请先配置社区词典文件路径。"))
                return
            
            # 弹窗询问用户是否更新
            if self.parent.winfo_exists():
                def ask_update():
                    # 显示确认对话框
                    from tkinter import messagebox
                    result = messagebox.askyesno(
                        "发现新版本",
                        f"发现社区词典新版本！\n\n当前版本: {local_version}\n最新版本: {remote_version}\n\n是否立即更新?",
                        parent=self.parent
                    )
                    if result:
                        # 用户确认更新，执行下载
                        self._download_dict(remote_info, local_path)
                self.parent.after(0, ask_update)
        finally:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.download_dict_button.config(state="normal", text="检查/更新"))
    
    def _download_dict(self, remote_info, local_path):
        """
        下载词典文件（异步）
        """
        import threading
        
        # 启动新线程进行下载，避免阻塞主UI线程
        def download_thread():
            import requests
            import logging
            from gui.dialogs import DownloadProgressDialog
            from utils import config_manager
            import time
            
            # 创建进度对话框
            progress_dialog = None
            if self.parent.winfo_exists():
                # 使用after方法创建进度对话框，避免线程阻塞
                def create_progress_dialog():
                    setattr(self, "_progress_dialog", DownloadProgressDialog(self.parent, title="更新社区词典"))
                self.parent.after(0, create_progress_dialog)
                # 等待进度对话框创建完成
                for _ in range(10):  # 最多等待1秒
                    if hasattr(self, "_progress_dialog"):
                        progress_dialog = self._progress_dialog
                        break
                    time.sleep(0.1)
            
            # 下载词典
            url = remote_info.get("url")
            if not url:
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "无法获取远程词典下载链接。"))
                return
            
            # 应用GitHub加速
            url = self._apply_github_acceleration(url)
            
            try:
                # 增加超时时间，使用更稳定的连接
                response = requests.get(url, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                bytes_downloaded = 0
                last_update_time = 0
                update_interval = 0.1  # 控制进度更新频率，每100ms更新一次
                
                with open(local_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=16384):  # 增大chunk大小，提高下载速度
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                            # 控制进度更新频率，避免过多的UI更新导致卡顿
                            current_time = time.time()
                            if progress_dialog and self.parent.winfo_exists() and (current_time - last_update_time) > update_interval:
                                progress = (bytes_downloaded / total_size) * 100 if total_size > 0 else 0
                                # 使用lambda捕获当前值，避免闭包延迟绑定问题
                                def update_ui(p=progress, b=bytes_downloaded, t=total_size):
                                    if progress_dialog and self.parent.winfo_exists():
                                        try:
                                            progress_dialog.update_progress("下载词典", int(p), f"已下载 {b//1024}/{t//1024} KB")
                                        except Exception:
                                            pass  # 忽略UI更新错误
                                self.parent.after(0, update_ui)
                                last_update_time = current_time
                
                # 更新本地版本记录
                config_manager.update_config("last_dict_version", remote_info.get("version"))
                
                # 显示成功信息
                if self.parent.winfo_exists():
                    def show_success():
                        if self.parent.winfo_exists():
                            ui_utils.show_info("更新成功", f"社区词典已成功更新到版本 {remote_info.get('version')}。")
                    self.parent.after(0, show_success)
                    
            except Exception as e:
                logging.error(f"下载词典失败: {e}")
                if self.parent.winfo_exists():
                    def show_error():
                        if self.parent.winfo_exists():
                            ui_utils.show_error("更新失败", f"下载词典时发生错误: {e}")
                    self.parent.after(0, show_error)
            finally:
                # 关闭进度对话框
                if hasattr(self, "_progress_dialog"):
                    progress_dialog = self._progress_dialog
                    if progress_dialog and self.parent.winfo_exists():
                        def close_dialog():
                            try:
                                progress_dialog.close_dialog()
                            except Exception:
                                pass  # 忽略关闭错误
                        self.parent.after(0, close_dialog)
                    delattr(self, "_progress_dialog")
        
        # 启动下载线程
        threading.Thread(target=download_thread, daemon=True).start()
    
    def _apply_github_acceleration(self, url):
        """
        应用GitHub加速
        """
        from utils import config_manager
        
        # 检查是否是GitHub链接
        if "github.com" in url:
            # 获取配置的GitHub代理
            config = config_manager.load_config()
            github_proxies = config.get("github_proxies", [])
            
            if github_proxies:
                # 使用第一个代理
                proxy = github_proxies[0]
                # 构建加速链接
                if url.startswith("https://github.com/"):
                    # 替换为加速链接
                    accelerated_url = proxy + url[8:]  # 移除 https:// 前缀
                    return accelerated_url
        return url
    
    def _get_remote_dict_info(self) -> dict | None:
        import requests
        import logging
        api_url = "https://api.github.com/repos/VM-Chinese-translate-group/i18n-Dict-Extender/releases/latest"
        try:
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            version = data.get("tag_name")
            url = next((asset.get("browser_download_url") for asset in data.get("assets", []) if asset.get("name") == "Dict-Sqlite.db"), None)
            if version and url: return {"version": version, "url": url}
        except Exception as e: logging.error(f"获取远程词典信息失败: {e}")
        return None
    
    def _create_term_database(self):
        community_dict_path = self.community_dict_var.get()
        if not community_dict_path:
            ui_utils.show_error("错误", "请先配置社区词典文件路径。")
            return
        
        try:
            # 显示确认对话框
            if not messagebox.askyesno("确认创建", 
                                      "确定要从社区词典创建术语库吗？\n这将导入单词数量为1-2个的术语到术语库中。", 
                                      parent=self.parent):
                return
            
            # 创建进度对话框
            progress_dialog = DownloadProgressDialog(self.parent, title="创建术语库")
            
            # 定义创建线程函数
            def create_thread_func():
                try:
                    # 步骤1: 连接社区词典数据库
                    progress_dialog.update_progress("连接数据库", 0, "")
                    
                    with sqlite3.connect(f"file:{community_dict_path}?mode=ro", uri=True) as conn:
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                        
                        # 步骤2: 加载术语库和现有术语
                        progress_dialog.update_progress("加载术语库", 10, "")
                        
                        term_db = TermDatabase()
                        existing_terms = term_db.get_all_terms()
                        existing_originals = {term["original"].lower() for term in existing_terms}
                        
                        # 步骤3: 查询总条目数，用于进度显示
                        progress_dialog.update_progress("获取总条目数", 20, "")
                        
                        # 先查询总条目数，让用户知道要处理多少数据
                        cursor.execute("SELECT COUNT(*) FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL")
                        total_dict_entries = cursor.fetchone()[0]
                        progress_dialog.update_progress("准备数据", 30, f"共 {total_dict_entries} 条数据")
                        
                        # 步骤4: 配置多线程参数
                        progress_dialog.update_progress("配置线程", 40, "")
                        
                        # 优化1: 根据系统CPU核心数动态调整线程数量
                        num_threads = os.cpu_count() or 4
                        # 限制最大线程数为8，避免过多线程导致系统资源竞争
                        num_threads = min(num_threads, 8)
                        # 确保至少有2个线程
                        num_threads = max(num_threads, 2)
                        
                        # 优化2: 根据线程数和数据量计算最佳批次大小
                        # 每个批次大小在1000-5000条之间，平衡内存使用和并行效率
                        batch_size = math.ceil(total_dict_entries / num_threads)
                        batch_size = max(1000, min(5000, batch_size))
                        
                        # 优化3: 预编译SQL查询，避免重复编译
                        sql = "SELECT ORIGIN_NAME, TRANS_NAME FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL"
                        
                        # 简化验证逻辑，使用更高效的实现
                        def is_valid_term(original):
                            """快速验证术语是否为1-2个单词"""
                            if not original:
                                return False
                            # 使用更快的字符串操作替代split()
                            space_count = original.count(' ')
                            return 0 <= space_count <= 1
                        
                        # 定义线程处理函数
                        def process_batch(batch_rows, batch_id, result_queue):
                            """处理数据批次"""
                            batch_import_count = 0
                            batch_skipped_count = 0
                            batch_terms = []
                            
                            # 每个线程都有自己的临时去重集合，避免全局锁
                            thread_skipped = set()
                            thread_skipped.update(existing_originals)  # 预先加载现有术语
                            
                            for row in batch_rows:
                                original = row["ORIGIN_NAME"].strip()
                                translation = row["TRANS_NAME"].strip()
                                
                                if original and translation:
                                    if is_valid_term(original):
                                        original_lower = original.lower()
                                        # 检查是否已存在（使用局部集合快速判断）
                                        if original_lower not in thread_skipped:
                                            batch_terms.append((original, translation))
                                            batch_import_count += 1
                                            thread_skipped.add(original_lower)
                                        else:
                                            batch_skipped_count += 1
                                    else:
                                        batch_skipped_count += 1
                                else:
                                    batch_skipped_count += 1
                            
                            # 将结果放入队列
                            result_queue.append((batch_id, batch_terms, batch_import, batch_skip))
                        
                        # 步骤5: 执行多线程处理
                        progress_dialog.update_progress("多线程处理", 50, f"使用 {num_threads} 线程")
                        
                        # 结果队列，用于收集各线程结果
                        result_queue = deque()
                        
                        # 使用线程池执行多线程处理
                        with ThreadPoolExecutor(max_workers=num_threads) as executor:
                            # 执行SQL查询，获取所有数据
                            cursor.execute(sql)
                            all_rows = cursor.fetchall()
                            
                            # 将数据分成多个批次
                            batches = [all_rows[i:i+batch_size] for i in range(0, len(all_rows), batch_size)]
                            
                            # 提交所有批次任务
                            futures = []
                            for i, batch in enumerate(batches):
                                future = executor.submit(process_batch, batch, i, result_queue)
                                futures.append(future)
                            
                            # 监控进度
                            completed_batches = 0
                            total_batches = len(futures)
                            
                            while completed_batches < total_batches:
                                completed_batches = sum(1 for f in futures if f.done())
                                current_progress = 50 + (35 * completed_batches // total_batches)  # 50%-85%
                                progress_dialog.update_progress("处理数据", current_progress, f"已完成 {completed_batches}/{total_batches} 个批次")
                                time.sleep(0.2)  # 更频繁的进度更新，让用户感觉更流畅
                            
                            # 等待所有任务完成
                            concurrent.futures.wait(futures)
                        
                        # 步骤6: 合并结果
                        progress_dialog.update_progress("合并结果", 85, "")
                        
                        import_count = 0
                        skipped_count = 0
                        all_terms_to_add = []
                        
                        # 按批次ID排序，确保顺序正确
                        sorted_results = sorted(result_queue, key=lambda x: x[0])
                        
                        # 合并所有结果
                        for batch_id, batch_terms, batch_import, batch_skip in sorted_results:
                            all_terms_to_add.extend(batch_terms)
                            import_count += batch_import
                            skipped_count += batch_skip
                        
                        # 步骤7: 优化的分批次导入
                        progress_dialog.update_progress("导入术语", 90, "")
                        
                        if all_terms_to_add:
                            # 优化4: 根据数据量动态调整导入批次大小
                            # 数据量越大，批次越大，减少IO操作次数
                            import_batch_size = min(1000, max(200, len(all_terms_to_add) // 10))
                            
                            # 优化5: 预创建所有批次，减少循环内计算
                            import_batches = [all_terms_to_add[i:i+import_batch_size] for i in range(0, len(all_terms_to_add), import_batch_size)]
                            
                            for i, batch in enumerate(import_batches):
                                # 直接调用批量导入方法，避免创建临时字典
                                term_db.add_terms_batch([{"original": orig, "translation": trans} for orig, trans in batch])
                                # 更新进度
                                batch_progress = (i / len(import_batches)) * 10
                                progress_dialog.update_progress("导入术语", 90 + int(batch_progress), f"已导入 {min((i + 1) * import_batch_size, len(all_terms_to_add))}/{len(all_terms_to_add)} 个术语")
                        
                        # 关闭进度对话框
                        self.parent.after(0, progress_dialog.close_dialog)
                        
                        # 显示结果
                        self.parent.after(0, lambda: ui_utils.show_info(
                            "创建成功", 
                            f"术语库创建完成！\n成功导入 {import_count} 个术语，跳过 {skipped_count} 个条目。\n使用 {num_threads} 线程并行处理，大幅提高了导入速度。"
                        ))
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.parent.after(0, progress_dialog.close_dialog)
                    self.parent.after(0, lambda: ui_utils.show_error(
                        "创建失败", 
                        f"创建术语库时发生错误：{str(e)}"
                    ))
            
            # 启动创建线程
            threading.Thread(target=create_thread_func, daemon=True).start()
            
        except Exception as e:
            ui_utils.show_error("错误", f"创建术语库时发生错误：{str(e)}")
    
    def get_config(self):
        return {
            "community_dict_path": self.community_dict_var.get(),
            "community_pack_paths": list(self.packs_listbox.get(0, tk.END))
        }
