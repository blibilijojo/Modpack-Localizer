# gui/main_window.py

import tkinter as tk
from tkinter import messagebox, Toplevel
import ttkbootstrap as ttk
import logging
import threading
import webbrowser
import sys
import subprocess
from pathlib import Path
import os
from gui.custom_widgets import ToolTip
from utils import config_manager, update_checker
from _version import __version__ 

class MainWindow:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title(f"Minecraft 整合包汉化工坊 Pro - v{__version__}")
        self.root.geometry("850x950") 
        self.root.minsize(800, 850)
        
        self._create_menu()
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)
        notebook_frame = ttk.Frame(main_pane)
        main_pane.add(notebook_frame, weight=1)
        notebook = ttk.Notebook(notebook_frame)
        notebook.pack(fill="both", expand=True)

        from gui.tab_main_control import TabMainControl
        from gui.tab_ai_service import TabAiService
        from gui.tab_ai_parameters import TabAiParameters
        from gui.tab_pack_settings import TabPackSettings
        
        ai_service_tab = TabAiService(notebook)
        ai_parameters_tab = TabAiParameters(notebook)
        pack_settings_tab = TabPackSettings(notebook)
        self.main_control_tab = TabMainControl(notebook, ai_service_tab, ai_parameters_tab, pack_settings_tab)

        notebook.add(self.main_control_tab.frame, text=" 一键汉化 ")
        notebook.add(ai_service_tab.frame, text=" AI 服务 ")
        notebook.add(ai_parameters_tab.frame, text=" AI 参数 ")
        notebook.add(pack_settings_tab.frame, text=" 资源包设置 ")
        main_pane.add(self.main_control_tab.get_log_frame(), weight=1)

        from utils.logger_setup import setup_logging
        setup_logging(self.main_control_tab.log_message)
        self.start_update_check()

    def _create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        help_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="检查更新", command=lambda: self.start_update_check(user_initiated=True))
        help_menu.add_separator()
        help_menu.add_command(label="访问项目主页", command=lambda: webbrowser.open("https://github.com/blibilijojo/Modpack-Localizer"))

    def start_update_check(self, user_initiated=False):
        if not getattr(sys, 'frozen', False):
            if user_initiated:
                messagebox.showinfo("提示", "此功能仅在打包后的 .exe 程序中可用。")
            return

        logging.info("准备启动后台更新检查线程...")
        update_thread = threading.Thread(target=self._check_for_updates_thread, args=(user_initiated,), daemon=True)
        update_thread.start()

    def _check_for_updates_thread(self, user_initiated):
        update_info = update_checker.check_for_updates(__version__)
        if update_info:
            self.root.after(0, self._show_update_dialog, update_info)
        elif user_initiated:
            self.root.after(0, lambda: messagebox.showinfo("检查更新", "恭喜，您使用的已是最新版本！"))

    def _show_update_dialog(self, update_info: dict):
        dialog = Toplevel(self.root)
        dialog.title(f"发现新版本: {update_info['version']}")
        dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)

        message_frame = ttk.Frame(dialog, padding=20)
        message_frame.pack(fill="x")
        
        message_text = (f"一个新版本 ({update_info['version']}) 可用！\n\n"
                        "是否立即下载并安装更新？")
        ttk.Label(message_frame, text=message_text, justify="left").pack(anchor="w")

        progress_frame = ttk.Frame(dialog, padding=(20, 10))
        progress_frame.pack(fill="x")
        self.status_label = ttk.Label(progress_frame, text="准备就绪")
        self.status_label.pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress_frame, length=300, mode='determinate')
        self.progress_bar.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill="x")
        
        def on_update():
            self.update_btn.config(state="disabled"); self.later_btn.config(state="disabled")
            threading.Thread(target=self._start_update_process, args=(update_info,), daemon=True).start()

        self.update_btn = ttk.Button(btn_frame, text="立即更新", command=on_update, bootstyle="success")
        self.update_btn.pack(side="right", padx=5)
        self.later_btn = ttk.Button(btn_frame, text="稍后提醒", command=dialog.destroy)
        self.later_btn.pack(side="right")
        
    def _update_progress_ui(self, status, percentage, speed):
        self.status_label.config(text=f"{status}... {int(percentage)}% ({speed})")
        self.progress_bar['value'] = percentage

    def _start_update_process(self, update_info: dict):
        current_exe_path = Path(sys.executable)
        exe_dir = current_exe_path.parent
        
        new_exe_temp_path = current_exe_path.with_suffix(current_exe_path.suffix + ".new")
        old_exe_backup_path = current_exe_path.with_suffix(current_exe_path.suffix + ".old")

        download_ok = update_checker.download_update(update_info["asset_url"], new_exe_temp_path,
                                                     lambda s, p, sp: self.root.after(0, self._update_progress_ui, s, p, sp))
        if not download_ok:
            self.root.after(0, lambda: messagebox.showerror("更新失败", "下载新版本失败，请检查网络或稍后重试。", parent=self.root))
            self.root.after(0, self.later_btn.master.master.destroy)
            return

        batch_script_path = exe_dir / "update.bat"
        script_content = f"""
@echo off
echo 更新程序正在执行...
echo.
ping 127.0.0.1 -n 4 > nul
echo 备份当前版本...
move /Y "{current_exe_path}" "{old_exe_backup_path}"
echo 应用新版本...
move /Y "{new_exe_temp_path}" "{current_exe_path}"
echo 重启应用程序...
start "" "{current_exe_path}"
del "%~f0"
"""
        with open(batch_script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        subprocess.Popen(f'"{batch_script_path}"', shell=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
        self.root.after(100, self.root.destroy)