import tkinter as tk
import ttkbootstrap as ttk
from gui import ui_utils
from utils import config_manager
from gui.theme_utils import set_title_bar_theme

class NewProjectDialog(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("选择项目类型")
        self.geometry("300x150")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        set_title_bar_theme(self, parent.style)
        
        self.result = None
        self.project_type = tk.StringVar(value="mod")

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="您想开始哪种类型的汉化项目？").pack(anchor="w", pady=(0, 10))

        ttk.Radiobutton(main_frame, text="模组汉化 (推荐)", variable=self.project_type, value="mod").pack(anchor="w")
        ttk.Radiobutton(main_frame, text="任务汉化", variable=self.project_type, value="quest").pack(anchor="w")

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(btn_frame, text="确定", command=self._on_ok, bootstyle="success").pack(side="right")
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, bootstyle="secondary").pack(side="right", padx=10)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _on_ok(self):
        self.result = self.project_type.get()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

class ModProjectSetupDialog(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("配置模组汉化项目")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        set_title_bar_theme(self, parent.style)

        self.result = None
        config = config_manager.load_config()
        self.mods_dir_var = tk.StringVar(value=config.get("mods_dir", ""))
        self.output_dir_var = tk.StringVar(value=config.get("output_dir", ""))

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="Mods 文件夹:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(main_frame, textvariable=self.mods_dir_var, width=50).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(main_frame, text="浏览...", command=lambda: ui_utils.browse_directory(self.mods_dir_var)).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(main_frame, text="输出文件夹:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir_var, width=50).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(main_frame, text="浏览...", command=lambda: ui_utils.browse_directory(self.output_dir_var)).grid(row=1, column=2, padx=5, pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="e", pady=(15, 0))
        ttk.Button(btn_frame, text="开始", command=self._on_ok, bootstyle="success").pack()
        
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _on_ok(self):
        mods_dir = self.mods_dir_var.get()
        output_dir = self.output_dir_var.get()
        if not mods_dir or not output_dir:
            ui_utils.show_error("路径不能为空", "请同时指定 Mods 文件夹和输出文件夹。", parent=self)
            return
        
        self.result = {"mods_dir": mods_dir, "output_dir": output_dir}
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

class QuestProjectSetupDialog(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("配置任务汉化项目")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        set_title_bar_theme(self, parent.style)

        self.result = None
        self.instance_dir_var = tk.StringVar()
        self.modpack_name_var = tk.StringVar(value="MyModpack")

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="Minecraft 实例文件夹:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(main_frame, textvariable=self.instance_dir_var, width=50).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(main_frame, text="浏览...", command=lambda: ui_utils.browse_directory(self.instance_dir_var)).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(main_frame, text="整合包名称 (英文):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(main_frame, textvariable=self.modpack_name_var, width=50).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="e", pady=(15, 0))
        ttk.Button(btn_frame, text="开始", command=self._on_ok, bootstyle="success").pack()
        
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _on_ok(self):
        instance_dir = self.instance_dir_var.get()
        modpack_name = self.modpack_name_var.get()
        if not instance_dir or not modpack_name.strip():
            ui_utils.show_error("输入不能为空", "请同时指定实例文件夹和整合包名称。", parent=self)
            return
        
        self.result = {"instance_dir": instance_dir, "modpack_name": modpack_name}
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

class PackPresetDialog(ttk.Toplevel):
    def __init__(self, parent, presets):
        super().__init__(parent)
        self.title("选择生成预案")
        self.resizable(False, False); self.transient(parent); self.grab_set()
        set_title_bar_theme(self, parent.style)
        
        self.result = None
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="请选择一个预案来生成资源包:").pack(anchor="w")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(main_frame, textvariable=self.preset_var, state="readonly", values=list(presets.keys()))
        if presets: self.preset_var.set(list(presets.keys())[0])
        self.preset_combo.pack(fill="x", expand=True, pady=10)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(btn_frame, text="确认生成", command=self._on_ok, bootstyle="success").pack(side="right")
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, bootstyle="secondary").pack(side="right", padx=10)
        
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _on_ok(self):
        self.result = self.preset_var.get()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

class DownloadProgressDialog(ttk.Toplevel):
    def __init__(self, parent, title="下载中"):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        if hasattr(parent, 'style'):
            set_title_bar_theme(self, parent.style)
        elif hasattr(parent, 'master') and hasattr(parent.master, 'style'):
             set_title_bar_theme(self, parent.master.style)

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        self.status_label = ttk.Label(main_frame, text="正在连接...")
        self.status_label.pack(fill="x", pady=5)
        
        self.progress_bar = ttk.Progressbar(main_frame, length=300, mode='determinate')
        self.progress_bar.pack(fill="x", pady=5)
        
        self.protocol("WM_DELETE_WINDOW", lambda: None) 

    def update_progress(self, status: str, percentage: float, speed: str):
        def _update():
            self.status_label.config(text=f"{status}... {int(percentage)}% ({speed})")
            self.progress_bar['value'] = percentage
        self.after(0, _update)

    def close_dialog(self):
        self.after(100, self.destroy)