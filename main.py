import ttkbootstrap as ttk
from gui.main_window import MainWindow
from utils import config_manager

def main():
    """
    应用程序主入口点。
    """
    # 固定使用亮色主题，不再支持主题切换
    theme_name = "litera"
    
    root = ttk.Window(themename=theme_name)
    app = MainWindow(root)
    
    root.mainloop()

if __name__ == "__main__":
    main()
