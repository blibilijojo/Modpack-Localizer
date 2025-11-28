import logging
import re
from pathlib import Path
from typing import Dict
import tempfile
import shutil
import zipfile
import os
import json

class PackBuilder:
    def _build_json_file_robust(self, template_content: str, translations: Dict[str, str]) -> str:
        kv_pattern = re.compile(r'("((?:[^"\\]|\\.)*)")\s*:\s*("((?:[^"\\]|\\.)*)")')

        def replacer_callback(match: re.Match) -> str:
            key_with_quotes = match.group(1)
            original_value_with_quotes = match.group(3)

            try:
                key = json.loads(key_with_quotes)

                if key in translations:
                    translated_value = translations[key]
                    new_value_with_quotes = json.dumps(translated_value, ensure_ascii=False)
                    return match.group(0).replace(original_value_with_quotes, new_value_with_quotes, 1)

            except (json.JSONDecodeError, KeyError):
                pass
            
            return match.group(0)

        return kv_pattern.sub(replacer_callback, template_content)

    def _build_lang_file(self, template_content: str, translations: Dict[str, str]) -> str:
        output_lines = []
        line_regex = re.compile(r"^(\s*)([^#=\s]+)(\s*=\s*)(.*)$")

        for line_with_ending in template_content.splitlines(keepends=True):
            line_content = line_with_ending.rstrip('\r\n')
            match = line_regex.match(line_content)
            
            if match:
                indent, key, separator, original_value = match.groups()
                translated_value = translations.get(key, original_value).replace('\n', '\\n')
                new_line_content = f"{indent}{key}{separator}{translated_value}"
                original_ending = line_with_ending[len(line_content):]
                output_lines.append(new_line_content + original_ending)
            else:
                output_lines.append(line_with_ending)
                
        return "".join(output_lines)

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

    def run(self, output_dir: Path, final_translations_lookup_by_ns: dict, pack_settings: dict, namespace_formats: dict, raw_english_files: dict):
        logging.info(f"--- 开始资源包构建流程 (正则替换模式) ---")
        pack_as_zip = pack_settings.get('pack_as_zip', False)
        pack_description = pack_settings.get('pack_description', 'A Modpack Localization Pack')
        base_name_raw = pack_settings.get('pack_base_name', 'Generated_Pack')
        base_name = self._sanitize_filename(base_name_raw)
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            logging.info(f"在临时目录中构建资源包内容: {temp_dir}")
            for namespace, template_content in raw_english_files.items():
                translations = final_translations_lookup_by_ns.get(namespace, {})
                try:
                    lang_dir = temp_dir / "assets" / namespace / "lang"
                    lang_dir.mkdir(parents=True, exist_ok=True)
                    file_format = namespace_formats.get(namespace, 'json')
                    
                    if file_format == 'json':
                        output_content = self._build_json_file_robust(template_content, translations)
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
                escaped_description = json.dumps(pack_description, ensure_ascii=False)[1:-1]
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