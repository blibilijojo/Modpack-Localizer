from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from gui import ui_utils

_SCAN_TARGETS = [
    "advancements", "functions", "loot_tables", "item_modifiers",
    "recipes", "predicates", "tags", "damage_types", "dimension", "worldgen",
]

_MCFUNCTION_JSON_RE = re.compile(r'\{[^{}]*\}')
_MCFUNCTION_CMD_RE = re.compile(
    r'^\s*(tellraw|title|execute)\b', re.IGNORECASE
)


def _is_translatable_text(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    if len(t) < 2:
        return False
    if t.startswith("/") or t.startswith("#"):
        return False
    if re.match(r'^[a-z0-9_.:]+$', t):
        return False
    if re.match(r'^[a-z_]+:[a-z_/]+$', t):
        return False
    return True


def _extract_text_from_component(obj, path_prefix: str = ""):
    results = []
    if isinstance(obj, dict):
        if "text" in obj and isinstance(obj["text"], str):
            val = obj["text"]
            if _is_translatable_text(val):
                results.append({
                    "json_path": f"{path_prefix}.text" if path_prefix else "text",
                    "text": val,
                })
        if "translate" in obj and isinstance(obj["translate"], str):
            val = obj["translate"]
            if _is_translatable_text(val):
                results.append({
                    "json_path": f"{path_prefix}.translate" if path_prefix else "translate",
                    "text": val,
                })
        if "extra" in obj and isinstance(obj["extra"], list):
            ep = f"{path_prefix}.extra" if path_prefix else "extra"
            for i, item in enumerate(obj["extra"]):
                results.extend(_extract_text_from_component(item, f"{ep}[{i}]"))
        if "with" in obj and isinstance(obj["with"], list):
            wp = f"{path_prefix}.with" if path_prefix else "with"
            for i, item in enumerate(obj["with"]):
                results.extend(_extract_text_from_component(item, f"{wp}[{i}]"))
        for key in ("score", "selector", "nbt", "keybind"):
            if key in obj:
                pass
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            p = f"{path_prefix}[{i}]" if path_prefix else f"[{i}]"
            results.extend(_extract_text_from_component(item, p))
    return results


def _extract_from_json_file(file_path: Path, rel_path: str):
    try:
        raw = file_path.read_text(encoding="utf-8-sig", errors="replace")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    entries = []

    if file_path.name == "pack.mcmeta":
        if isinstance(data, dict) and "pack" in data:
            pack = data["pack"]
            desc = pack.get("description")
            if isinstance(desc, str) and _is_translatable_text(desc):
                entries.append({
                    "file": rel_path,
                    "json_path": "pack.description",
                    "text": desc,
                })
            elif isinstance(desc, dict):
                found = _extract_text_from_component(desc, "pack.description")
                for f in found:
                    f["file"] = rel_path
                    entries.append(f)
        return entries

    if isinstance(data, dict):
        _walk_json_dict(data, "", entries, rel_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                _walk_json_dict(item, f"[{i}]", entries, rel_path)
    return entries


def _walk_json_dict(obj: dict, path_prefix: str, entries: list, rel_path: str):
    if "text" in obj and isinstance(obj["text"], str):
        val = obj["text"]
        if _is_translatable_text(val):
            entries.append({
                "file": rel_path,
                "json_path": f"{path_prefix}.text" if path_prefix else "text",
                "text": val,
            })
    if "translate" in obj and isinstance(obj["translate"], str):
        val = obj["translate"]
        if _is_translatable_text(val):
            entries.append({
                "file": rel_path,
                "json_path": f"{path_prefix}.translate" if path_prefix else "translate",
                "text": val,
            })
    if "extra" in obj and isinstance(obj["extra"], list):
        ep = f"{path_prefix}.extra" if path_prefix else "extra"
        for i, item in enumerate(obj["extra"]):
            if isinstance(item, dict):
                _walk_json_dict(item, f"{ep}[{i}]", entries, rel_path)
            elif isinstance(item, str) and _is_translatable_text(item):
                entries.append({
                    "file": rel_path,
                    "json_path": f"{ep}[{i}]",
                    "text": item,
                })
    if "with" in obj and isinstance(obj["with"], list):
        wp = f"{path_prefix}.with" if path_prefix else "with"
        for i, item in enumerate(obj["with"]):
            if isinstance(item, dict):
                _walk_json_dict(item, f"{wp}[{i}]", entries, rel_path)
    for key, val in obj.items():
        if key in ("text", "translate", "extra", "with", "score", "selector", "nbt", "keybind"):
            continue
        if isinstance(val, dict):
            child_path = f"{path_prefix}.{key}" if path_prefix else key
            _walk_json_dict(val, child_path, entries, rel_path)
        elif isinstance(val, list):
            child_path = f"{path_prefix}.{key}" if path_prefix else key
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    _walk_json_dict(item, f"{child_path}[{i}]", entries, rel_path)


def _extract_from_mcfunction_file(file_path: Path, rel_path: str):
    entries = []
    try:
        lines = file_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except UnicodeDecodeError:
        return entries

    for line_no, line in enumerate(lines, 1):
        if not _MCFUNCTION_CMD_RE.match(line):
            continue
        for match in _MCFUNCTION_JSON_RE.finditer(line):
            json_str = match.group(0)
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            found = _extract_text_from_component(data, "")
            for f in found:
                f["file"] = rel_path
                f["line"] = line_no
                f["_raw_json"] = json_str
                entries.append(f)
    return entries


class DatapackWorkflowManager:
    def __init__(self, project_info: dict, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.datapack_dir = Path(project_info["datapack_dir"])
        self.output_dir = Path(project_info.get("output_dir", ""))

        self._extracted_entries: list[dict] = []
        self._file_cache: dict[str, list[str]] = {}

    def _log(self, message: str, level: str = "INFO"):
        self.main_window.log_message(message, level)

    def _update_status(self, message: str):
        def _do():
            wb = getattr(self.main_window, "workbench_instance", None)
            if wb and hasattr(wb, "status_label"):
                try:
                    wb.status_label.config(text=message)
                except Exception:
                    pass
        try:
            self.main_window.root.after(0, _do)
        except Exception:
            pass

    def run_extraction_phase(self):
        try:
            if not self.datapack_dir.is_dir():
                raise FileNotFoundError(f"数据包文件夹不存在: {self.datapack_dir}")

            self._log(f"正在扫描数据包: {self.datapack_dir.name}", "INFO")

            data_dir = self.datapack_dir / "data"
            if not data_dir.is_dir():
                raise FileNotFoundError(
                    f"未找到 data/ 目录。\n"
                    f"请确认数据包结构正确（应包含 data/ 子目录）。"
                )

            all_entries = []

            pack_mcmeta = self.datapack_dir / "pack.mcmeta"
            if pack_mcmeta.is_file():
                entries = _extract_from_json_file(pack_mcmeta, "pack.mcmeta")
                all_entries.extend(entries)
                if entries:
                    self._log(f"  pack.mcmeta: {len(entries)} 条", "INFO")

            for namespace_dir in sorted(data_dir.iterdir()):
                if not namespace_dir.is_dir():
                    continue
                ns_name = namespace_dir.name
                for target in _SCAN_TARGETS:
                    target_dir = namespace_dir / target
                    if not target_dir.is_dir():
                        continue
                    for fpath in sorted(target_dir.rglob("*")):
                        if not fpath.is_file():
                            continue
                        rel = str(fpath.relative_to(self.datapack_dir))
                        if fpath.suffix == ".json":
                            entries = _extract_from_json_file(fpath, rel)
                            all_entries.extend(entries)
                        elif fpath.suffix == ".mcfunction":
                            entries = _extract_from_mcfunction_file(fpath, rel)
                            all_entries.extend(entries)

            self._extracted_entries = all_entries
            self._log(f"共提取到 {len(all_entries)} 条可翻译文本", "SUCCESS")

            if not all_entries:
                self._log("未发现需要翻译的文本内容。", "WARNING")
                self.main_window.root.after(
                    0,
                    lambda: ui_utils.show_info("扫描完成", "未在数据包中发现需要翻译的文本内容。"),
                )
                self.main_window.root.after(0, self.main_window._show_welcome_view)
                return

            workbench_data = self._build_workbench_data()
            self._log("正在打开工作台...", "INFO")
            self.main_window.root.after(
                0, self.main_window._launch_datapack_workbench, workbench_data
            )

        except Exception as e:
            logging.error(f"数据包扫描失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("扫描失败", f"扫描数据包时发生错误:\n{err}"),
            )
            self.main_window.root.after(0, self.main_window._show_welcome_view)

    def _build_workbench_data(self) -> dict:
        seen = set()
        items = []
        for entry in self._extracted_entries:
            text = entry["text"]
            file_rel = entry["file"]
            json_path = entry["json_path"]
            location = f"{file_rel} → {json_path}"
            dedup_key = (file_rel, json_path, text)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            items.append({
                "key": location,
                "en": text,
                "zh": "",
                "source": file_rel,
            })

        return {
            "datapack_texts": {
                "display_name": f"{self.datapack_dir.name} / 数据包文本",
                "jar_name": self.datapack_dir.name,
                "items": items,
            }
        }

    def run_build_phase(self, final_workbench_data: dict):
        try:
            self._log("开始写入翻译...", "INFO")
            self._update_status("正在写入翻译到数据包文件...")

            translations: dict[tuple[str, str, str], str] = {}
            for ns_data in final_workbench_data.values():
                for item in ns_data.get("items", []):
                    zh = item.get("zh", "").strip()
                    key = item.get("key", "").strip()
                    en = item.get("en", "").strip()
                    if not zh or not key:
                        continue
                    if zh == en:
                        continue
                    parts = key.split(" → ", 1)
                    if len(parts) == 2:
                        file_rel, json_path = parts
                        translations[(file_rel, json_path, en)] = zh

            if not translations:
                self._log("没有需要写入的翻译。", "WARNING")
                self.main_window.root.after(
                    0, lambda: ui_utils.show_info("提示", "没有需要写入的翻译。")
                )
                return

            self._log(f"共 {len(translations)} 条翻译需要写入", "INFO")

            files_to_update: dict[str, list[tuple[str, str, str]]] = {}
            for (file_rel, json_path, en_text), zh_text in translations.items():
                files_to_update.setdefault(file_rel, []).append(
                    (json_path, en_text, zh_text)
                )

            modified_count = 0
            if self.output_dir and self.output_dir != self.datapack_dir:
                base_dir = self.output_dir
                base_dir.mkdir(parents=True, exist_ok=True)
            else:
                base_dir = self.datapack_dir

            for file_rel, replacements in files_to_update.items():
                src_path = self.datapack_dir / file_rel
                dst_path = base_dir / file_rel

                if not src_path.is_file():
                    self._log(f"  跳过不存在的文件: {file_rel}", "WARNING")
                    continue

                dst_path.parent.mkdir(parents=True, exist_ok=True)

                if src_path.resolve() != dst_path.resolve() and dst_path.is_file():
                    pass
                elif not dst_path.is_file() and src_path.resolve() != dst_path.resolve():
                    shutil.copy2(str(src_path), str(dst_path))

                if file_rel.endswith(".json") or file_rel.endswith(".mcmeta"):
                    self._apply_json_translations(dst_path, replacements)
                    modified_count += 1
                elif file_rel.endswith(".mcfunction"):
                    self._apply_mcfunction_translations(dst_path, replacements)
                    modified_count += 1

            self._log(f"已修改 {modified_count} 个文件", "SUCCESS")
            self._update_status(f"翻译完成！已修改 {modified_count} 个文件")

            self.main_window.root.after(
                0,
                lambda: ui_utils.show_info(
                    "完成",
                    f"已将翻译写入数据包文件。\n\n"
                    f"修改文件数: {modified_count}\n"
                    f"翻译条目数: {len(translations)}\n"
                    f"输出目录: {base_dir}",
                ),
            )

        except Exception as e:
            logging.error(f"写入翻译失败: {e}", exc_info=True)
            self._log(f"写入失败: {e}", "CRITICAL")
            self._update_status(f"写入失败: {e}")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("写入失败", f"写入翻译时发生错误:\n{err}"),
            )

    def _apply_json_translations(self, file_path: Path, replacements: list[tuple[str, str, str]]):
        try:
            raw = file_path.read_text(encoding="utf-8-sig", errors="replace")
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._log(f"  JSON 解析失败: {file_path.name}: {e}", "WARNING")
            return

        for json_path, en_text, zh_text in replacements:
            if file_path.name == "pack.mcmeta" and json_path == "pack.description":
                if isinstance(data, dict) and "pack" in data:
                    desc = data["pack"].get("description")
                    if isinstance(desc, str) and desc == en_text:
                        data["pack"]["description"] = zh_text
                continue

            _replace_in_json(data, json_path, en_text, zh_text)

        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_mcfunction_translations(self, file_path: Path, replacements: list[tuple[str, str, str]]):
        try:
            lines = file_path.read_text(encoding="utf-8-sig", errors="replace").splitlines(keepends=True)
        except UnicodeDecodeError:
            return

        for i, line in enumerate(lines):
            if not _MCFUNCTION_CMD_RE.match(line):
                continue
            for match in _MCFUNCTION_JSON_RE.finditer(line):
                json_str = match.group(0)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    continue
                changed = False
                for json_path, en_text, zh_text in replacements:
                    if _replace_in_json(data, json_path, en_text, zh_text):
                        changed = True
                if changed:
                    new_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                    lines[i] = line[:match.start()] + new_json + line[match.end():]
                    line = lines[i]

        file_path.write_text("".join(lines), encoding="utf-8")


def _navigate_to_parent(obj, json_path: str):
    parts = json_path.split(".")
    current = obj
    for part in parts[:-1]:
        m = re.match(r'^(.*?)\[(\d+)\]$', part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if key:
                current = current[key]
            current = current[idx]
        else:
            current = current[part]
    return current, parts[-1]


def _replace_in_json(data, json_path: str, en_text: str, zh_text: str) -> bool:
    try:
        parent, last_key = _navigate_to_parent(data, json_path)
        m = re.match(r'^(.*?)\[(\d+)\]$', last_key)
        if m:
            key, idx = m.group(1), int(m.group(2))
            target = parent[key] if key else parent
            if isinstance(target[idx], str) and target[idx] == en_text:
                target[idx] = zh_text
                return True
            elif isinstance(target[idx], dict) and target[idx].get("text") == en_text:
                target[idx]["text"] = zh_text
                return True
            elif isinstance(target[idx], dict) and target[idx].get("translate") == en_text:
                target[idx]["translate"] = zh_text
                return True
        else:
            if isinstance(parent.get(last_key), str) and parent.get(last_key) == en_text:
                parent[last_key] = zh_text
                return True
            elif isinstance(parent.get(last_key), dict):
                obj = parent[last_key]
                if obj.get("text") == en_text:
                    obj["text"] = zh_text
                    return True
                if obj.get("translate") == en_text:
                    obj["translate"] = zh_text
                    return True
    except (KeyError, IndexError, TypeError):
        pass

    if _deep_replace(data, en_text, zh_text):
        return True
    return False


def _deep_replace(obj, en_text: str, zh_text: str) -> bool:
    if isinstance(obj, dict):
        if obj.get("text") == en_text:
            obj["text"] = zh_text
            return True
        if obj.get("translate") == en_text:
            obj["translate"] = zh_text
            return True
        for v in obj.values():
            if isinstance(v, (dict, list)):
                if _deep_replace(v, en_text, zh_text):
                    return True
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and item == en_text:
                obj[i] = zh_text
                return True
            if isinstance(item, (dict, list)):
                if _deep_replace(item, en_text, zh_text):
                    return True
    return False
