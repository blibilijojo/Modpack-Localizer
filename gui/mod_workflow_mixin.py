from __future__ import annotations
import threading
import logging
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from utils import config_manager
from core.orchestrator import Orchestrator
from gui import ui_utils


class ModWorkflowMixin:
    """ProjectTab 的 Mod 翻译工作流方法 Mixin。"""

    def _on_workbench_finish(self, final_translations, final_workbench_data):
        self.main_window.update_menu_state()
        from gui.project_type_config import get_project_type_config
        type_config = get_project_type_config(self.project_type)

        if self.project_type == "quest":
             self.log_message(type_config.finish_log_message, "SUCCESS")
             final_lang_dict = {}
             for item in final_workbench_data.get('quest_files', {}).get('items', []):
                 if item.get('zh', '').strip():
                     final_lang_dict[item['key']] = item['zh']
                 else:
                     final_lang_dict[item['key']] = item['en']
             self._run_quest_build_phase(final_lang_dict)
             self._show_welcome_view()
        elif self.project_type == "palladium":
            self.log_message(type_config.finish_log_message, "SUCCESS")
            translation_map = {}
            for item in final_workbench_data.get('palladium', {}).get('items', []):
                if item.get('zh', '').strip():
                    translation_map[item['key']] = item['zh']
            if translation_map:
                self.log_message(f"正在将 {len(translation_map)} 条翻译写入 JAR...", "INFO")
                wb = getattr(self, 'workbench_instance', None)
                if wb and hasattr(wb, 'status_label'):
                    try:
                        wb.status_label.config(text=f"正在将 {len(translation_map)} 条翻译写入 JAR，请稍候...")
                    except Exception:
                        pass
                try:
                    self._run_palladium_build_phase(translation_map)
                except Exception as e:
                    logging.error(f"启动 Palladium 写入失败: {e}", exc_info=True)
                    self.log_message(f"启动写入失败: {e}", "CRITICAL")
                    self.root.after(0, lambda: messagebox.showerror("启动失败", f"启动写入失败: {e}"))
            else:
                self.log_message("没有翻译内容，跳过写入。", "WARNING")
                self.root.after(0, lambda: messagebox.showinfo("提示", "没有翻译内容，跳过写入。"))
        elif self.project_type == "decompile":
            self.log_message(type_config.finish_log_message, "SUCCESS")
            wb = getattr(self, 'workbench_instance', None)
            if wb and hasattr(wb, 'status_label'):
                try:
                    wb.status_label.config(text="正在将翻译写入 JAR，请稍候...")
                except Exception:
                    pass
            try:
                self._run_decompile_build_phase(final_workbench_data)
            except Exception as e:
                logging.error(f"启动 JAR 写入失败: {e}", exc_info=True)
                self.log_message(f"启动 JAR 写入失败: {e}", "CRITICAL")
                self.root.after(0, lambda: messagebox.showerror("启动失败", f"启动 JAR 写入失败: {e}"))
        elif self.project_type == "shader":
            self.log_message(type_config.finish_log_message, "SUCCESS")
            wb = getattr(self, 'workbench_instance', None)
            if wb and hasattr(wb, 'status_label'):
                try:
                    wb.status_label.config(text="正在生成汉化文件，请稍候...")
                except Exception:
                    pass
            try:
                self._run_shader_build_phase(final_workbench_data)
            except Exception as e:
                logging.error(f"启动光影汉化写入失败: {e}", exc_info=True)
                self.log_message(f"启动写入失败: {e}", "CRITICAL")
                self.root.after(0, lambda: messagebox.showerror("启动失败", f"启动写入失败: {e}"))
        elif self.project_type == "datapack":
            self.log_message(type_config.finish_log_message, "SUCCESS")
            wb = getattr(self, 'workbench_instance', None)
            if wb and hasattr(wb, 'status_label'):
                try:
                    wb.status_label.config(text="正在写入翻译到数据包文件，请稍候...")
                except Exception:
                    pass
            try:
                self._run_datapack_build_phase(final_workbench_data)
            except Exception as e:
                logging.error(f"启动数据包翻译写入失败: {e}", exc_info=True)
                self.log_message(f"启动写入失败: {e}", "CRITICAL")
                self.root.after(0, lambda: messagebox.showerror("启动失败", f"启动写入失败: {e}"))
        elif self.project_type == "javamap":
            self.log_message(type_config.finish_log_message, "SUCCESS")
            wb = getattr(self, 'workbench_instance', None)
            if wb and hasattr(wb, 'status_label'):
                try:
                    wb.status_label.config(text="正在写入翻译到地图文件，请稍候...")
                except Exception:
                    pass
            try:
                self._run_javamap_build_phase(final_workbench_data)
            except Exception as e:
                logging.error(f"启动地图翻译写入失败: {e}", exc_info=True)
                self.log_message(f"启动写入失败: {e}", "CRITICAL")
                self.root.after(0, lambda: messagebox.showerror("启动失败", f"启动写入失败: {e}"))
        else:
            self.orchestrator.final_translations = final_translations
            self.orchestrator.final_workbench_data = final_workbench_data
            self.log_message(type_config.finish_log_message, "SUCCESS")
            if type_config.finish_progress_message:
                self.update_progress(type_config.finish_progress_message, -10)

    def _on_workbench_cancel(self):
        self.main_window.update_menu_state()
        self.log_message("翻译工作台已取消，操作中止。", "WARNING")
        self.update_progress("操作已取消", -2)
        self._show_welcome_view()

    def start_localization_process(self, file_path, file_info=None):
        """开始汉化流程"""
        self.status_var.set("准备汉化流程...")
        
        # 构建项目名称
        project_name = f"汉化 - {file_path.stem}"
        if file_info:
            version = file_info.get('version_number', '')
            if version:
                project_name = f"汉化 - {file_path.stem} (v{version})"
        
        self.log_message(f"开始汉化流程: {project_name}")
        
        # 创建临时mods目录
        import tempfile
        from pathlib import Path
        
        temp_mods_dir = tempfile.mkdtemp()
        
        # 将下载的文件复制到临时mods目录
        import shutil
        mod_file_path = Path(temp_mods_dir) / file_path.name
        shutil.copy2(file_path, mod_file_path)
        
        # 更新项目信息
        self.project_type = "mod"
        self.project_name = project_name
        self.project_info = {
            "mods_dir": temp_mods_dir,
            "output_dir": self.project_info.get('output_dir')
        }
        
        # 更新标签页标题
        self.main_window.update_tab_title(self.tab_id, self.project_name)
        
        # 先保存配置（不包含临时目录），然后再设置运行时需要的 mods_dir
        from utils import config_manager
        config = config_manager.load_config()
        config['output_dir'] = self.project_info.get('output_dir')
        config_manager.save_config(config)  # 保存时不包含 temp_mods_dir
        config['mods_dir'] = temp_mods_dir  # 仅在运行时使用，不保存
        
        # 开始汉化流程
        self._prepare_ui_for_workflow(1)
        from core.orchestrator import Orchestrator
        self.orchestrator = Orchestrator(
            settings=config,
            update_progress=self.update_progress,
            log_callback=self.log_message,
            show_error_callback=lambda title, msg: self.root.after(0, lambda: messagebox.showerror(title, msg)),
            launch_workbench_callback=lambda data: self._show_workbench_view(
                data, 
                self.orchestrator.namespace_formats, 
                self.orchestrator.raw_english_files, 
                config, 
                None, 
                "完成并生成资源包",
                save_session_after=True
            )
        )
        # 传递停止事件
        self.orchestrator.stop_event = self.stop_event
        
        # 启动翻译流程
        thread = threading.Thread(target=self.orchestrator.run_translation_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _load_project(self):
        path = filedialog.askopenfilename(
            title="选择一个项目存档文件",
            filetypes=[("项目存档", "*.sav"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path: return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            required_keys = ['workbench_data', 'namespace_formats', 'raw_english_files']
            if not all(k in save_data for k in required_keys):
                raise ValueError("存档文件格式不正确或已损坏。")

            self.project_type = "mod"
            self.project_name = Path(path).stem
            self.log_message(f"成功加载项目: {Path(path).name}", "SUCCESS")
            self.log_message("所有个人设置将保持不变，使用您本地的配置。", "INFO")
            self.main_window.update_tab_title(self.tab_id, self.project_name)

            self._prepare_ui_for_workflow(1)
            settings = config_manager.load_config()
            self.orchestrator = Orchestrator(
                settings, self.update_progress,
                log_callback=self.log_message,
                show_error_callback=lambda title, msg: self.root.after(0, lambda: messagebox.showerror(title, msg)),
                launch_workbench_callback=lambda data: self._show_workbench_view(data, self.orchestrator.namespace_formats, self.orchestrator.raw_english_files, settings, path, "完成并生成资源包", save_session_after=True),
                save_data=save_data, project_path=path
            )
            # 传递停止事件
            self.orchestrator.stop_event = self.stop_event
            
            thread = threading.Thread(target=self.orchestrator.run_workflow, daemon=True)
            self.add_background_thread(thread)
            thread.start()

        except Exception as e:
            ui_utils.show_error("加载失败", f"无法加载或解析项目文件：\n{e}", parent=self.root)
            logging.error(f"加载项目文件 '{path}' 失败: {e}", exc_info=True)

    def load_from_save_data(self, save_data: dict, project_name: str):
        """从局域网接收的存档数据加载项目到工作台。"""
        try:
            inner = save_data.get("save_data", save_data)
            translation_state = inner.get("translation_state", {})
            mc_version = inner.get("target_minecraft_version", "")

            if not translation_state:
                raise ValueError("存档中没有翻译数据")

            self.project_type = "mod"
            self.project_name = project_name
            self.main_window.update_tab_title(self.tab_id, project_name)

            workbench_data = {}
            namespace_formats = {}
            for ns, entries in translation_state.items():
                items = []
                for key, entry in entries.items():
                    if isinstance(entry, dict):
                        items.append({
                            "key": entry.get("key", key),
                            "en": entry.get("origin", entry.get("en", "")),
                            "zh": entry.get("zh", ""),
                            "source": entry.get("source", "unknown"),
                        })
                workbench_data[ns] = {
                    "display_name": ns,
                    "items": items,
                    "jar_name": entries[list(entries.keys())[0]].get("mod", "") if entries else "",
                    "modrinth_info": None,
                    "curseforge_info": None,
                }
                namespace_formats[ns] = "json"

            settings = config_manager.load_config()
            self._show_workbench_view(
                workbench_data, namespace_formats, {},
                settings, None, "完成并生成资源包", save_session_after=False
            )

            self.log_message(f"已从局域网接收项目: {project_name}", "SUCCESS")
            self.log_message(f"包含 {len(workbench_data)} 个命名空间", "INFO")

        except Exception as e:
            ui_utils.show_error("加载失败", f"无法加载接收到的存档：\n{e}", parent=self.root)
            logging.error(f"加载局域网接收存档失败: {e}", exc_info=True)

    def _prepare_ui_for_workflow(self, stage: int):
        if self.workbench_instance:
            self.workbench_instance.pack_forget()
        else:
            self._clear_content_frame()
    
        if hasattr(self, 'loading_frame') and self.loading_frame and self.loading_frame.winfo_exists():
            self.loading_frame.destroy()
            
        self.loading_frame = ttk.Frame(self.content_frame)
        self.loading_frame.pack(expand=True)
        ttk.Label(self.loading_frame, text="正在处理中，请稍候...", font="-size 14").pack(pady=10)
        self.root.update_idletasks()
        
        # 移除自动展开日志的功能，保留日志清除功能
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        
        if stage == 1: self.status_var.set("准备开始处理翻译...")
        else: self.status_var.set("准备开始生成...")
        self.progress_var.set(0)

    def _reset_ui_after_workflow(self, final_status: str):
        if hasattr(self, 'loading_frame') and self.loading_frame and self.loading_frame.winfo_exists():
            self.loading_frame.destroy()
            self.loading_frame = None
    
        if final_status == "success":
            self.log_message("流程执行完毕！", "SUCCESS")
            self.progress_bar.config(bootstyle="success")
        elif final_status == "cancelled":
            self.log_message("流程已被用户取消", "WARNING")
            self.progress_bar.config(bootstyle="secondary")
        else:
            self.log_message(f"流程因错误中断", "CRITICAL")
            self.progress_bar.config(bootstyle="danger")
    
        if self.workbench_instance:
            self.workbench_instance.pack(fill="both", expand=True)
        else:
            # 不显示欢迎界面，保持空白，等待工作台启动
            # 只有在明确需要显示欢迎界面时才调用_show_welcome_view()
            pass

    def _continue_to_build_phase(self):
        if not self.orchestrator:
            ui_utils.show_error("内部错误", "Orchestrator实例丢失，无法继续生成。", parent=self.root)
            self._reset_ui_after_workflow("error")
            return

        config = config_manager.load_config()
        presets = config.get("pack_settings_presets", {})
        if not presets:
            ui_utils.show_error("操作失败", "没有可用的资源包生成预案。\n请在“配置”菜单中打开设置面板创建一个预案。", parent=self.root)
            self._reset_ui_after_workflow("cancelled")
            return

        dialog = PackPresetDialog(self.root, presets)
        chosen_preset_name = dialog.result

        if chosen_preset_name is None:
            self.log_message("生成操作已取消", "INFO")
            self._reset_ui_after_workflow("cancelled")
            return

        final_pack_settings = presets.get(chosen_preset_name, {}).copy()
        final_pack_settings['preset_name'] = chosen_preset_name
        final_pack_settings['pack_as_zip'] = config.get("pack_as_zip", False)

        self._prepare_ui_for_workflow(stage=2)
        thread = threading.Thread(target=self.orchestrator.run_build_phase, args=(final_pack_settings,), daemon=True)
        self.add_background_thread(thread)
        thread.start()
