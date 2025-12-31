import tkinter as tk
from tkinter import messagebox, scrolledtext
from tkinter import ttk as tk_ttk
import ttkbootstrap as ttk
from utils import config_manager
from gui.custom_widgets import ToolTip
from gui.theme_utils import set_title_bar_theme

class UserDictionaryEditor(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self._setup_window()
        self.user_dict = config_manager.load_user_dict()
        self.is_dirty = False
        self.current_selection_id = None
        self._create_widgets()
        self._populate_tree()
        self._update_editor_state(enabled=False)
        self._update_window_title()

    def _setup_window(self):
        self.title("个人词典编辑器")
        self.geometry("900x600")
        self.minsize(700, 500)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        set_title_bar_theme(self, self.parent.style)

    def _create_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)
        left_frame = ttk.Frame(main_pane)
        tree_frame = tk_ttk.LabelFrame(left_frame, text="词典条目")
        tree_frame.pack(fill="both", expand=True, pady=(0, 5))
        self.tree = ttk.Treeview(tree_frame, columns=("type", "key_origin", "translation"), show="headings")
        self.tree.heading("type", text="类型", anchor="w")
        self.tree.heading("key_origin", text="原文 / Key", anchor="w")
        self.tree.heading("translation", text="译文", anchor="w")
        self.tree.column("type", width=80, stretch=False)
        self.tree.column("key_origin", width=250, stretch=True)
        self.tree.column("translation", width=250, stretch=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        action_frame = ttk.Frame(left_frame)
        action_frame.pack(fill="x")
        ttk.Button(action_frame, text="新建条目", command=self._prepare_new_entry, bootstyle="success").pack(side="left")
        self.delete_btn = ttk.Button(action_frame, text="删除条目", command=self._delete_entry, bootstyle="danger-outline", state="disabled")
        self.delete_btn.pack(side="left", padx=5)
        main_pane.add(left_frame, weight=2)
        editor_frame = tk_ttk.LabelFrame(main_pane, text="编辑区域", padding=10)
        editor_frame.columnconfigure(1, weight=1)
        ttk.Label(editor_frame, text="类型:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(editor_frame, textvariable=self.type_var, values=["按Key", "按原文"], state="readonly")
        self.type_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(editor_frame, text="原文/Key:", anchor="nw").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.key_origin_text = scrolledtext.ScrolledText(editor_frame, height=5, wrap=tk.WORD)
        self.key_origin_text.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        ttk.Label(editor_frame, text="译文:", anchor="nw").grid(row=2, column=0, sticky="nw", padx=5, pady=5)
        self.trans_text = scrolledtext.ScrolledText(editor_frame, height=5, wrap=tk.WORD)
        self.trans_text.grid(row=2, column=1, sticky="nsew", padx=5, pady=5)
        editor_frame.rowconfigure(1, weight=1)
        editor_frame.rowconfigure(2, weight=1)
        self.save_entry_btn = ttk.Button(editor_frame, text="保存更改", command=self._save_entry)
        self.save_entry_btn.grid(row=3, column=1, sticky="e", padx=5, pady=10)
        main_pane.add(editor_frame, weight=3)
        bottom_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom_frame.pack(fill="x", side="bottom")
        ttk.Button(bottom_frame, text="取消", command=self._on_close_request, bootstyle="secondary").pack(side="right")
        ttk.Button(bottom_frame, text="保存并关闭", command=self._on_save_and_close, bootstyle="primary").pack(side="right", padx=10)

    def _populate_tree(self):
        self.tree.unbind("<<TreeviewSelect>>")
        self.tree.delete(*self.tree.get_children())
        for key, trans in self.user_dict.get('by_key', {}).items():
            iid = f"key___{key}"
            self.tree.insert("", "end", iid=iid, values=("按Key", key, trans))
        for origin, trans in self.user_dict.get('by_origin_name', {}).items():
            iid = f"origin___{origin}"
            self.tree.insert("", "end", iid=iid, values=("按原文", origin, trans))
        self.tree.bind("<<TreeviewSelect>>", self._on_item_selected)

    def _on_item_selected(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        self.current_selection_id = selection[0]
        item_type_str, key_origin = self.current_selection_id.split("___", 1)
        item_type = "按Key" if item_type_str == "key" else "按原文"
        dict_key = 'by_key' if item_type_str == "key" else 'by_origin_name'
        translation = self.user_dict[dict_key].get(key_origin, "")
        self._update_editor_state(enabled=True)
        self.type_var.set(item_type)
        self.type_combo.config(state="disabled")
        self.key_origin_text.delete("1.0", tk.END)
        self.key_origin_text.insert("1.0", key_origin)
        self.trans_text.delete("1.0", tk.END)
        self.trans_text.insert("1.0", translation)

    def _prepare_new_entry(self):
        self.tree.selection_set()
        self.current_selection_id = None
        self._update_editor_state(enabled=True, is_new=True)
        self.key_origin_text.delete("1.0", tk.END)
        self.trans_text.delete("1.0", tk.END)
        self.type_var.set("按原文")
        self.key_origin_text.focus_set()

    def _save_entry(self):
        key_origin = self.key_origin_text.get("1.0", "end-1c").strip()
        translation = self.trans_text.get("1.0", "end-1c").strip()
        item_type = self.type_var.get()
        if not key_origin or not translation:
            messagebox.showerror("输入错误", "原文/Key 和译文均不能为空！", parent=self)
            return
        if self.current_selection_id:
            old_type_str, old_key_origin = self.current_selection_id.split("___", 1)
            old_dict_key = 'by_key' if old_type_str == 'key' else 'by_origin_name'
            if old_key_origin in self.user_dict[old_dict_key]:
                del self.user_dict[old_dict_key][old_key_origin]
        dict_key = 'by_key' if item_type == "按Key" else 'by_origin_name'
        self.user_dict[dict_key][key_origin] = translation
        self._set_dirty(True)
        self._populate_tree()
        new_iid = f"{'key' if item_type == '按Key' else 'origin'}___{key_origin}"
        if self.tree.exists(new_iid):
            self.tree.selection_set(new_iid)
            self.tree.focus(new_iid)
            self.tree.see(new_iid)
        messagebox.showinfo("成功", "条目已保存！", parent=self)

    def _delete_entry(self):
        if not self.current_selection_id:
            return
        item_type_str, key_origin = self.current_selection_id.split("___", 1)
        dict_key = 'by_key' if item_type_str == 'key' else 'by_origin_name'
        if messagebox.askyesno("确认删除", f"确定要删除此条目吗？\n\n原文/Key: {key_origin[:100]}", parent=self):
            if key_origin in self.user_dict[dict_key]:
                del self.user_dict[dict_key][key_origin]
                self._set_dirty(True)
                self._populate_tree()
                self._update_editor_state(enabled=False)
                self.current_selection_id = None

    def _on_save_and_close(self):
        config_manager.save_user_dict(self.user_dict)
        self.is_dirty = False
        self.destroy()

    def _on_close_request(self):
        if self.is_dirty:
            response = messagebox.askyesnocancel("未保存的更改", "您有未保存的更改，是否要保存？", parent=self)
            if response is True:
                self._on_save_and_close()
            elif response is False:
                self.destroy()
        else:
            self.destroy()

    def _update_editor_state(self, enabled: bool, is_new: bool = False):
        state = "normal" if enabled else "disabled"
        self.key_origin_text.config(state=state)
        self.trans_text.config(state=state)
        self.save_entry_btn.config(state=state)
        self.delete_btn.config(state="disabled" if is_new else state)
        if is_new:
            self.type_combo.config(state="readonly")
        elif enabled:
            self.type_combo.config(state="disabled")
        else:
            self.type_combo.config(state="disabled")
            self.type_var.set("")
            self.key_origin_text.delete("1.0", tk.END)
            self.trans_text.delete("1.0", tk.END)

    def _set_dirty(self, dirty_status: bool):
        if self.is_dirty != dirty_status:
            self.is_dirty = dirty_status
            self._update_window_title()

    def _update_window_title(self):
        title = "个人词典编辑器"
        if self.is_dirty:
            title += " *"
        self.title(title)