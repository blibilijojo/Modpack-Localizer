import tkinter as tk
from tkinter import messagebox, ttk as tk_ttk, filedialog
import ttkbootstrap as ttk
from gui import ui_utils
from gui import custom_widgets
from utils import config_manager
import base64
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

class AdvancedSettings:
    def __init__(self, parent, config, save_callback):
        self.parent = parent
        self.config = config.copy()
        self.save_callback = save_callback
        
        # 创建变量
        self._create_variables()
        
        # 创建UI
        self._create_widgets()
    
    def _create_variables(self):
        # 日志设置
        self.log_level_var = tk.StringVar(value=self.config.get("log_level", "INFO"))
        
        # 绑定变量变化事件
        self._bind_events()
    
    def _bind_events(self):
        # 绑定变量变化事件
        self.log_level_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_widgets(self):
        # 创建主容器
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建日志设置
        self._create_log_settings(main_frame)
        
        # 创建高级设置
        self._create_advanced_settings(main_frame)
    
    def _create_log_settings(self, parent):
        frame = tk_ttk.LabelFrame(parent, text="日志设置", padding="10")
        frame.pack(fill="x", pady=(0, 5), padx=5)
        
        # 日志级别说明 - 动态更新
        self.log_level_desc_var = tk.StringVar(value="选择日志级别以查看详细说明")
        log_level_desc_label = ttk.Label(frame, textvariable=self.log_level_desc_var, wraplength=600, justify="left")
        log_level_desc_label.pack(anchor="w", pady=5)
        
        # 日志级别选择
        log_level_frame = ttk.Frame(frame)
        log_level_frame.pack(fill="x", pady=5)
        log_level_label = ttk.Label(log_level_frame, text="选择日志级别:", width=15)
        log_level_label.pack(side="left")
        custom_widgets.ToolTip(log_level_label, "设置日志记录的详细程度")
        
        # 日志级别选项和对应说明
        self.log_level_options = {
            "DEBUG": "最详细的日志，记录所有程序运行细节（适合开发调试）",
            "INFO": "基本的程序运行信息，如任务开始、完成等（适合普通用户）",
            "WARNING": "警告信息，提示潜在问题但不影响程序运行",
            "ERROR": "错误信息，表示部分功能可能无法正常工作",
            "CRITICAL": "致命错误，程序即将崩溃"
        }
        
        log_level_combobox = ttk.Combobox(log_level_frame, textvariable=self.log_level_var, 
                                         values=list(self.log_level_options.keys()), 
                                         state="readonly")
        log_level_combobox.pack(side="left", fill="x", expand=True, padx=5)
        
        # 清除选中状态的事件处理
        def on_combobox_select(event):
            self.save_callback()
            # 更新动态说明
            selected_level = self.log_level_var.get()
            self.log_level_desc_var.set(self.log_level_options.get(selected_level, "选择日志级别以查看详细说明"))
            # 立即取消文字选中状态，仅在event不为None时执行
            if event is not None:
                event.widget.selection_clear()
                event.widget.icursor(tk.END)
        
        def on_combobox_focus_in(event):
            # 立即取消文字选中状态
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        def on_combobox_focus_out(event):
            # 立即取消文字选中状态
            event.widget.selection_clear()
            event.widget.icursor(tk.END)
        
        # 绑定事件
        log_level_combobox.bind('<<ComboboxSelected>>', on_combobox_select)
        log_level_combobox.bind('<FocusIn>', on_combobox_focus_in)
        log_level_combobox.bind('<FocusOut>', on_combobox_focus_out)
        
        # 初始化动态说明
        on_combobox_select(None)
        
        # 添加日志保留配置
        log_retention_frame = ttk.Frame(frame)
        log_retention_frame.pack(fill="x", pady=5)
        
        # 日志保留天数
        log_retention_days_label = ttk.Label(log_retention_frame, text="日志保留天数:", width=15)
        log_retention_days_label.pack(side="left")
        custom_widgets.ToolTip(log_retention_days_label, "设置日志文件保留的天数，超过该天数的日志将被自动删除")
        self.log_retention_days_var = tk.IntVar(value=self.config.get("log_retention_days", 10))
        log_retention_days_spinbox = ttk.Spinbox(log_retention_frame, from_=1, to=365, textvariable=self.log_retention_days_var, width=10)
        log_retention_days_spinbox.pack(side="left", padx=5)
        
        # 最大日志数量
        max_log_count_label = ttk.Label(log_retention_frame, text="最大日志数量:", width=15)
        max_log_count_label.pack(side="left")
        custom_widgets.ToolTip(max_log_count_label, "设置保留的最大日志文件数量，超过该数量的最旧日志将被自动删除")
        self.max_log_count_var = tk.IntVar(value=self.config.get("max_log_count", 30))
        max_log_count_spinbox = ttk.Spinbox(log_retention_frame, from_=5, to=100, textvariable=self.max_log_count_var, width=10)
        max_log_count_spinbox.pack(side="left", padx=5)
        
        # 绑定变量变化事件
        self.log_retention_days_var.trace_add("write", lambda *args: self.save_callback())
        self.max_log_count_var.trace_add("write", lambda *args: self.save_callback())
    
    def _create_advanced_settings(self, parent):
        # 高级设置框架
        advanced_frame = tk_ttk.LabelFrame(parent, text="高级设置", padding="10")
        advanced_frame.pack(fill="x", pady=(0, 5), padx=5)
        
        # 配置导入导出
        config_io_frame = tk_ttk.LabelFrame(advanced_frame, text="配置导入导出", padding="10")
        config_io_frame.pack(fill="x", pady=(0, 5))
        
        # 导入导出按钮
        io_btn_frame = ttk.Frame(config_io_frame)
        io_btn_frame.pack(fill="x", pady=5)
        
        export_btn = ttk.Button(io_btn_frame, text="导出配置", command=self._export_config, bootstyle="info-outline")
        export_btn.pack(side="left", padx=(0, 10))
        custom_widgets.ToolTip(export_btn, "导出当前配置到文件，支持密钥加密")
        
        import_btn = ttk.Button(io_btn_frame, text="导入配置", command=self._import_config, bootstyle="info-outline")
        import_btn.pack(side="left", padx=(0, 10))
        custom_widgets.ToolTip(import_btn, "从文件导入配置，需要输入正确的密钥")
        
        # 重置设置
        reset_frame = tk_ttk.LabelFrame(advanced_frame, text="重置设置", padding="10")
        reset_frame.pack(fill="x")
        
        reset_btn = ttk.Button(reset_frame, text="重置为默认设置", command=self._reset_settings, bootstyle="danger-outline")
        reset_btn.pack(anchor="w", pady=5)
        custom_widgets.ToolTip(reset_btn, "警告：此操作将清除所有自定义设置，包括API密钥和路径设置。")
    
    def _reset_settings(self):
        """
        将所有设置重置为默认值
        """
        result = messagebox.askyesnocancel(
            "重置设置",
            "警告：此操作将清除所有自定义设置，包括API密钥、路径设置和AI参数等。\n\n是否确定要重置所有设置？",
            icon="warning"
        )
        
        if result:
            try:
                # 加载默认配置
                default_config = config_manager.DEFAULT_CONFIG
                # 保存默认配置
                config_manager.save_config(default_config)
                # 更新当前配置
                self.config = default_config.copy()
                # 刷新UI
                self._refresh_ui_from_config()
                ui_utils.show_info("重置成功", "所有设置已恢复为默认值")
            except Exception as e:
                ui_utils.show_error("重置失败", f"重置设置时发生错误：{str(e)}")
    
    def _derive_key(self, password):
        """从密码派生加密密钥"""
        salt = b'modpack_localizer_salt'  # 固定盐值，确保相同密码生成相同密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def _encrypt_config(self, config_data, password):
        """使用密码加密配置数据"""
        key = self._derive_key(password)
        fernet = Fernet(key)
        json_data = json.dumps(config_data, indent=4, ensure_ascii=False).encode()
        encrypted_data = fernet.encrypt(json_data)
        return encrypted_data
    
    def _decrypt_config(self, encrypted_data, password):
        """使用密码解密配置数据"""
        key = self._derive_key(password)
        fernet = Fernet(key)
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode())
    
    def _export_config(self):
        """导出配置文件"""
        # 获取当前配置
        current_config = config_manager.load_config()
        
        # 询问用户是否需要加密
        use_encryption = messagebox.askyesno(
            "导出配置",
            "是否需要加密配置文件？加密后需要输入密钥才能导入。"
        )
        
        password = None
        if use_encryption:
            # 询问密码
            password = ui_utils.ask_string(
                "设置密钥",
                "请输入配置文件加密密钥（至少6个字符）:",
                show="*",
                parent=self.parent
            )
            
            # 如果用户取消，直接返回
            if password is None:
                return
            
            # 检查密钥长度
            if len(password) < 6:
                messagebox.showerror("错误", "密钥长度不能小于6个字符")
                return
            
            # 确认密码
            confirm_password = ui_utils.ask_string(
                "确认密钥",
                "请再次输入密钥以确认:",
                show="*",
                parent=self.parent
            )
            
            # 如果用户取消，直接返回
            if confirm_password is None:
                return
            
            if password != confirm_password:
                messagebox.showerror("错误", "两次输入的密钥不一致")
                return
        
        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json" if not use_encryption else ".mplcfg",
            filetypes=[
                ("未加密配置文件", "*.json"),
                ("加密配置文件", "*.mplcfg"),
                ("所有文件", "*.*")
            ],
            title="导出配置文件"
        )
        
        if not file_path:
            return
        
        try:
            if use_encryption:
                # 加密配置
                encrypted_data = self._encrypt_config(current_config, password)
                with open(file_path, "wb") as f:
                    f.write(encrypted_data)
                messagebox.showinfo("成功", f"配置已成功加密导出到文件: {file_path}")
            else:
                # 直接保存为JSON
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(current_config, f, indent=4, ensure_ascii=False)
                messagebox.showinfo("成功", f"配置已成功导出到文件: {file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出配置时发生错误: {e}")
    
    def _import_config(self):
        """导入配置文件"""
        # 选择文件
        file_path = filedialog.askopenfilename(
            filetypes=[
                ("配置文件", "*.json *.mplcfg"),
                ("所有文件", "*.*")
            ],
            title="导入配置文件"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取配置文件时发生错误: {e}")
            return
        
        config_data = None
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 判断文件类型
        if file_ext == ".mplcfg":
            # 加密文件，需要密码
            password = ui_utils.ask_string(
                "输入密钥",
                "请输入配置文件加密密钥:",
                show="*",
                parent=self.parent
            )
            
            if not password:
                return
            
            try:
                config_data = self._decrypt_config(file_content, password)
            except Exception as e:
                messagebox.showerror("错误", f"解密配置文件失败: {e}\n请检查密钥是否正确")
                return
        else:
            # 未加密文件，直接解析JSON
            try:
                config_data = json.loads(file_content.decode("utf-8"))
            except Exception as e:
                messagebox.showerror("错误", f"解析配置文件失败: {e}")
                return
        
        # 确认导入
        confirm = messagebox.askyesno(
            "确认导入",
            "导入配置将覆盖当前所有设置，包括API密钥、路径设置等，是否继续？"
        )
        
        if not confirm:
            return
        
        try:
            # 保存导入的配置
            config_manager.save_config(config_data)
            
            # 更新当前配置
            self.config = config_data.copy()
            
            # 刷新UI
            self._refresh_ui_from_config()
            
            # 触发保存回调
            self.save_callback()
            
            messagebox.showinfo("成功", "配置已成功导入")
        except Exception as e:
            messagebox.showerror("错误", f"导入配置时发生错误: {e}")
    
    def _refresh_ui_from_config(self):
        """从配置刷新UI"""
        # 更新日志级别
        self.log_level_var.set(self.config.get("log_level", "INFO"))
        
        # 更新日志保留设置
        self.log_retention_days_var.set(self.config.get("log_retention_days", 10))
        self.max_log_count_var.set(self.config.get("max_log_count", 30))
        
        # 触发保存回调，确保所有组件都更新
        self.save_callback()
    
    def get_config(self):
        return {
            "log_level": self.log_level_var.get(),
            "log_retention_days": self.log_retention_days_var.get(),
            "max_log_count": self.max_log_count_var.get()
        }
