from __future__ import annotations
import json
import logging
import os
import re
import threading
import zipfile
from pathlib import Path
from io import BytesIO

from gui import ui_utils


_TRANSLATABLE_FIELDS = {"name", "title", "description"}
_NAME_CHANGE_TYPE = "palladium:name_change"
_CONDITION_DESC_TYPES = {"palladium:property_buyable"}
_COMMAND_TEXT_PATTERN = re.compile(
    r'title\s+@s\s+actionbar\s+"([^"]*)"',
    re.IGNORECASE,
)


class PalladiumWorkflowManager:
    def __init__(self, project_info: dict, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.jar_path = Path(project_info["jar_path"])

        self._jar_data: dict[str, dict] = {}
        self._text_index: dict[str, list[dict]] = {}
        self._command_index: dict[str, list[dict]] = {}
        self._key_to_text: dict[str, str] = {}

    def _log(self, message: str, level: str = "INFO"):
        self.main_window.log_message(message, level)

    def _update_workbench_status(self, message: str, level: str = "info"):
        def _update():
            wb = getattr(self.main_window, 'workbench_instance', None)
            if wb and hasattr(wb, 'status_label'):
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
            self._scan_jar()

            if not self._jar_data:
                raise ValueError("未在 JAR 中找到 palladium/powers/*.json 文件。")

            self._log(f"共发现 {len(self._jar_data)} 个能力文件", "INFO")

            total_raw = sum(len(locs) for locs in self._text_index.values())
            unique_count = len(self._text_index)
            cmd_count = sum(len(locs) for locs in self._command_index.values())
            self._log(
                f"提取到 {total_raw} 条文本（去重后 {unique_count} 条唯一文本，"
                f"{cmd_count} 条命令文本）",
                "SUCCESS",
            )

            workbench_data = self._build_workbench_data()
            self._launch_workbench(workbench_data)

        except Exception as e:
            logging.error(f"Palladium 文本提取失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("处理失败", f"提取文本时发生错误:\n{err}"),
            )
            self.main_window.root.after(0, self.main_window._show_welcome_view)

    def _launch_workbench(self, workbench_data: dict):
        self.main_window.root.after(0, self.main_window._launch_palladium_workbench, workbench_data)

    def _scan_jar(self):
        self._jar_data.clear()
        self._text_index.clear()
        self._command_index.clear()

        with zipfile.ZipFile(self.jar_path, "r") as zf:
            for entry in zf.namelist():
                if "palladium/powers/" in entry and entry.endswith(".json") and not entry.endswith("/"):
                    try:
                        raw = zf.read(entry)
                        data = json.loads(raw)
                        self._jar_data[entry] = data
                    except (json.JSONDecodeError, zipfile.BadZipFile) as exc:
                        logging.warning(f"跳过无法解析的文件 {entry}: {exc}")

        for file_path, data in self._jar_data.items():
            self._extract_from_node(data, file_path, [])

    def _extract_from_node(self, node, file_path: str, json_path: list):
        if isinstance(node, dict):
            if "abilities" in node and isinstance(node["abilities"], dict):
                for ability_key, ability_val in node["abilities"].items():
                    self._extract_from_ability(
                        ability_val, file_path, ["abilities", ability_key]
                    )

            if (
                "type" in node
                and node["type"] == _NAME_CHANGE_TYPE
                and "name" in node
                and isinstance(node["name"], dict)
                and "text" in node["name"]
                and isinstance(node["name"]["text"], str)
                and node["name"]["text"].strip()
            ):
                self._register_text(
                    node["name"]["text"],
                    file_path,
                    json_path + ["name", "text"],
                    "name_text",
                )

            if (
                "type" in node
                and node["type"] in _CONDITION_DESC_TYPES
                and "description" in node
                and isinstance(node["description"], dict)
                and "text" in node["description"]
                and isinstance(node["description"]["text"], str)
                and node["description"]["text"].strip()
            ):
                self._register_text(
                    node["description"]["text"],
                    file_path,
                    json_path + ["description", "text"],
                    "condition_desc",
                )

            if (
                "name" in node
                and isinstance(node["name"], str)
                and node["name"].strip()
                and "type" not in node
                and json_path
                and json_path[-1] != "abilities"
            ):
                self._register_text(
                    node["name"], file_path, json_path + ["name"], "name"
                )

            for key, val in node.items():
                if key == "abilities":
                    continue
                if key in _TRANSLATABLE_FIELDS and isinstance(val, str) and val.strip():
                    self._register_text(val, file_path, json_path + [key], key)
                elif isinstance(val, (dict, list)):
                    self._extract_from_node(val, file_path, json_path + [key])

        elif isinstance(node, list):
            for i, item in enumerate(node):
                self._extract_from_node(item, file_path, json_path + [i])

    def _extract_from_ability(self, ability, file_path: str, json_path: list):
        if not isinstance(ability, dict):
            return

        for field in _TRANSLATABLE_FIELDS:
            val = ability.get(field)
            if isinstance(val, str) and val.strip():
                self._register_text(val, file_path, json_path + [field], field)

        if "titles" in ability and isinstance(ability["titles"], list):
            for i, title_obj in enumerate(ability["titles"]):
                if not isinstance(title_obj, dict):
                    continue
                for field in ("title", "description"):
                    val = title_obj.get(field)
                    if isinstance(val, str) and val.strip():
                        self._register_text(
                            val, file_path, json_path + ["titles", i, field], field
                        )

        for key, val in ability.items():
            if key in ("title", "description", "titles", "name"):
                continue
            if isinstance(val, (dict, list)):
                self._extract_from_node(val, file_path, json_path + [key])

        if "commands" in ability and isinstance(ability["commands"], list):
            self._extract_command_texts(ability["commands"], file_path, json_path + ["commands"])
        for cmd_key in ("first_tick_commands", "last_tick_commands"):
            if cmd_key in ability and isinstance(ability[cmd_key], list):
                self._extract_command_texts(
                    ability[cmd_key], file_path, json_path + [cmd_key]
                )

    def _extract_command_texts(self, commands: list, file_path: str, json_path: list):
        for i, cmd in enumerate(commands):
            if not isinstance(cmd, str):
                continue
            m = _COMMAND_TEXT_PATTERN.search(cmd)
            if m:
                text = m.group(1).strip()
                if text:
                    self._register_command_text(
                        text, file_path, json_path + [i], cmd
                    )

    def _register_text(self, text: str, file_path: str, json_path: list, field: str):
        entry = {"file": file_path, "path": json_path, "field": field}
        self._text_index.setdefault(text, []).append(entry)

    def _register_command_text(
        self, text: str, file_path: str, json_path: list, full_cmd: str
    ):
        entry = {
            "file": file_path,
            "path": json_path,
            "field": "command",
            "full_command": full_cmd,
        }
        self._command_index.setdefault(text, []).append(entry)

    def _build_workbench_data(self) -> dict:
        self._key_to_text.clear()
        items = []

        all_texts: list[tuple[str, str]] = []
        for text in self._text_index:
            all_texts.append((text, "text"))
        for text in self._command_index:
            if text not in self._text_index:
                all_texts.append((text, "command"))

        for text, source_type in all_texts:
            if source_type == "text":
                occurrences = len(self._text_index[text])
                first_loc = self._text_index[text][0]
            else:
                occurrences = len(self._command_index[text])
                first_loc = self._command_index[text][0]

            stable_key = self._make_stable_key(first_loc)
            self._key_to_text[stable_key] = text

            items.append(
                {
                    "key": stable_key,
                    "en": text,
                    "zh": "",
                    "source": f"出现 {occurrences} 次" if occurrences > 1 else "出现 1 次",
                }
            )

        return {
            "palladium": {
                "display_name": "Palladium 能力文本",
                "jar_name": self.jar_path.name,
                "items": items,
            }
        }

    @staticmethod
    def _make_stable_key(loc: dict) -> str:
        path_str = ".".join(str(p) for p in loc["path"])
        return f"{loc['file']}::{path_str}"

    def run_build_phase(self, translation_map: dict[str, str]):
        try:
            self._log(f"开始将翻译写入 JAR: {self.jar_path.name}", "INFO")

            applied = self._apply_translations(translation_map)
            self._log(f"共替换 {applied} 处文本", "INFO")

            if applied == 0:
                self._log("没有文本被替换，跳过写入。", "WARNING")
                self._update_workbench_status("没有文本被替换", "warning")
                return

            self._update_workbench_status("正在构建新的 JAR 文件...", "info")
            self._log("正在构建新的 JAR 文件...", "INFO")
            buf = BytesIO()
            with zipfile.ZipFile(self.jar_path, "r") as zin:
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        if item.filename in self._jar_data:
                            content = json.dumps(
                                self._jar_data[item.filename],
                                indent=2,
                                ensure_ascii=False,
                            )
                            zout.writestr(item, content.encode("utf-8"))
                        else:
                            zout.writestr(item, zin.read(item.filename))

            jar_bytes = buf.getvalue()
            self._log(f"新 JAR 数据大小: {len(jar_bytes)} 字节", "INFO")

            temp_path = self.jar_path.with_suffix(".jar.tmp")
            try:
                temp_path.write_bytes(jar_bytes)
                os.replace(str(temp_path), str(self.jar_path))
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

            translated_count = len(translation_map)
            self._log(
                f"完成！已将 {translated_count} 条翻译写入 JAR 文件。", "SUCCESS"
            )
            self._update_workbench_status(
                f"写入完成！{translated_count} 条翻译已写入 {self.jar_path.name}", "success"
            )
            self.main_window.root.after(
                0,
                lambda: ui_utils.show_info(
                    "完成",
                    f"已成功将 {translated_count} 条翻译写入\n{self.jar_path.name}",
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

    def _apply_translations(self, translation_map: dict[str, str]) -> int:
        applied = 0

        for stable_key, zh in translation_map.items():
            text = self._key_to_text.get(stable_key)
            if not text:
                continue

            for loc in self._text_index.get(text, []):
                file_data = self._jar_data.get(loc["file"])
                if file_data is None:
                    continue
                self._set_nested_value(file_data, loc["path"], zh)
                applied += 1

            for loc in self._command_index.get(text, []):
                file_data = self._jar_data.get(loc["file"])
                if file_data is None:
                    continue
                old_cmd = loc.get("full_command", "")
                if text in old_cmd:
                    new_cmd = old_cmd.replace(text, zh, 1)
                    self._set_nested_value(file_data, loc["path"], new_cmd)
                    applied += 1

        return applied

    @staticmethod
    def _set_nested_value(data: dict | list, path: list, value):
        current = data
        for key in path[:-1]:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list):
                current = current[key]
        last = path[-1]
        if isinstance(current, (dict, list)):
            current[last] = value
