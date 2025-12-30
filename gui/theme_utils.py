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
        # 移除ShowWindow调用，避免窗口闪烁
        # 只需要设置DwmSetWindowAttribute就足够更新标题栏主题

    except Exception as e:
        logging.warning(f"无法设置Windows深色标题栏: {e}")


def set_menu_bar_theme(window, style_instance):
    """设置菜单栏主题"""
    if sys.platform != "win32":
        return
    
    try:
        # 确保标题栏主题已经设置
        set_title_bar_theme(window, style_instance)
        
        # 尝试使用Windows API来设置菜单的颜色
        from ctypes import windll, byref, c_int, sizeof, c_uint, c_void_p, WINFUNCTYPE
        
        # 定义一些常量
        GCL_HBRBACKGROUND = -10
        COLOR_MENU = 4
        COLOR_MENUTEXT = 7
        COLOR_HIGHLIGHT = 13
        COLOR_HIGHLIGHTTEXT = 14
        
        # 获取当前主题
        current_theme = style_instance.theme_use()
        is_dark = current_theme == "darkly"
        
        if is_dark:
            # 暗黑模式下的颜色
            menu_bg_color = 0x1a1a1a  # 深灰色
            menu_fg_color = 0xffffff  # 白色
            highlight_bg_color = 0x404040  # 高亮时的灰色
            highlight_fg_color = 0xffffff  # 高亮时的白色
        else:
            # 亮色模式下的颜色
            menu_bg_color = 0xf0f0f0  # 浅灰色
            menu_fg_color = 0x000000  # 黑色
            highlight_bg_color = 0xd0d0d0  # 高亮时的灰色
            highlight_fg_color = 0x000000  # 高亮时的黑色
        
        # 设置系统颜色
        # 注意：这会影响所有应用程序，所以我们不应该这样做
        # windll.user32.SetSysColors(1, byref(c_int(COLOR_MENU)), byref(c_uint(menu_bg_color)))
        
        # 另一种方法是使用SetClassLongPtr来设置窗口类的背景颜色
        # 但这可能不会影响菜单栏
        
        # 对于ttkbootstrap的Menu组件，我们需要确保它使用了正确的样式
        # 这里我们主要依赖沉浸式深色模式的设置来影响菜单
        
    except Exception as e:
        logging.warning(f"无法设置Windows菜单栏主题: {e}")