from __future__ import annotations
import threading
import logging
from pathlib import Path
from tkinter import messagebox
from utils import config_manager
from gui import ui_utils


class ProjectTabWorkflowMixin:
    """ProjectTab 的工作流设置方法 Mixin。"""

    def _setup_quest_workflow(self, path_values, config):
        instance_dir = path_values.get("instance_dir", "")
        output_dir = path_values.get("output_dir", "")
        self.project_info = {"instance_dir": instance_dir, "output_dir": output_dir}

        self.quest_manager = QuestWorkflowManager(project_info=self.project_info, main_window=self)

        def launch_quest_workbench(data):
            self._show_workbench_view(data, {}, {}, config_manager.load_config(), None, "完成")
        self.quest_manager._launch_workbench = launch_quest_workbench

        def run_quest_build(trans_dict):
            thread = threading.Thread(target=self.quest_manager._run_build_phase, args=(trans_dict,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_quest_build_phase = run_quest_build

        thread = threading.Thread(target=self.quest_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _setup_palladium_workflow(self, path_values, config):
        from gui.palladium_workflow_manager import PalladiumWorkflowManager
        self.project_info = {"jar_path": path_values.get("jar_path", "")}
        self.palladium_manager = PalladiumWorkflowManager(project_info=self.project_info, main_window=self)

        def run_palladium_build(trans_dict):
            thread = threading.Thread(target=self.palladium_manager.run_build_phase, args=(trans_dict,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_palladium_build_phase = run_palladium_build

        thread = threading.Thread(target=self.palladium_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _launch_palladium_workbench(self, workbench_data):
        self._show_workbench_view(workbench_data, {}, {}, config_manager.load_config(), None, "完成并写入 JAR", save_session_after=True)

    def _setup_decompile_workflow(self, path_values, config):
        from gui.decompile_workflow_manager import DecompileWorkflowManager
        self.project_info = {"jar_path": path_values.get("jar_path", "")}
        self.decompile_manager = DecompileWorkflowManager(project_info=self.project_info, main_window=self)

        def run_decompile_build(final_workbench_data):
            thread = threading.Thread(target=self.decompile_manager.run_build_phase, args=(final_workbench_data,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_decompile_build_phase = run_decompile_build

        thread = threading.Thread(target=self.decompile_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _launch_decompile_workbench(self, workbench_data):
        self._show_workbench_view(workbench_data, {}, {}, config_manager.load_config(), None, "完成并替换 JAR", save_session_after=True)

    def _setup_shader_workflow(self, path_values, config):
        from gui.shader_workflow_manager import ShaderWorkflowManager
        self.project_info = {
            "shader_dir": path_values.get("shader_dir", ""),
            "output_dir": path_values.get("output_dir", ""),
        }
        self.shader_manager = ShaderWorkflowManager(project_info=self.project_info, main_window=self)

        def run_shader_build(final_workbench_data):
            thread = threading.Thread(target=self.shader_manager.run_build_phase, args=(final_workbench_data,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_shader_build_phase = run_shader_build

        thread = threading.Thread(target=self.shader_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _launch_shader_workbench(self, workbench_data):
        self._show_workbench_view(workbench_data, {}, {}, config_manager.load_config(), None, "完成并替换文件", save_session_after=True)

    def _setup_datapack_workflow(self, path_values, config):
        from gui.datapack_workflow_manager import DatapackWorkflowManager
        self.project_info = {
            "datapack_dir": path_values.get("datapack_dir", ""),
        }
        self.datapack_manager = DatapackWorkflowManager(project_info=self.project_info, main_window=self)

        def run_datapack_build(final_workbench_data):
            thread = threading.Thread(target=self.datapack_manager.run_build_phase, args=(final_workbench_data,), daemon=True)
            self.add_background_thread(thread)
            thread.start()
        self._run_datapack_build_phase = run_datapack_build

        thread = threading.Thread(target=self.datapack_manager.run_extraction_phase, daemon=True)
        self.add_background_thread(thread)
        thread.start()

    def _launch_datapack_workbench(self, workbench_data):
        self._show_workbench_view(workbench_data, {}, {}, config_manager.load_config(), None, "完成并替换文件", save_session_after=True)

    def _setup_new_mod_project(self):
        from gui.project_type_config import get_project_type_config
        self._setup_generic_project(get_project_type_config("mod"))

    def _setup_new_quest_project(self):
        from gui.project_type_config import get_project_type_config
        self._setup_generic_project(get_project_type_config("quest"))
