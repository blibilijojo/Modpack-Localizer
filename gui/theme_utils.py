import sys
import logging

def set_title_bar_theme(window, style_instance):
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll, byref, c_int, sizeof
        
        window.update_idletasks()
        
        HWND = int(window.wm_frame(), 16)

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        is_dark_theme = style_instance.theme_use() == "darkly"
        value = c_int(1 if is_dark_theme else 0)
        windll.dwmapi.DwmSetWindowAttribute(HWND, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(value), sizeof(value))
        
        SW_HIDE = 0
        SW_SHOW = 5
        windll.user32.ShowWindow(HWND, SW_HIDE)
        windll.user32.ShowWindow(HWND, SW_SHOW)

    except Exception as e:
        logging.warning(f"无法设置Windows深色标题栏: {e}")