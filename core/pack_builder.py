import logging
import re
from pathlib import Path
from typing import Dict
import tempfile
import shutil
import zipfile
import os
class PackBuilder:
    def _escape_string_for_json(self, text: str) -> str:
        text = text.replace('\\', '\\\\')
        text = text.replace('"', '\\"')
        text = text.replace('\n', '\\n')
        text = text.replace('\r', '\\r')
        text = text.replace('\t', '\\t')
        return text
    def _build_lang_file(self, template_content: str, translations: Dict[str, str]) -> str:
        output_lines = []
        line_regex = re.compile(r"^(\s*)([^#=\s]+)(\s*=\s*)(.*)$")
        for line in template_content.splitlines():
            match = line_regex.match(line)
            if match:
                indent, key, separator, original_value = match.groups()
                if key in translations:
                    translated_value = str(translations[key]).replace('\n', '\\n')
                    new_line = f"{indent}{key}{separator}{translated_value}"
                    output_lines.append(new_line)
                else:
                    output_lines.append(line)
            else:
                output_lines.append(line)
        output_content = "\n".join(output_lines)
        if template_content.endswith('\n') and not output_content.endswith('\n'):
            output_content += '\n'
        return output_content
    def _build_json_file_pure_text_replacement(self, template_content: str, translations: Dict[str, str]) -> str:
        def replacer(match):
            key_with_quotes = match.group(1)
            key_content_escaped = match.group(2)
            separator = match.group(3)
            try:
                key = key_content_escaped.encode('latin-1').decode('unicode-escape')
            except Exception:
                return match.group(0)
            if key in translations:
                translated_text = translations[key]
                escaped_translated_text = self._escape_string_for_json(translated_text)
                return f'{key_with_quotes}{separator}"{escaped_translated_text}"'
            else:
                return match.group(0)
        pattern = re.compile(r'("((?:[^"\\]|\\.)*)")(\s*:\s*)("((?:[^"\\]|\\.)*)")')
        output_content = pattern.sub(replacer, template_content)
        return output_content
    def _sanitize_filename(self, text: str) -> str:
        first_line = text.splitlines()[0]
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
    def run(self, output_dir: Path, final_translations_lookup_by_ns: dict, pack_settings: dict, namespace_formats: dict, raw_english_files: dict):
        logging.info(f"--- 开始资源包构建流程 (纯文本替换模式) ---")
        pack_as_zip = pack_settings.get('pack_as_zip', False)
        pack_description = pack_settings.get('pack_description', 'A Modpack Localization Pack')
        base_name_raw = pack_settings.get('pack_base_name', 'Generated_Pack')
        base_name = self._sanitize_filename(base_name_raw)
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            logging.info(f"在临时目录中构建资源包内容: {temp_dir}")
            for namespace, template_content in raw_english_files.items():
                translations = final_translations_lookup_by_ns.get(namespace, {})
                if not translations:
                    continue
                try:
                    lang_dir = temp_dir / "assets" / namespace / "lang"
                    lang_dir.mkdir(parents=True, exist_ok=True)
                    file_format = namespace_formats.get(namespace, 'json')
                    if file_format == 'json':
                        output_content = self._build_json_file_pure_text_replacement(template_content, translations)
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
            try:
                escaped_description = self._escape_string_for_json(pack_description)
                pack_mcmeta_content = (
                    "{\n"
                    '    "pack": {\n'
                    f'        "pack_format": {pack_settings["pack_format"]},\n'
                    f'        "description": "{escaped_description}"\n'
                    '    }\n'
                    "}"
                )
                (temp_dir / "pack.mcmeta").write_text(pack_mcmeta_content, encoding='utf-8')
                icon_path_str = pack_settings.get('pack_icon_path', '')
                if icon_path_str and Path(icon_path_str).is_file():
                    shutil.copy(icon_path_str, temp_dir / "pack.png")
            except Exception as e:
                logging.error(f"写入元数据时出错: {e}", exc_info=True)
                return False, f"写入元数据时出错: {e}"
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
                        logging.info(f"成功将资源包压缩到: {final_unique_path}")
                    finally:
                        if temp_zip_path.exists():
                            os.remove(temp_zip_path)
                    final_output_path = final_unique_path
                else:
                    final_folder_path = output_dir / base_name
                    final_unique_path = self._get_unique_path(final_folder_path)
                    shutil.move(str(temp_dir), str(final_unique_path))
                    final_output_path = final_unique_path
                logging.info(f"成功创建资源包: {final_output_path.name}")
            except Exception as e:
                logging.error(f"完成最终资源包时出错: {e}", exc_info=True)
                return False, f"完成最终资源包时出错: {e}"
        logging.info("--- 资源包构建成功！ ---")
        return True, "资源包构建成功！"