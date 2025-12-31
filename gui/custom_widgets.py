import tkinter as tk
import ttkbootstrap as ttk

class ToolTip:
    def __init__(self, widget, text, width=350):
        self.widget = widget
        self.text = text
        self.width = width
        self.tooltip = None
        self.hovering = False  # 状态变量：是否正在悬停
        self.widget.bind("<Enter>", self._on_enter_widget)
        self.widget.bind("<Leave>", self._on_leave_widget)

    def _on_enter_widget(self, event=None):
        """当鼠标进入控件时"""
        self.hovering = True
        self.show_tip()

    def _on_leave_widget(self, event=None):
        """当鼠标离开控件时"""
        # 立即设置hovering为False，因为鼠标已经离开控件
        self.hovering = False
        # 如果tooltip存在，检查鼠标是否进入了tooltip
        if self.tooltip:
            # 延迟检查鼠标是否进入了tooltip
            self.widget.after(100, self._check_hover_status)

    def _on_enter_tooltip(self, event=None):
        """当鼠标进入tooltip时"""
        self.hovering = True

    def _on_leave_tooltip(self, event=None):
        """当鼠标离开tooltip时"""
        self.hovering = False
        self.hide_tip()

    def _check_hover_status(self):
        """检查鼠标悬停状态，决定是否隐藏tooltip"""
        # 如果tooltip仍然存在且hovering为False，说明鼠标已经离开控件和tooltip
        if self.tooltip and not self.hovering:
            self.hide_tip()

    def show_tip(self, event=None):
        if self.tooltip: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        style = ttk.Style.get_instance()
        bg_color = style.colors.get("light")
        fg_color = style.colors.get("fg")

        label = ttk.Label(self.tooltip, text=self.text, justify='left',
                          background=bg_color, foreground=fg_color,
                          relief='solid', borderwidth=1,
                          wraplength=self.width, font=("Microsoft YaHei UI", 9, "normal"),
                          padding=(5, 5, 5, 5))
        label.pack(ipadx=1)
        # 添加tooltip的鼠标事件绑定
        self.tooltip.bind("<Enter>", self._on_enter_tooltip)
        self.tooltip.bind("<Leave>", self._on_leave_tooltip)

    def hide_tip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
        self.hovering = False

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, bootstyle="round")
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        
        frame_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(frame_id, width=e.width))
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.bind_mousewheel_to_children(self)
        self.canvas.bind("<MouseWheel>", _on_mousewheel)

    def _on_frame_configure(self, event=None):
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def bind_mousewheel_to_children(self, widget):
        def _on_mousewheel(event):
             self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        widget.bind("<MouseWheel>", _on_mousewheel)
        for child in widget.winfo_children():
            self.bind_mousewheel_to_children(child)