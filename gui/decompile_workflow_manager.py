from __future__ import annotations

import json
import logging
import os
import zipfile
from pathlib import Path
from io import BytesIO

from gui import ui_utils


class DecompileWorkflowManager:
    def __init__(self, project_info: dict, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.jar_path = Path(project_info["jar_path"])

        self._hardcoded_strings: list[dict] = []

    def _log(self, message: str, level: str = "INFO"):
        self.main_window.log_message(message, level)

    def _update_workbench_status(self, message: str, level: str = "info"):
        def _update():
            wb = getattr(self.main_window, "workbench_instance", None)
            if wb and hasattr(wb, "status_label"):
                try:
                    wb.status_label.config(text=message)
                except Exception:
                    pass
        try:
            self.main_window.root.after(0, _update)
        except Exception:
            pass

    def run_extraction_phase(self):
        try:
            if not self.jar_path.is_file():
                raise FileNotFoundError(f"JAR 文件不存在: {self.jar_path}")

            self._log(f"正在扫描 JAR 文件: {self.jar_path.name}", "INFO")

            self._log("正在扫描 .class 常量池提取硬编码字符串...", "INFO")
            self._update_workbench_status("正在扫描 .class 常量池...")
            from core.decompiler import extract_translatable_from_jar
            self._hardcoded_strings = extract_translatable_from_jar(self.jar_path)
            self._log(f"提取到 {len(self._hardcoded_strings)} 条硬编码自然语言文本", "SUCCESS")

            workbench_data = self._build_workbench_data()
            total_items = sum(len(ns.get("items", [])) for ns in workbench_data.values())
            self._log(f"共提取 {total_items} 条可翻译文本，正在打开工作台...", "SUCCESS")

            self._launch_workbench(workbench_data)

        except KeyboardInterrupt:
            self._log("操作已取消", "WARNING")
            self.main_window.root.after(0, self.main_window._show_welcome_view)
        except Exception as e:
            logging.error(f"JAR 提取失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("处理失败", f"提取文本时发生错误:\n{err}"),
            )
            self.main_window.root.after(0, self.main_window._show_welcome_view)

    def _launch_workbench(self, workbench_data: dict):
        self.main_window.root.after(
            0, self.main_window._launch_decompile_workbench, workbench_data
        )

    def _build_workbench_data(self) -> dict:
        from core.decompiler import _is_already_translated

        data: dict[str, dict] = {}

        if not self._hardcoded_strings:
            return data

        file_groups: dict[str, list[dict]] = {}
        for entry in self._hardcoded_strings:
            cls_file = entry["file"]
            if cls_file not in file_groups:
                file_groups[cls_file] = []
            file_groups[cls_file].append(entry)

        for cls_file, entries in file_groups.items():
            items = []
            seen: set[str] = set()
            for entry in entries:
                text = entry["text"]
                if text in seen:
                    continue
                seen.add(text)

                if _is_already_translated(text):
                    items.append({
                        "key": text,
                        "en": "[已翻译]",
                        "zh": text,
                        "source": "常量池",
                    })
                else:
                    items.append({
                        "key": text,
                        "en": text,
                        "zh": "",
                        "source": "常量池",
                    })
            if items:
                short_name = cls_file.rsplit("/", 1)[-1].replace(".class", "")
                data[cls_file] = {
                    "display_name": short_name,
                    "jar_name": self.jar_path.name,
                    "items": items,
                }

        return data

    def run_build_phase(self, final_workbench_data: dict):
        try:
            self._log(f"开始将翻译写入 JAR: {self.jar_path.name}", "INFO")
            self._update_workbench_status("正在处理翻译数据...")

            translations: dict[str, str] = {}
            for ns, ns_data in final_workbench_data.items():
                for item in ns_data.get("items", []):
                    zh = item.get("zh", "").strip()
                    key = item.get("key", "").strip()
                    if not zh or not key:
                        continue
                    translations[key] = zh

            self._log(f"共 {len(translations)} 条翻译待写入", "INFO")

            self._update_workbench_status("正在构建新的 JAR 文件...")
            self._log("正在构建新的 JAR 文件...", "INFO")

            from core.decompiler import patch_class_strings

            temp_path = self.jar_path.with_suffix(".jar.tmp")

            with zipfile.ZipFile(self.jar_path, "r") as zin:
                buf = BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        lower = item.filename.lower()
                        if lower.endswith(".class") and translations:
                            class_data = zin.read(item.filename)
                            modified = patch_class_strings(class_data, translations)
                            zout.writestr(item, modified)
                        else:
                            zout.writestr(item, zin.read(item.filename))

            jar_bytes = buf.getvalue()
            self._log(f"新 JAR 数据大小: {len(jar_bytes)} 字节", "INFO")

            try:
                temp_path.write_bytes(jar_bytes)
                os.replace(str(temp_path), str(self.jar_path))
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

            self._log(f"完成！已将 {len(translations)} 条翻译写入 JAR 文件。", "SUCCESS")
            self._update_workbench_status(
                f"写入完成！{len(translations)} 条翻译已写入 {self.jar_path.name}", "success"
            )
            self.main_window.root.after(
                0,
                lambda: ui_utils.show_info(
                    "完成",
                    f"已成功将 {len(translations)} 条翻译写入\n{self.jar_path.name}",
                ),
            )

        except Exception as e:
            logging.error(f"写入 JAR 失败: {e}", exc_info=True)
            self._log(f"写入 JAR 失败: {e}", "CRITICAL")
            self._update_workbench_status(f"写入失败: {e}", "danger")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("写入失败", f"写入 JAR 时发生错误:\n{err}"),
            )
