import tkinter as tk
import ttkbootstrap as ttk
class ToolTip:
    """一个通用的、可自定义的工具提示类"""
    def __init__(self, widget, text, width=350):
        self.widget = widget
        self.text = text
        self.width = width
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)
    def show_tip(self, event=None):
        if self.tooltip: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip, text=self.text, justify='left',
                          background="#ffffe0", relief='solid', borderwidth=1,
                          wraplength=self.width, font=("Microsoft YaHei UI", 9, "normal"),
                          padding=(5, 5, 5, 5))
        label.pack(ipadx=1)
        self.tooltip.bind("<Leave>", self.hide_tip)
    def hide_tip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
        self.tooltip = None
class ScrollableFrame(ttk.Frame):
    """一个可滚动的框架，用于容纳大量控件"""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview, bootstyle="round")
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        frame_id = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(frame_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_mousewheel(canvas)
        self.bind_mousewheel(self.scrollable_frame)
    def bind_mousewheel(self, widget):
        widget.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
    def _on_mousewheel(self, event):
        x, y = self.winfo_pointerxy()
        widget_under_mouse = self.winfo_containing(x, y)
        if widget_under_mouse and widget_under_mouse.winfo_toplevel() == self.winfo_toplevel():
            canvas = self.winfo_children()[0]
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")