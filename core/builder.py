from __future__ import annotations
import logging
import re
from pathlib import Path
import tempfile
import shutil
import zipfile
import os
import json

from .models import (
    TranslationResult, ExtractionResult, NamespaceInfo,
    PackSettings, JSON_KEY_VALUE_PATTERN, LANG_KV_PATTERN
)

class Builder:

    def _build_json_file(self, template_content: str, translations: dict[str, str]) -> str:
        key_info = []
        for match in JSON_KEY_VALUE_PATTERN.finditer(template_content):
            key_info.append({
                'key': match.group(1),
                'original_value': match.group(2),
                'start': match.start(),
                'end': match.end(),
                'full_match': match.group(0)
            })
        return self._rebuild_file_from_key_info(template_content, key_info, translations, 'json')

    def _build_lang_file(self, template_content: str, translations: dict[str, str]) -> str:
        key_info = []
        for match in LANG_KV_PATTERN.finditer(template_content):
            key = match.group(1)
            start, end = match.span()

            line_start = template_content.rfind('\n', 0, start)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1

            indent = template_content[line_start:start].split('\n')[-1]

            key_info.append({
                'key': key,
                'original_value': match.group(2),
                'start': start,
                'end': end,
                'full_match': match.group(0),
                'indent': indent
            })
        return self._rebuild_file_from_key_info(template_content, key_info, translations, 'lang')

    def _rebuild_file_from_key_info(
        self,
        template_content: str,
        key_info: list[dict],
        translations: dict[str, str],
        file_format: str,
    ) -> str:
        key_info.sort(key=lambda x: x['start'])

        output: list[str] = []
        current_pos = 0
        comment_counter = 0

        for info in key_info:
            output.append(template_content[current_pos:info['start']])

            if info['key'] == '_comment':
                comment_counter += 1
                translated_key = f'_comment_{comment_counter}'
                if translated_key in translations:
                    translated_value = translations[translated_key].replace('"', '\\"')
                    output.append(self._format_kv_pair(info['key'], translated_value, file_format, info))
                else:
                    output.append(info['full_match'])
            elif info['key'] in translations:
                translated_value = translations[info['key']].replace('"', '\\"')
                output.append(self._format_kv_pair(info['key'], translated_value, file_format, info))
            else:
                output.append(info['full_match'])

            current_pos = info['end']

        output.append(template_content[current_pos:])

        result = ''.join(output)
        return result.replace('\r\n', '\n').replace('\r', '\n')

    def _format_kv_pair(self, key: str, value: str, file_format: str, info: dict) -> str:
        if file_format == 'json':
            return f'"{key}":"{value}"'
        else:
            indent = info.get('indent', '')
            return f'{indent}{key} = {value}'

    def _sanitize_filename(self, text: str) -> str:
        first_line = text.splitlines()[0] if text else ""
        if not first_line.strip():
            return "GeneratedPack"
        return re.sub(r'[\\/*?:"<>|]', "", first_line).strip()

    def _get_unique_path(self, target_path: Path) -> Path:
        if not target_path.exists():
            return target_path
        parent = target_path.parent
        if target_path.name.lower().endswith('.zip'):
            stem = target_path.name[:-4]
            extension = target_path.name[-4:]
        else:
            stem = target_path.name
            extension = ""
        counter = 1
        while True:
            new_name = f"{stem} ({counter}){extension}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def _resolve_namespace_and_format(self, namespace: str, extraction_result: ExtractionResult) -> tuple[str, str]:
        if ":" in namespace:
            base_namespace, file_format = namespace.split(":", 1)
            return base_namespace, file_format
        namespace_info = extraction_result.namespace_info.get(namespace, NamespaceInfo(name=namespace))
        return namespace, namespace_info.file_format

    def _build_translations_lookup(self, translation_result: TranslationResult) -> dict[str, dict[str, str]]:
        lookup: dict[str, dict[str, str]] = {}
        for namespace, entries in translation_result.workbench_data.items():
            ns_translations = {}
            for key, entry in entries.items():
                if entry.zh and entry.zh.strip():
                    ns_translations[key] = entry.zh
            lookup[namespace] = ns_translations
        return lookup

    def _write_lang_files(
        self,
        temp_dir: Path,
        translations_lookup: dict[str, dict[str, str]],
        extraction_result: ExtractionResult,
    ) -> tuple[bool, str]:
        for namespace, translations in translations_lookup.items():
            template_content = extraction_result.raw_english_files.get(namespace, '{}')

            try:
                base_namespace, file_format = self._resolve_namespace_and_format(namespace, extraction_result)

                lang_dir = temp_dir / "assets" / base_namespace / "lang"
                lang_dir.mkdir(parents=True, exist_ok=True)

                if file_format == 'json':
                    output_content = self._build_json_file(template_content, translations)
                    target_path = lang_dir / "zh_cn.json"
                elif file_format == 'lang':
                    output_content = self._build_lang_file(template_content, translations)
                    target_path = lang_dir / "zh_cn.lang"
                else:
                    continue

                target_path.write_text(output_content, encoding='utf-8')
            except Exception as e:
                logging.error(f"为 '{namespace}' 构建文件时出错: {e}", exc_info=True)
                return False, f"构建 '{namespace}' 文件时出错: {e}"

        return True, ""

    def _write_pack_metadata(self, temp_dir: Path, pack_settings: PackSettings) -> tuple[bool, str]:
        try:
            pack_mcmeta_data = {
                "pack": {
                    "pack_format": pack_settings.pack_format,
                    "description": pack_settings.pack_description
                }
            }
            (temp_dir / "pack.mcmeta").write_text(
                json.dumps(pack_mcmeta_data, indent=4, ensure_ascii=False),
                encoding='utf-8'
            )

            if pack_settings.pack_icon_path and Path(pack_settings.pack_icon_path).is_file():
                shutil.copy(pack_settings.pack_icon_path, temp_dir / "pack.png")
        except Exception as e:
            logging.error(f"写入元数据时出错: {e}", exc_info=True)
            return False, f"写入元数据时出错: {e}"

        return True, ""

    def _generate_output(
        self,
        temp_dir: Path,
        output_dir: Path,
        base_name: str,
        pack_as_zip: bool,
    ) -> tuple[bool, str, Path | None]:
        try:
            if pack_as_zip:
                final_zip_path = output_dir / (base_name + '.zip')
                final_unique_path = self._get_unique_path(final_zip_path)
                temp_zip_path = final_unique_path.with_suffix('.zip.tmp')

                try:
                    with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for file_path in temp_dir.rglob('*'):
                            if file_path.is_file():
                                arcname = file_path.relative_to(temp_dir)
                                zf.write(file_path, arcname)
                    os.rename(temp_zip_path, final_unique_path)
                    final_output_path = final_unique_path
                finally:
                    if temp_zip_path.exists():
                        os.remove(temp_zip_path)
            else:
                final_folder_path = output_dir / base_name
                final_unique_path = self._get_unique_path(final_folder_path)
                shutil.move(str(temp_dir), str(final_unique_path))
                final_output_path = final_unique_path

            logging.info(f"成功创建资源包: {final_output_path}")
            return True, "", final_output_path
        except Exception as e:
            logging.error(f"完成最终资源包时出错: {e}", exc_info=True)
            return False, f"完成最终资源包时出错: {e}", None

    def run(
        self,
        output_dir: Path,
        translation_result: TranslationResult,
        extraction_result: ExtractionResult,
        pack_settings: PackSettings
    ) -> tuple[bool, str]:
        logging.info(f"=== 阶段 3: 开始资源包构建流程 (正则替换模式) ===")

        base_name = self._sanitize_filename(pack_settings.pack_base_name)

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            logging.debug(f"在临时目录中构建资源包内容: {temp_dir}")

            translations_lookup = self._build_translations_lookup(translation_result)

            success, error_msg = self._write_lang_files(temp_dir, translations_lookup, extraction_result)
            if not success:
                return False, error_msg

            success, error_msg = self._write_pack_metadata(temp_dir, pack_settings)
            if not success:
                return False, error_msg

            success, error_msg, final_output_path = self._generate_output(
                temp_dir, output_dir, base_name, pack_settings.pack_as_zip
            )
            if not success:
                return False, error_msg

        logging.info("=== 资源包构建成功完成 ===")
        return True, f"资源包构建成功！输出位置: {final_output_path}"
