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
    def _build_json_file(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        基于正则表达式的JSON语言文件逆向生成
        """
        # 使用与提取时相同的正则表达式模式
        JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
        
        # 提取模板中的所有键值对信息
        key_info = []
        for match in JSON_KEY_VALUE_PATTERN.finditer(template_content):
            key = match.group(1)
            original_value = match.group(2)
            start, end = match.span()
            key_info.append({
                'key': key,
                'original_value': original_value,
                'start': start,
                'end': end,
                'full_match': match.group(0)
            })
        
        # 按出现顺序排序
        key_info.sort(key=lambda x: x['start'])
        
        # 构建输出内容，保留原始格式
        output = []
        current_pos = 0
        
        for info in key_info:
            # 添加匹配前的内容
            output.append(template_content[current_pos:info['start']])
            
            # 替换值
            if info['key'] in translations:
                translated_value = translations[info['key']].replace('"', '\\"')
                # 保持原始键的格式，只替换值
                output.append(f'"{info["key"]}":"{translated_value}"')
            else:
                # 保留原始值
                output.append(info['full_match'])
            
            current_pos = info['end']
        
        # 添加剩余内容
        output.append(template_content[current_pos:])
        
        return ''.join(output)
    
    def _build_lang_file(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        基于正则表达式的lang语言文件逆向生成
        """
        # 使用与提取时相同的正则表达式模式
        LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
        
        # 提取模板中的所有键值对信息
        key_info = []
        for match in LANG_KV_PATTERN.finditer(template_content):
            key = match.group(1)
            original_value = match.group(2)
            start, end = match.span()
            
            # 获取行首空格
            line_start = template_content.rfind('\n', 0, start)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            
            indent = template_content[line_start:start].split('\n')[-1]
            
            key_info.append({
                'key': key,
                'original_value': original_value,
                'start': start,
                'end': end,
                'full_match': match.group(0),
                'indent': indent
            })
        
        # 按出现顺序排序
        key_info.sort(key=lambda x: x['start'])
        
        # 构建输出内容，保留原始格式
        output = []
        current_pos = 0
        
        for info in key_info:
            # 添加匹配前的内容
            output.append(template_content[current_pos:info['start']])
            
            # 替换值
            if info['key'] in translations:
                translated_value = translations[info['key']]
                # 保持原始缩进和键的格式，只替换值
                output.append(f'{info["indent"]}{info["key"]} = {translated_value}')
            else:
                # 保留原始值
                output.append(info['full_match'])
            
            current_pos = info['end']
        
        # 添加剩余内容
        output.append(template_content[current_pos:])
        
        return ''.join(output)
    
    def _build_json_file_robust(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        健壮的JSON文件构建，处理各种特殊情况
        """
        # 使用与提取时相同的正则表达式
        from core.data_aggregator import DataAggregator
        agg = DataAggregator(None, [], None)
        
        # 提取模板中所有的键值对位置信息
        key_positions = []
        for match in agg.JSON_KEY_VALUE_PATTERN.finditer(template_content):
            key = match.group(1)
            start, end = match.span()
            key_positions.append((key, start, end))
        
        # 按位置排序
        key_positions.sort(key=lambda x: x[1])
        
        # 处理模板内容，替换已存在的键值对
        current_pos = 0
        output_content = ""
        processed_keys = set()
        
        for key, start, end in key_positions:
            # 添加当前位置到匹配开始位置的内容
            output_content += template_content[current_pos:start]
            
            # 替换为翻译后的值
            if key in translations:
                translated_value = translations[key].replace('"', '\\"')
                # 保持原始键的格式，只替换值
                output_content += f'"{key}":"{translated_value}"'
            else:
                # 如果没有翻译，保持原始值
                output_content += template_content[start:end]
            
            processed_keys.add(key)
            current_pos = end
        
        # 添加剩余内容
        output_content += template_content[current_pos:]
        
        # 处理没有出现在模板中的键值对
        # 查找JSON对象的结束位置
        end_brace_pos = output_content.rfind('}')
        if end_brace_pos != -1:
            # 收集所有未处理的键值对
            unprocessed_pairs = []
            for key, value in translations.items():
                if key not in processed_keys:
                    escaped_value = value.replace('"', '\\"')
                    unprocessed_pairs.append(f'    "{key}":"{escaped_value}"')
            
            if unprocessed_pairs:
                # 在结束括号前添加未处理的键值对
                prefix = output_content[:end_brace_pos]
                suffix = output_content[end_brace_pos:]
                
                # 检查前缀末尾是否有逗号
                if not prefix.strip().endswith(',') and len(key_positions) > 0:
                    prefix += ','
                
                # 添加未处理的键值对
                output_content = f'{prefix}\n' + ',\n'.join(unprocessed_pairs) + f'\n{suffix}'
        
        return output_content
    
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
        """
        兼容旧版 PackBuilder 的接口（薄封装）。

        统一委托给 `core/builder.py`，避免资源包构建出现多套实现。
        """
        logging.info("--- 开始资源包构建流程（委托实现） ---")

        from .builder import Builder
        from .models import TranslationResult, ExtractionResult, LanguageEntry, NamespaceInfo, PackSettings

        output_dir = Path(output_dir)

        # 1) 构建 ExtractionResult（只需要 raw_english_files + namespace_info）
        extraction_result = ExtractionResult()
        extraction_result.raw_english_files = raw_english_files or {}

        all_namespaces = set((final_translations_lookup_by_ns or {}).keys()) | set((namespace_formats or {}).keys())
        for ns in all_namespaces:
            extraction_result.namespace_info[ns] = NamespaceInfo(
                name=ns,
                jar_name="Unknown",
                file_format=(namespace_formats or {}).get(ns, "json"),
                raw_content=(raw_english_files or {}).get(ns, ""),
            )

        # 2) 构建 TranslationResult（仅用于提供每个 ns 的 zh 值）
        translation_result = TranslationResult()
        for ns, translations in (final_translations_lookup_by_ns or {}).items():
            translation_result.workbench_data[ns] = {}
            for key, zh_value in (translations or {}).items():
                zh_text = zh_value if isinstance(zh_value, str) else str(zh_value)
                translation_result.workbench_data[ns][key] = LanguageEntry(
                    key=key,
                    en="",
                    zh=zh_text,
                    source="待翻译",
                    namespace=ns,
                )

        # 3) 构建 PackSettings
        builder_pack_settings = PackSettings(
            pack_as_zip=pack_settings.get("pack_as_zip", False),
            pack_description=pack_settings.get("pack_description", "A Modpack Localization Pack"),
            pack_base_name=pack_settings.get("pack_base_name", "Generated_Pack"),
            pack_format=pack_settings.get("pack_format", 7),
            pack_icon_path=pack_settings.get("pack_icon_path", ""),
        )

        builder = Builder()
        return builder.run(
            output_dir=output_dir,
            translation_result=translation_result,
            extraction_result=extraction_result,
            pack_settings=builder_pack_settings,
        )