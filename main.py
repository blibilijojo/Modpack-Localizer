import ttkbootstrap as ttk
from gui.main_window import MainWindow
def main():
    """
    应用程序主入口点。
    """
    root = ttk.Window(themename="litera")
    app = MainWindow(root)
    root.mainloop()
if __name__ == "__main__":
    main()
