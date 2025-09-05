# Modpack_Localizer/gui/ui_utils.py
from tkinter import filedialog, messagebox

def browse_directory(entry_var):
    path = filedialog.askdirectory()
    if path: entry_var.set(path)

def browse_file(entry_var, filetypes):
    path = filedialog.askopenfilename(filetypes=filetypes)
    if path: entry_var.set(path)

def show_error(title, message): messagebox.showerror(title, message)
def show_info(title, message): messagebox.showinfo(title, message)
def show_warning(title, message) -> bool: return messagebox.askyesno(title, message)