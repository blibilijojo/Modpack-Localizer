from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from gui import ui_utils

_LANG_FILE_PATTERN = "*.lang"
_SHADER_LANG_DIR = "shaders/lang"


def _parse_lang_lines(raw: str) -> list[dict]:
    lines = []
    for i, line in enumerate(raw.splitlines(keepends=True)):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            lines.append({"type": "comment", "raw": line})
            continue
        sep_idx = -1
        for ci, ch in enumerate(stripped):
            if ch in ("=", ":"):
                sep_idx = ci
                break
        if sep_idx < 0:
            lines.append({"type": "comment", "raw": line})
            continue
        key = stripped[:sep_idx].strip()
        value = stripped[sep_idx + 1:].strip()
        lines.append({"type": "kv", "key": key, "value": value, "raw": line})
    return lines


def _find_lang_dir(shader_dir: Path) -> Path | None:
    candidates = [
        shader_dir / "shaders" / "lang",
        shader_dir / "lang",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


class ShaderWorkflowManager:
    def __init__(self, project_info: dict, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.shader_dir = Path(project_info["shader_dir"])
        self.output_dir = Path(project_info.get("output_dir", ""))

        self._en_lines: list[dict] = []
        self._zh_existing: dict[str, str] = {}

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
            if not self.shader_dir.is_dir():
                raise FileNotFoundError(f"光影包文件夹不存在: {self.shader_dir}")

            self._log(f"正在扫描光影包: {self.shader_dir.name}", "INFO")

            lang_dir = _find_lang_dir(self.shader_dir)
            if not lang_dir:
                raise FileNotFoundError(
                    f"未找到 shaders/lang/ 目录。\n"
                    f"请确认光影包结构正确（应包含 shaders/lang/ 子目录）。"
                )

            en_us_path = lang_dir / "en_us.lang"
            if not en_us_path.is_file():
                other_langs = list(lang_dir.glob("*.lang"))
                if other_langs:
                    en_us_path = other_langs[0]
                    self._log(f"未找到 en_us.lang，使用 {en_us_path.name} 作为源语言", "WARNING")
                else:
                    raise FileNotFoundError(f"shaders/lang/ 目录中没有任何 .lang 文件")

            self._log(f"读取语言文件: {en_us_path.relative_to(self.shader_dir)}", "INFO")
            raw = en_us_path.read_text(encoding="utf-8-sig", errors="replace")
            self._en_lines = _parse_lang_lines(raw)
            en_kv_count = sum(1 for l in self._en_lines if l["type"] == "kv")
            self._log(f"解析到 {en_kv_count} 条翻译条目", "SUCCESS")

            self._log("检查已有翻译...", "INFO")
            self._zh_existing = {}
            zh_cn_path = lang_dir / "zh_cn.lang"
            if zh_cn_path.is_file():
                raw_zh = zh_cn_path.read_text(encoding="utf-8-sig", errors="replace")
                zh_lines = _parse_lang_lines(raw_zh)
                for l in zh_lines:
                    if l["type"] == "kv":
                        self._zh_existing[l["key"]] = l["value"]
                self._log(f"发现已有 zh_cn.lang，包含 {len(self._zh_existing)} 条翻译", "SUCCESS")
            else:
                self._log("未找到已有 zh_cn.lang，将从零开始翻译", "INFO")

            workbench_data = self._build_workbench_data()
            total = sum(len(ns.get("items", [])) for ns in workbench_data.values())
            self._log(f"共 {total} 条可翻译条目，正在打开工作台...", "SUCCESS")

            self.main_window.root.after(
                0, self.main_window._launch_shader_workbench, workbench_data
            )

        except Exception as e:
            logging.error(f"光影包扫描失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("扫描失败", f"扫描光影包时发生错误:\n{err}"),
            )
            self.main_window.root.after(0, self.main_window._show_welcome_view)

    def _build_workbench_data(self) -> dict:
        items = []
        for line in self._en_lines:
            if line["type"] != "kv":
                continue
            key = line["key"]
            en_value = line["value"]
            zh_value = self._zh_existing.get(key, "")
            if zh_value:
                source = "已有翻译"
            else:
                source = "待翻译"
            items.append({
                "key": key,
                "en": en_value,
                "zh": zh_value,
                "source": source,
            })

        return {
            "shader_lang": {
                "display_name": f"{self.shader_dir.name} / lang",
                "jar_name": self.shader_dir.name,
                "items": items,
            }
        }

    def run_build_phase(self, final_workbench_data: dict):
        try:
            self._log("开始生成汉化文件...", "INFO")
            self._update_status("正在生成汉化文件...")

            translations: dict[str, str] = {}
            for ns_data in final_workbench_data.values():
                for item in ns_data.get("items", []):
                    zh = item.get("zh", "").strip()
                    key = item.get("key", "").strip()
                    if zh and key:
                        translations[key] = zh

            self._log(f"共 {len(translations)} 条翻译", "INFO")

            out_lines = []
            for line in self._en_lines:
                if line["type"] == "kv":
                    key = line["key"]
                    if key in translations:
                        out_lines.append(f"{key}={translations[key]}\n")
                    else:
                        out_lines.append(line["raw"])
                else:
                    out_lines.append(line["raw"])

            content = "".join(out_lines)

            if self.output_dir and self.output_dir != self.shader_dir:
                dest_lang_dir = self.output_dir / "shaders" / "lang"
                dest_lang_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_lang_dir / "zh_cn.lang"
            else:
                lang_dir = _find_lang_dir(self.shader_dir)
                if not lang_dir:
                    lang_dir = self.shader_dir / "shaders" / "lang"
                    lang_dir.mkdir(parents=True, exist_ok=True)
                dest_path = lang_dir / "zh_cn.lang"

            if dest_path.is_file():
                backup = dest_path.with_suffix(".lang.bak")
                shutil.copy2(str(dest_path), str(backup))
                self._log(f"已备份原文件: {backup.name}", "INFO")

            dest_path.write_text(content, encoding="utf-8")

            self._log(f"汉化文件已写入: {dest_path}", "SUCCESS")
            self._update_status(f"汉化完成！已写入 {dest_path.name}")

            self.main_window.root.after(
                0,
                lambda: ui_utils.show_info(
                    "完成",
                    f"已生成汉化文件:\n{dest_path}\n\n共 {len(translations)} 条翻译",
                ),
            )

        except Exception as e:
            logging.error(f"写入汉化文件失败: {e}", exc_info=True)
            self._log(f"写入失败: {e}", "CRITICAL")
            self._update_status(f"写入失败: {e}")
            self.main_window.root.after(
                0,
                lambda err=e: ui_utils.show_error("写入失败", f"写入汉化文件时发生错误:\n{err}"),
            )
