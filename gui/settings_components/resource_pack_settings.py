from __future__ import annotations
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
from collections import deque
from gui.settings_components.shared_utils import (
    apply_github_acceleration,
    get_remote_dict_info,
    download_dict_file,
)

class ResourcePackSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        self._create_variables()
        self._create_widgets()

    def _create_variables(self):
        self.community_dict_var = tk.StringVar(value=self.config.get("community_dict_dir", ""))
        self._bind_events()

    def _bind_events(self):
        self.community_dict_var.trace_add("write", lambda *args: self.save_callback())

    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self._create_resource_pack_settings(main_frame)
        self._create_community_packs_list(main_frame)

    def _create_resource_pack_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="术语词典", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)

        dict_path_frame = ttk.Frame(frame)
        dict_path_frame.pack(fill="x", pady=5)
        dict_label = ttk.Label(dict_path_frame, text="词典目录:", width=15)
        dict_label.pack(side="left")
        custom_widgets.ToolTip(dict_label, "可选。存放社区词典文件的目录，程序会在该目录中使用 Dict-Sqlite.db 文件\n可以从GitHub下载最新的社区维护版本。")
        dict_entry = ttk.Entry(dict_path_frame, textvariable=self.community_dict_var, takefocus=False)
        dict_entry.pack(side="left", fill="x", expand=True, padx=5)
        dict_entry.after_idle(dict_entry.selection_clear)
        browse_btn = ttk.Button(dict_path_frame, text="浏览...", command=lambda: ui_utils.browse_directory(self.community_dict_var), bootstyle="primary-outline")
        browse_btn.pack(side="left")
        self.download_dict_button = ttk.Button(dict_path_frame, text="检查/更新", command=self._check_and_update_dict_async, bootstyle="info")
        self.download_dict_button.pack(side="left", padx=(5, 5))

    def _create_community_packs_list(self, parent):
        packs_frame = tk_ttk.LabelFrame(parent, text="附加汉化包 (优先级由上至下)", padding="10")
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
        list_btn_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(list_btn_frame, text="添加", command=self._add_packs, bootstyle="success-outline", width=8).pack(side="left", padx=2)
        ttk.Button(list_btn_frame, text="移除", command=self._remove_packs, bootstyle="danger-outline", width=8).pack(side="left", padx=2)
        ttk.Frame(list_btn_frame).pack(side="left", fill="x", expand=True)
        ttk.Button(list_btn_frame, text="上移", command=lambda: self._move_pack(-1), bootstyle="info-outline", width=8).pack(side="left", padx=2)
        ttk.Button(list_btn_frame, text="下移", command=lambda: self._move_pack(1), bootstyle="info-outline", width=8).pack(side="left", padx=2)

    def _add_packs(self):
        paths = filedialog.askopenfilenames(title="选择一个或多个第三方汉化包", filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")])
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
        if not indices:
            return
        for i in sorted(list(indices), reverse=(direction < 0)):
            if 0 <= i + direction < self.packs_listbox.size():
                text = self.packs_listbox.get(i)
                self.packs_listbox.delete(i)
                self.packs_listbox.insert(i + direction, text)
                self.packs_listbox.selection_set(i + direction)
        self.save_callback()

    def _check_and_update_dict_async(self):
        self.download_dict_button.config(state="disabled", text="检查中...")
        from utils.download_manager import download_manager
        download_manager.submit(self._dict_update_worker)

    def _dict_update_worker(self):
        from pathlib import Path
        from utils import config_manager

        try:
            remote_info = get_remote_dict_info()
            if not remote_info:
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "无法获取远程词典信息，请检查网络连接。"))
                return

            community_dict_dir = self.community_dict_var.get()
            if community_dict_dir:
                local_path = Path(community_dict_dir) / "Dict-Sqlite.db"
            else:
                local_path = None

            local_version = config_manager.load_config().get("last_dict_version", "0.0.0")
            remote_version = remote_info.get("version", "0.0.0")

            if local_path and local_path.exists():
                if local_version == remote_version:
                    if self.parent.winfo_exists():
                        self.parent.after(0, lambda: ui_utils.show_info("检查完成", "社区词典已是最新版本。"))
                    return

            if not community_dict_dir:
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "请先配置社区词典目录路径。"))
                return

            dict_dir = Path(community_dict_dir)
            if not dict_dir.exists() or not dict_dir.is_dir():
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", "社区词典目录不存在或不是有效目录。"))
                return

            if self.parent.winfo_exists():
                def ask_update():
                    result = messagebox.askyesno(
                        "发现新版本",
                        f"发现社区词典新版本！\n\n当前版本: {local_version}\n最新版本: {remote_version}\n\n是否立即更新?",
                        parent=self.parent
                    )
                    if result:
                        self._download_dict(remote_info, local_path)
                self.parent.after(0, ask_update)
        finally:
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.download_dict_button.config(state="normal", text="检查/更新"))

    def _download_dict(self, remote_info, local_path):
        from utils.download_manager import download_manager

        def download_thread():
            import logging
            import time

            logging.info(f"开始下载社区词典，版本: {remote_info.get('version')}")
            logging.info(f"下载地址: {remote_info.get('url')}")
            logging.info(f"保存路径: {local_path}")

            progress_dialog = None
            if self.parent.winfo_exists():
                def create_progress_dialog():
                    setattr(self, "_progress_dialog", DownloadProgressDialog(self.parent, title="更新社区词典"))
                self.parent.after(0, create_progress_dialog)
                for _ in range(10):
                    if hasattr(self, "_progress_dialog"):
                        progress_dialog = self._progress_dialog
                        break
                    time.sleep(0.1)

            def progress_callback(progress, bytes_downloaded, total_size):
                if progress_dialog and self.parent.winfo_exists():
                    try:
                        progress_dialog.update_progress("下载词典", int(progress), f"已下载 {bytes_downloaded // 1024}/{total_size // 1024} KB")
                    except Exception:
                        pass

            success, message = download_dict_file(remote_info, local_path, progress_callback)

            if hasattr(self, "_progress_dialog"):
                progress_dialog = self._progress_dialog
                if progress_dialog and self.parent.winfo_exists():
                    def close_dialog():
                        try:
                            progress_dialog.close_dialog()
                        except Exception:
                            pass
                    self.parent.after(0, close_dialog)
                delattr(self, "_progress_dialog")

            if self.parent.winfo_exists():
                if success:
                    self.parent.after(0, lambda: ui_utils.show_info("更新成功", message))
                else:
                    self.parent.after(0, lambda: ui_utils.show_error("更新失败", message))

        download_manager.submit(download_thread)

    def _create_term_database(self):
        from pathlib import Path

        community_dict_dir = self.community_dict_var.get()
        if not community_dict_dir:
            ui_utils.show_error("错误", "请先配置社区词典目录路径。")
            return

        community_dict_path = str(Path(community_dict_dir) / "Dict-Sqlite.db")

        try:
            if not messagebox.askyesno("确认创建",
                                       "确定要从社区词典创建术语库吗？\n这将导入单词数量为1-2个的术语到术语库中。",
                                       parent=self.parent):
                return

            progress_dialog = DownloadProgressDialog(self.parent, title="创建术语库")

            def create_thread_func():
                try:
                    progress_dialog.update_progress("连接数据库", 0, "")

                    with sqlite3.connect(f"file:{community_dict_path}?mode=ro", uri=True) as conn:
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()

                        progress_dialog.update_progress("加载术语库", 10, "")
                        term_db = TermDatabase()
                        existing_terms = term_db.get_all_terms()
                        existing_originals = {term["original"].lower() for term in existing_terms}

                        progress_dialog.update_progress("获取总条目数", 20, "")
                        cursor.execute("SELECT COUNT(*) FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL")
                        total_dict_entries = cursor.fetchone()[0]
                        progress_dialog.update_progress("准备数据", 30, f"共 {total_dict_entries} 条数据")

                        progress_dialog.update_progress("配置线程", 40, "")
                        num_threads = min(os.cpu_count() or 4, 8)
                        num_threads = max(num_threads, 2)
                        batch_size = max(1000, min(5000, math.ceil(total_dict_entries / num_threads)))

                        sql = "SELECT ORIGIN_NAME, TRANS_NAME FROM dict WHERE ORIGIN_NAME IS NOT NULL AND TRANS_NAME IS NOT NULL"

                        def is_valid_term(original):
                            if not original:
                                return False
                            space_count = original.count(' ')
                            return 0 <= space_count <= 1

                        def process_batch(batch_rows, batch_id, result_queue):
                            batch_import_count = 0
                            batch_skipped_count = 0
                            batch_terms = []
                            thread_skipped = set(existing_originals)

                            for row in batch_rows:
                                original = row["ORIGIN_NAME"].strip()
                                translation = row["TRANS_NAME"].strip()

                                if original and translation:
                                    if is_valid_term(original):
                                        original_lower = original.lower()
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

                            result_queue.append((batch_id, batch_terms, batch_import_count, batch_skipped_count))

                        progress_dialog.update_progress("多线程处理", 50, f"使用 {num_threads} 线程")
                        result_queue = deque()

                        with ThreadPoolExecutor(max_workers=num_threads) as executor:
                            cursor.execute(sql)
                            all_rows = cursor.fetchall()
                            batches = [all_rows[i:i + batch_size] for i in range(0, len(all_rows), batch_size)]
                            futures = [executor.submit(process_batch, batch, i, result_queue) for i, batch in enumerate(batches)]

                            completed_batches = 0
                            total_batches = len(futures)
                            while completed_batches < total_batches:
                                completed_batches = sum(1 for f in futures if f.done())
                                current_progress = 50 + (35 * completed_batches // total_batches)
                                progress_dialog.update_progress("处理数据", current_progress, f"已完成 {completed_batches}/{total_batches} 个批次")
                                time.sleep(0.2)
                            concurrent.futures.wait(futures)

                        progress_dialog.update_progress("合并结果", 85, "")
                        import_count = 0
                        skipped_count = 0
                        all_terms_to_add = []

                        for batch_id, batch_terms, batch_import_count, batch_skipped_count in sorted(result_queue, key=lambda x: x[0]):
                            all_terms_to_add.extend(batch_terms)
                            import_count += batch_import_count
                            skipped_count += batch_skipped_count

                        progress_dialog.update_progress("导入术语", 90, "")
                        if all_terms_to_add:
                            import_batch_size = min(1000, max(200, len(all_terms_to_add) // 10))
                            import_batches = [all_terms_to_add[i:i + import_batch_size] for i in range(0, len(all_terms_to_add), import_batch_size)]
                            for i, batch in enumerate(import_batches):
                                term_db.add_terms_batch([{"original": orig, "translation": trans} for orig, trans in batch])
                                batch_progress = (i / len(import_batches)) * 10
                                progress_dialog.update_progress("导入术语", 90 + int(batch_progress), f"已导入 {min((i + 1) * import_batch_size, len(all_terms_to_add))}/{len(all_terms_to_add)} 个术语")

                        self.parent.after(0, progress_dialog.close_dialog)
                        self.parent.after(0, lambda: ui_utils.show_info(
                            "创建成功",
                            f"术语库创建完成！\n成功导入 {import_count} 个术语，跳过 {skipped_count} 个条目。\n使用 {num_threads} 线程并行处理，大幅提高了导入速度。"
                        ))

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.parent.after(0, progress_dialog.close_dialog)
                    self.parent.after(0, lambda: ui_utils.show_error("创建失败", f"创建术语库时发生错误：{str(e)}"))

            threading.Thread(target=create_thread_func, daemon=True).start()

        except Exception as e:
            ui_utils.show_error("错误", f"创建术语库时发生错误：{str(e)}")

    def get_config(self):
        return {
            "community_dict_dir": self.community_dict_var.get(),
            "community_pack_paths": list(self.packs_listbox.get(0, tk.END))
        }
