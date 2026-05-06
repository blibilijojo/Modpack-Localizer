"""局域网传输对话框 - 浏览远程设备项目并下载。"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from tkinter import ttk as tk_ttk, messagebox
from typing import Dict, List, Optional

import ttkbootstrap as ttk

from core.lan_transfer_service import LANTransferService, DeviceInfo
from core.save_format_adapter import convert_for_desktop


class LANTransferDialog(ttk.Toplevel):
    """局域网传输对话框。"""

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.parent = parent
        self.main_window = main_window
        self.title("局域网传输")
        self.geometry("700x620")
        self.minsize(600, 500)
        self.resizable(True, True)

        self.transient(parent)
        self.grab_set()

        self.service = LANTransferService()
        self.devices: Dict[str, DeviceInfo] = {}
        self._server_running = False
        self._discovering = False
        self._alive = True
        self._browsing = False
        self._downloading = False
        self._selected_device: Optional[DeviceInfo] = None
        self._remote_projects: List[dict] = []

        self.service.set_device_found_callback(self._on_device_found)
        self.service.set_file_received_callback(self._on_file_received)
        self.service.set_project_providers(
            list_provider=self._provide_project_list,
            data_provider=self._provide_project_data,
        )

        self._create_widgets()
        self._auto_start_server()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _safe_after(self, func):
        if not self._alive:
            return
        try:
            self.after(0, func)
        except Exception:
            pass

    def _auto_start_server(self):
        try:
            port = self.service.start_server()
            self._server_running = True
            self._update_server_status()
            self._log(f"服务已启动，HTTP 端口: {port}")
            self._log("其他设备可以浏览和下载你的项目")
        except Exception as e:
            self._log(f"服务启动失败: {e}")

    def _update_server_status(self):
        port = self.service.http_port or "未启动"
        self.server_status_label.configure(
            text=f"服务状态: {'运行中' if self._server_running else '已停止'} · 端口: {port}"
        )

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        info_frame = tk_ttk.LabelFrame(main_frame, text="本机信息", padding=6)
        info_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(info_frame, text=f"设备名称: {self.service.device_name}").pack(anchor="w")
        self.server_status_label = ttk.Label(info_frame, text="服务状态: 启动中...")
        self.server_status_label.pack(anchor="w")

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

        self._create_browse_tab()
        self._create_receive_tab()

    def _create_browse_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  浏览远程项目  ")

        scan_frame = ttk.Frame(tab)
        scan_frame.pack(fill="x", pady=(0, 8))
        self.scan_btn = ttk.Button(scan_frame, text="扫描设备", command=self._start_scan, bootstyle="primary")
        self.scan_btn.pack(side="left", padx=(0, 10))
        self.scan_status = ttk.Label(scan_frame, text="点击扫描局域网中的设备", bootstyle="secondary")
        self.scan_status.pack(side="left", fill="x", expand=True)

        manual_frame = ttk.Frame(tab)
        manual_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(manual_frame, text="手动连接IP:").pack(side="left", padx=(0, 5))
        self.ip_entry = ttk.Entry(manual_frame, width=20)
        self.ip_entry.pack(side="left", padx=(0, 5))
        self.probe_btn = ttk.Button(manual_frame, text="连接", command=self._probe_device, bootstyle="info")
        self.probe_btn.pack(side="left")

        device_frame = tk_ttk.LabelFrame(tab, text="发现的设备", padding=5)
        device_frame.pack(fill="x", pady=(0, 8))
        columns = ("name", "platform", "ip")
        self.device_tree = ttk.Treeview(device_frame, columns=columns, show="headings", height=4)
        self.device_tree.heading("name", text="设备名称")
        self.device_tree.heading("platform", text="平台")
        self.device_tree.heading("ip", text="IP 地址")
        self.device_tree.column("name", width=200)
        self.device_tree.column("platform", width=80)
        self.device_tree.column("ip", width=150)
        scrollbar = ttk.Scrollbar(device_frame, orient="vertical", command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.device_tree.pack(fill="x", expand=True)

        browse_frame = ttk.Frame(tab)
        browse_frame.pack(fill="x", pady=(0, 8))
        self.browse_btn = ttk.Button(browse_frame, text="浏览项目", command=self._browse_projects, bootstyle="info")
        self.browse_btn.pack(side="left", padx=(0, 10))
        self.browse_status = ttk.Label(browse_frame, text="选择设备后点击浏览", bootstyle="secondary")
        self.browse_status.pack(side="left", fill="x", expand=True)

        proj_frame = tk_ttk.LabelFrame(tab, text="远程项目列表", padding=5)
        proj_frame.pack(fill="both", expand=True, pady=(0, 8))
        p_cols = ("name", "namespaces", "mc_version", "status")
        self.project_tree = ttk.Treeview(proj_frame, columns=p_cols, show="headings", height=6)
        self.project_tree.heading("name", text="项目名称")
        self.project_tree.heading("namespaces", text="命名空间数")
        self.project_tree.heading("mc_version", text="MC版本")
        self.project_tree.heading("status", text="状态")
        self.project_tree.column("name", width=200)
        self.project_tree.column("namespaces", width=80)
        self.project_tree.column("mc_version", width=100)
        self.project_tree.column("status", width=80)
        p_scrollbar = ttk.Scrollbar(proj_frame, orient="vertical", command=self.project_tree.yview)
        self.project_tree.configure(yscrollcommand=p_scrollbar.set)
        p_scrollbar.pack(side="right", fill="y")
        self.project_tree.pack(fill="both", expand=True)

        dl_frame = ttk.Frame(tab)
        dl_frame.pack(fill="x")
        self.download_btn = ttk.Button(dl_frame, text="下载选中项目", command=self._download_project, bootstyle="success")
        self.download_btn.pack(side="right")
        self.download_status = ttk.Label(dl_frame, text="", bootstyle="secondary")
        self.download_status.pack(side="left", fill="x", expand=True)

    def _create_receive_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  接收日志  ")

        log_frame = tk_ttk.LabelFrame(tab, text="传输日志", padding=5)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=15, state="disabled", wrap="word")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

    def _start_scan(self):
        if self._discovering:
            return
        self._discovering = True
        self.devices.clear()
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        self._remote_projects.clear()
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)

        self.scan_btn.configure(state="disabled")
        self.scan_status.configure(text="正在扫描...")
        self.service.start_discovery()

        def _finish_scan():
            time.sleep(12)
            self._discovering = False
            self._safe_after(lambda: self.scan_btn.configure(state="normal"))
            count = len(self.devices)
            self._safe_after(lambda c=count: self.scan_status.configure(
                text=f"扫描完成，发现 {c} 个设备" if c > 0 else "未发现设备，请确认对方已开启局域网传输"
            ))
        threading.Thread(target=_finish_scan, daemon=True).start()

    def _probe_device(self):
        ip = self.ip_entry.get().strip()
        if not ip:
            messagebox.showwarning("提示", "请输入IP地址", parent=self)
            return
        import re
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            messagebox.showwarning("提示", "IP地址格式不正确", parent=self)
            return
        self.probe_btn.configure(state="disabled")
        self._log(f"正在探测 {ip} ...")

        def _do_probe():
            try:
                device = self.service.probe_device(ip)
                if device:
                    self._safe_after(lambda: self._log(f"发现设备: {device.name} ({device.platform})"))
                    self._safe_after(lambda: self.scan_status.configure(
                        text=f"手动连接成功: {device.name}"
                    ))
                else:
                    self._safe_after(lambda: self._log(f"未在 {ip} 发现服务"))
                    self._safe_after(lambda: self.scan_status.configure(
                        text=f"未在 {ip} 发现服务"
                    ))
            except Exception as e:
                self._safe_after(lambda err=str(e): self._log(f"探测失败: {err}"))
            finally:
                self._safe_after(lambda: self.probe_btn.configure(state="normal"))

        threading.Thread(target=_do_probe, daemon=True).start()

    def _on_device_found(self, device: DeviceInfo):
        if device.ip in self.devices:
            return
        self.devices[device.ip] = device
        platform_text = {"mobile": "手机", "desktop": "电脑"}.get(device.platform, device.platform)
        self._safe_after(lambda d=device, p=platform_text: self._add_device_to_tree(d, p))

    def _add_device_to_tree(self, device: DeviceInfo, platform_text: str):
        self.device_tree.insert("", "end", iid=device.ip, values=(
            device.name, platform_text, device.ip
        ))
        self.scan_status.configure(text=f"发现 {len(self.devices)} 个设备")

    def _browse_projects(self):
        selection = self.device_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个设备", parent=self)
            return

        target_ip = selection[0]
        device = self.devices.get(target_ip)
        if not device:
            return

        self._selected_device = device
        self._browsing = True
        self.browse_btn.configure(state="disabled")
        self.browse_status.configure(text=f"正在连接 {device.name}...")

        for item in self.project_tree.get_children():
            self.project_tree.delete(item)

        def _do_browse():
            try:
                projects = self.service.fetch_projects(device.ip, device.http_port)
                self._remote_projects = projects
                self._safe_after(lambda: self._populate_project_tree(projects))
                self._safe_after(lambda: self.browse_status.configure(
                    text=f"共 {len(projects)} 个项目"
                ))
            except Exception as e:
                self._safe_after(lambda err=str(e): self.browse_status.configure(text=f"连接失败: {err}"))
                self._safe_after(lambda err=str(e): self._log(f"浏览失败: {err}"))
            finally:
                self._browsing = False
                self._safe_after(lambda: self.browse_btn.configure(state="normal"))

        threading.Thread(target=_do_browse, daemon=True).start()

    def _populate_project_tree(self, projects: list):
        for p in projects:
            ns_count = p.get("namespace_count", 0)
            self.project_tree.insert("", "end", iid=p.get("id", ""), values=(
                p.get("name", "未命名"),
                ns_count,
                p.get("mc_version", ""),
                p.get("status", ""),
            ))

    def _download_project(self):
        selection = self.project_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个项目", parent=self)
            return
        if not self._selected_device:
            messagebox.showwarning("提示", "请先选择设备并浏览项目", parent=self)
            return

        project_id = selection[0]
        project_name = ""
        for p in self._remote_projects:
            if p.get("id") == project_id:
                project_name = p.get("name", project_id)
                break

        self._downloading = True
        self.download_btn.configure(state="disabled")
        self.download_status.configure(text=f"正在下载 \"{project_name}\"...")
        self._log(f"开始下载: {project_name}")

        def _do_download():
            try:
                save_data = self.service.fetch_project_data(
                    self._selected_device.ip, self._selected_device.http_port, project_id
                )
                desktop_data = convert_for_desktop(save_data)
                final_name = desktop_data.get("save_data", {}).get("project_name", project_name)

                self._safe_after(lambda: self._log(f"下载完成，正在导入: {final_name}"))
                self._safe_after(lambda: self._load_downloaded_project(desktop_data, final_name))
                self._safe_after(lambda: self.download_status.configure(text=f"已下载并导入: {final_name}"))
            except Exception as e:
                self._safe_after(lambda err=str(e): self.download_status.configure(text=f"下载失败: {err}"))
                self._safe_after(lambda err=str(e): self._log(f"下载失败: {err}"))
            finally:
                self._downloading = False
                self._safe_after(lambda: self.download_btn.configure(state="normal"))

        threading.Thread(target=_do_download, daemon=True).start()

    def _load_downloaded_project(self, save_data: dict, project_name: str):
        try:
            self.main_window._add_new_tab(select_tab=True, show_initial_welcome=False)
            current_tab_id = self.main_window.notebook.select()
            if not current_tab_id:
                return
            project_tab = self.main_window.project_tabs.get(current_tab_id)
            if project_tab:
                project_tab.load_from_save_data(save_data, project_name)
                self._log(f"项目 \"{project_name}\" 已导入成功")
                messagebox.showinfo(
                    "下载成功",
                    f"项目 \"{project_name}\" 已下载并导入到新标签页。",
                    parent=self,
                )
            else:
                self._log("无法找到新创建的标签页")
        except Exception as e:
            self._log(f"导入项目失败: {e}")
            logging.error(f"导入下载的项目失败: {e}", exc_info=True)

    def _provide_project_list(self) -> list:
        """提供本机项目列表供远程设备浏览。"""
        projects = []
        for tab_id, tab in self.main_window.project_tabs.items():
            ns_count = 0
            if tab.workbench_instance and tab.workbench_instance.translation_data:
                ns_count = len(tab.workbench_instance.translation_data)
            mc_version = ""
            if tab.orchestrator:
                mc_version = getattr(tab.orchestrator, "target_minecraft_version", "")
            projects.append({
                "id": tab_id,
                "name": tab.project_name,
                "namespace_count": ns_count,
                "mc_version": mc_version,
                "status": "active" if tab.workbench_instance else "ready",
            })
        return projects

    def _provide_project_data(self, project_id: str) -> Optional[dict]:
        """提供本机指定项目的存档数据。"""
        tab = self.main_window.project_tabs.get(project_id)
        if not tab:
            return None
        return self._build_save_data(tab)

    def _build_save_data(self, project_tab) -> Optional[dict]:
        workbench = project_tab.workbench_instance
        if not workbench or not workbench.translation_data:
            return None
        translation_state = {}
        for ns, ns_data in workbench.translation_data.items():
            items = ns_data.get("items", [])
            if not items:
                continue
            ns_dict = {}
            for item in items:
                key = item.get("key", "")
                ns_dict[key] = {
                    "key": key, "origin": item.get("en", ""),
                    "zh": item.get("zh", ""), "source": item.get("source", "unknown"),
                    "mod": ns_data.get("jar_name", ""),
                }
            translation_state[ns] = ns_dict
        if not translation_state:
            return None
        mc_version = ""
        if project_tab.orchestrator:
            mc_version = getattr(project_tab.orchestrator, "target_minecraft_version", "")
        return {
            "version": "0.2.2",
            "save_data": {
                "project_name": project_tab.project_name,
                "target_minecraft_version": mc_version,
                "translation_state": translation_state,
                "mod_files": [], "modrinth_mods": [], "curseforge_mods": [],
            },
        }

    def _on_file_received(self, save_data: dict, sender_name: str):
        self._safe_after(lambda: self._log(f"收到来自 {sender_name} 的存档"))
        try:
            desktop_data = convert_for_desktop(save_data)
            project_name = desktop_data.get("save_data", {}).get("project_name", "未知项目")
            self._safe_after(lambda: self._log(f"项目: {project_name}，正在导入..."))
            self._safe_after(lambda: self._load_downloaded_project(desktop_data, project_name))
        except Exception as e:
            self._safe_after(lambda err=str(e): self._log(f"处理存档失败: {err}"))

    def _log(self, message: str):
        if not self._alive:
            return
        def _do():
            if not self._alive:
                return
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"{message}\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except Exception:
                pass
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self._safe_after(_do)

    def _on_close(self):
        self._alive = False
        self._discovering = False
        if self._server_running:
            self.service.stop_server()
        self.service._running = False
        self.destroy()
