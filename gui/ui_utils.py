from tkinter import filedialog, messagebox, Toplevel, Text, Scrollbar, Button, Label
from tkinter import ttk as tk_ttk
from utils.error_logger import ErrorLogger
from pathlib import Path

def browse_directory(entry_var, parent=None):
    path = filedialog.askdirectory(parent=parent)
    if path: entry_var.set(path)

def browse_file(entry_var, filetypes, parent=None):
    path = filedialog.askopenfilename(filetypes=filetypes, parent=parent)
    if path: entry_var.set(path)

def show_error(title, message, exception=None, parent=None):
    """
    显示错误信息对话框
    Args:
        title: 对话框标题
        message: 错误信息
        exception: 异常对象（可选）
        parent: 父窗口（可选）
    """
    # 记录错误日志
    if exception:
        from utils.error_logger import ErrorLogger
        ErrorLogger.log_general_error(
            error_title=title,
            error_message=message,
            exception=exception,
            error_level="ERROR"
        )
    
    # 显示基本错误信息
    messagebox.showerror(title, message, parent=parent)

def show_info(title, message, parent=None):
    """
    显示信息对话框
    Args:
        title: 对话框标题
        message: 信息内容
        parent: 父窗口（可选）
    """
    messagebox.showinfo(title, message, parent=parent)

def show_warning(title, message, parent=None) -> bool:
    """
    显示警告对话框
    Args:
        title: 对话框标题
        message: 警告信息
        parent: 父窗口（可选）
    Returns:
        用户的选择（是/否）
    """
    return messagebox.askyesno(title, message, parent=parent)

def show_question(title, message, parent=None) -> bool:
    """
    显示询问对话框
    Args:
        title: 对话框标题
        message: 询问内容
        parent: 父窗口（可选）
    Returns:
        用户的选择（是/否）
    """
    return messagebox.askyesno(title, message, parent=parent)

def show_ok_cancel(title, message, parent=None) -> bool:
    """
    显示确定/取消对话框
    Args:
        title: 对话框标题
        message: 提示内容
        parent: 父窗口（可选）
    Returns:
        用户的选择（确定/取消）
    """
    return messagebox.askokcancel(title, message, parent=parent)

def show_error_details(title, message, exception=None, parent=None):
    """
    显示带有详细信息的错误对话框
    Args:
        title: 对话框标题
        message: 错误信息
        exception: 异常对象（可选）
        parent: 父窗口（可选）
    """
    # 记录错误日志
    if exception:
        from utils.error_logger import ErrorLogger
        ErrorLogger.log_general_error(
            error_title=title,
            error_message=message,
            exception=exception,
            error_level="ERROR"
        )
    
    # 创建自定义对话框
    dialog = Toplevel(parent)
    dialog.title(title)
    dialog.geometry("500x300")
    dialog.resizable(True, True)
    dialog.transient(parent)
    dialog.grab_set()
    
    # 配置对话框样式
    style = tk_ttk.Style()
    
    # 主框架
    main_frame = tk_ttk.Frame(dialog, padding=10)
    main_frame.pack(fill="both", expand=True)
    
    # 基本错误信息
    basic_msg_label = tk_ttk.Label(main_frame, text=message, wraplength=480, justify="left")
    basic_msg_label.pack(pady=(0, 10), anchor="w")
    
    # 详细信息区域
    details_frame = tk_ttk.LabelFrame(main_frame, text="详细信息", padding=10)
    details_frame.pack(fill="both", expand=True, pady=(0, 10))
    
    # 文本框和滚动条
    text_scroll = Scrollbar(details_frame, orient="vertical")
    text_widget = Text(details_frame, wrap="word", height=10, yscrollcommand=text_scroll.set)
    text_scroll.config(command=text_widget.yview)
    
    text_scroll.pack(side="right", fill="y")
    text_widget.pack(side="left", fill="both", expand=True)
    
    # 填充详细信息
    if exception:
        import traceback
        details_text = f"异常类型: {type(exception).__name__}\n"
        details_text += f"异常信息: {str(exception)}\n\n"
        details_text += "堆栈跟踪:\n"
        details_text += traceback.format_exc()
        text_widget.insert("1.0", details_text)
    else:
        text_widget.insert("1.0", "无可用的详细信息")
    
    text_widget.config(state="disabled")
    
    # 按钮框架
    button_frame = tk_ttk.Frame(main_frame)
    button_frame.pack(fill="x", anchor="e")
    
    # 查看日志按钮
    def view_logs():
        import webbrowser
        log_dir = Path("error_logs")
        if log_dir.exists():
            webbrowser.open(str(log_dir))
        else:
            show_info("日志文件夹不存在", "错误日志文件夹尚未创建")
    
    view_logs_btn = tk_ttk.Button(button_frame, text="查看日志", command=view_logs)
    view_logs_btn.pack(side="right", padx=(0, 5))
    
    # 关闭按钮
    close_btn = tk_ttk.Button(button_frame, text="关闭", command=dialog.destroy, style="primary.TButton")
    close_btn.pack(side="right")
    
    # 居中显示
    if parent:
        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    dialog.wait_window()

def show_progress_dialog(title, message, max_value=100, parent=None):
    """
    显示进度对话框
    Args:
        title: 对话框标题
        message: 进度信息
        max_value: 进度最大值（默认为100）
        parent: 父窗口（可选）
    Returns:
        进度更新函数和取消回调函数
    """
    dialog = Toplevel(parent)
    dialog.title(title)
    dialog.geometry("400x120")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()
    
    # 主框架
    main_frame = tk_ttk.Frame(dialog, padding=10)
    main_frame.pack(fill="both", expand=True)
    
    # 进度信息
    msg_label = tk_ttk.Label(main_frame, text=message)
    msg_label.pack(pady=(0, 10))
    
    # 进度条
    progress_var = tk_ttk.DoubleVar()
    progress_bar = tk_ttk.Progressbar(main_frame, variable=progress_var, maximum=max_value)
    progress_bar.pack(fill="x", pady=(0, 10))
    
    # 进度百分比
    percent_label = tk_ttk.Label(main_frame, text="0%")
    percent_label.pack()
    
    # 取消标志
    cancelled = [False]
    
    # 取消按钮
    def cancel(): cancelled[0] = True
    cancel_btn = tk_ttk.Button(main_frame, text="取消", command=cancel)
    cancel_btn.pack(pady=(10, 0))
    
    # 居中显示
    if parent:
        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    # 进度更新函数
    def update_progress(value):
        progress_var.set(value)
        percent = int((value / max_value) * 100)
        percent_label.config(text=f"{percent}%")
        dialog.update_idletasks()
        return cancelled[0]
    
    return update_progress, dialog

def show_success(title, message, parent=None):
    """
    显示成功提示
    Args:
        title: 对话框标题
        message: 成功信息
        parent: 父窗口（可选）
    """
    messagebox.showinfo(title, message, parent=parent)

def show_confirmation(title, message, parent=None) -> bool:
    """
    显示确认对话框
    Args:
        title: 对话框标题
        message: 确认信息
        parent: 父窗口（可选）
    Returns:
        用户的选择（是/否）
    """
    return messagebox.askyesno(title, message, parent=parent)