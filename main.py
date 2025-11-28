import ttkbootstrap as ttk
from gui.main_window import MainWindow
from utils import config_manager

def main():
    """
    应用程序主入口点。
    """
    config = config_manager.load_config()
    theme_name = config.get("theme", "litera")
    
    root = ttk.Window(themename=theme_name)
    app = MainWindow(root)
    
    root.mainloop()

if __name__ == "__main__":
    main()
