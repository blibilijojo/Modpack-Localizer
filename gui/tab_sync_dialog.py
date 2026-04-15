"""当前标签页通过中继（Deno Deploy）发布 / 拉取项目状态。"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as ttk

from utils import config_manager, project_sync_relay

_log = logging.getLogger(__name__)


class TabSyncDialog(ttk.Toplevel):
    def __init__(self, parent: tk.Misc, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title("标签页中继同步")
        self.geometry("560x400")
        self.minsize(520, 360)
        self.transient(parent)
        self.resizable(True, True)

        cfg = config_manager.load_config()
        relay = (cfg.get("project_sync_relay_url") or "").strip()

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="作用范围：始终针对「当前选中的标签页」。\n"
            "首次向某房间发布为全量；之后在同一房间、同一标签上再次发布会走增量（仅变更的命名空间等）。\n"
            "拉取：若本标签此前从该房间同步过，会先询问中继是否有新版本（无则不下发整包）。",
            bootstyle="secondary",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        relay_row = ttk.Frame(outer)
        relay_row.pack(fill="x", pady=(0, 8))
        ttk.Label(relay_row, text="当前中继:", width=10).pack(side="left")
        ttk.Label(
            relay_row,
            text=relay if relay else "（未配置，请到 设置 → 外部服务 填写）",
            bootstyle="warning" if not relay else "secondary",
        ).pack(side="left", fill="x", expand=True)

        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True, pady=(8, 0))

        pub = ttk.Frame(nb, padding=10)
        pull = ttk.Frame(nb, padding=10)
        nb.add(pub, text=" 发布当前标签页 ")
        nb.add(pull, text=" 拉取到当前标签页 ")

        self.room_var = tk.StringVar(value=project_sync_relay.suggest_room_id())
        ttk.Label(pub, text="房间号（另一台设备填相同号码即可拉取）:").pack(anchor="w")
        room_row = ttk.Frame(pub)
        room_row.pack(fill="x", pady=(4, 8))
        ttk.Entry(room_row, textvariable=self.room_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(
            room_row,
            text="随机生成",
            command=lambda: self.room_var.set(project_sync_relay.suggest_room_id()),
            bootstyle="secondary-outline",
        ).pack(side="right")

        self.pub_status = tk.StringVar(value="")
        self.pub_btn = ttk.Button(
            pub,
            text="上传当前标签页到此房间",
            command=self._on_publish,
            bootstyle="primary",
        )
        self.pub_btn.pack(anchor="w", pady=(8, 4))
        ttk.Label(pub, textvariable=self.pub_status, bootstyle="secondary", wraplength=480, justify="left").pack(
            anchor="w", fill="x", pady=(4, 0)
        )

        self.pull_room_var = tk.StringVar(value="")
        ttk.Label(pull, text="要加入的房间号:").pack(anchor="w")
        ttk.Entry(pull, textvariable=self.pull_room_var).pack(fill="x", pady=(4, 8))
        self.pull_status = tk.StringVar(value="")
        self.pull_btn = ttk.Button(
            pull,
            text="拉取并覆盖当前标签页",
            command=self._on_pull,
            bootstyle="warning",
        )
        self.pull_btn.pack(anchor="w", pady=(8, 4))
        ttk.Label(pull, textvariable=self.pull_status, bootstyle="secondary", wraplength=480, justify="left").pack(
            anchor="w", fill="x", pady=(4, 0)
        )

        ttk.Button(outer, text="关闭", command=self.destroy, bootstyle="secondary").pack(anchor="e", pady=(12, 0))

    def _relay_base(self) -> str:
        cfg = config_manager.load_config()
        return (cfg.get("project_sync_relay_url") or "").strip()

    def _on_publish(self):
        base = self._relay_base()
        if not base:
            messagebox.showwarning("未配置中继", "请先在「设置 → 外部服务」填写「中继站点根地址」并检测连接。", parent=self)
            return
        tab = self.main_window._get_current_tab()
        if not tab:
            messagebox.showerror("错误", "没有可用的标签页。", parent=self)
            return
        state = tab.get_state()
        if not state:
            messagebox.showinfo(
                "无法上传",
                "当前标签页没有可同步的数据。\n请先在本标签完成提取并进入翻译工作台后再上传。",
                parent=self,
            )
            return
        rid, err = project_sync_relay.parse_room_id(self.room_var.get())
        if not rid:
            messagebox.showerror("房间号无效", err, parent=self)
            return

        _log.info(
            "[标签同步] 开始发布 房间=%r 中继地址=%r 标签ID=%r",
            rid,
            (base or "")[:400],
            getattr(tab, "tab_id", None),
        )
        self.pub_status.set("正在上传，请稍候…")
        self.pub_btn.config(state="disabled")

        def task():
            ok, msg, rev, mode = project_sync_relay.relay_publish_tab_state_smart(
                base, rid, tab, state
            )
            self.after(
                0,
                lambda o=ok, m=msg, r=rev, md=mode, t=tab, room=rid, st=state: self._publish_done(
                    o, m, r, md, t, room, st
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    def _publish_done(self, ok, msg, rev, mode, tab, room_id, state):
        self.pub_btn.config(state="normal")
        self.pub_status.set(msg)
        _mode_zh = {"full": "全量", "incremental": "增量", "noop": "跳过", "error": "错误"}.get(
            mode, mode
        )
        _log.info(
            "[标签同步] 发布结束 成功=%s 模式=%s 版本=%s 房间=%s 说明=%s",
            ok,
            _mode_zh,
            rev,
            room_id,
            (msg or "")[:500],
        )
        if ok:
            eff = rev if isinstance(rev, int) else getattr(tab, "_relay_sync_remote_rev", None)
            if isinstance(eff, int):
                project_sync_relay.tab_relay_fingerprint_write(tab, room_id, eff, state)
            if mode == "noop":
                messagebox.showinfo("同步", msg, parent=self)
            else:
                messagebox.showinfo("上传完成", msg, parent=self)
        else:
            messagebox.showerror("上传失败", msg, parent=self)

    def _on_pull(self):
        base = self._relay_base()
        if not base:
            messagebox.showwarning("未配置中继", "请先在「设置 → 外部服务」填写「中继站点根地址」。", parent=self)
            return
        tab = self.main_window._get_current_tab()
        if not tab:
            messagebox.showerror("错误", "没有可用的标签页。", parent=self)
            return
        rid, err = project_sync_relay.parse_room_id(self.pull_room_var.get())
        if not rid:
            messagebox.showerror("房间号无效", err, parent=self)
            return

        since_rev = None
        if rid == getattr(tab, "_relay_sync_room", None):
            sr = getattr(tab, "_relay_sync_remote_rev", None)
            if isinstance(sr, int) and sr > 0:
                since_rev = sr

        _log.info(
            "[标签同步] 开始拉取 房间=%r 本地已知版本=%r 中继地址=%r 标签ID=%r",
            rid,
            since_rev,
            (base or "")[:400],
            getattr(tab, "tab_id", None),
        )
        self.pull_status.set("正在拉取…")
        self.pull_btn.config(state="disabled")

        def task():
            ok, data, msg, rev, unchanged = project_sync_relay.relay_fetch_tab_state(
                base, rid, since_rev=since_rev
            )
            self.after(
                0,
                lambda o=ok, d=data, m=msg, r=rev, u=unchanged, t=tab, room=rid: self._pull_finish(
                    t, room, o, d, m, r, u
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    def _pull_finish(self, tab, room_id, ok, data, msg, rev, unchanged):
        self.pull_btn.config(state="normal")
        if not ok:
            _log.warning("[标签同步] 拉取失败 房间=%s 说明=%s", room_id, msg)
            self.pull_status.set(msg)
            messagebox.showerror("拉取失败", msg, parent=self)
            return
        if unchanged:
            _log.info("[标签同步] 拉取跳过 远端未变 房间=%s 版本=%s", room_id, rev)
            self.pull_status.set(msg)
            messagebox.showinfo("拉取", msg, parent=self)
            return
        if tab.get_state() is not None:
            if not messagebox.askyesno(
                "确认覆盖",
                "当前标签页已有项目数据，拉取后将完全替换为房间内的快照。\n是否继续？",
                parent=self,
            ):
                self.pull_status.set("已取消")
                return
        self._pull_apply(tab, room_id, data, msg, rev)

    def _pull_apply(self, tab, room_id: str, data: dict, msg: str, remote_rev):
        try:
            rv = remote_rev if isinstance(remote_rev, int) and remote_rev >= 1 else 1
            _log.info("[标签同步] 应用拉取数据 房间=%s 版本=%s", room_id, rv)
            tab.replace_with_synced_state(data, relay_room=room_id, relay_remote_rev=rv)
            self.pull_status.set(msg)
            messagebox.showinfo("拉取完成", "已加载到当前标签页。", parent=self)
        except Exception as e:
            self.pull_status.set(str(e))
            messagebox.showerror("加载失败", str(e), parent=self)
