import logging
import re
from pathlib import Path
from typing import Dict, Optional
import tempfile
import shutil
import zipfile
import os
import json

from .models import (
    TranslationResult, ExtractionResult, NamespaceInfo,
    PackSettings
)

class Builder:
    """资源包构建器"""
    
    def __init__(self):
        # 保持原有正则表达式规则不变
        self.JSON_KEY_VALUE_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
        self.LANG_KV_PATTERN = re.compile(r"^\s*([^#=\s]+)\s*=\s*(.*)", re.MULTILINE)
    
    def _build_json_file(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        基于正则表达式的JSON语言文件逆向生成
        """
        # 提取模板中的所有键值对信息
        key_info = []
        for match in self.JSON_KEY_VALUE_PATTERN.finditer(template_content):
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
                translated_value = translations[info['key']]
                # 保持原始键的格式，只替换值
                output.append(f'"{info["key"]}":"{translated_value}"')
            else:
                # 保留原始值
                output.append(info['full_match'])
            
            current_pos = info['end']
        
        # 添加剩余内容
        output.append(template_content[current_pos:])
        
        # 确保返回的字符串只使用\n换行符
        result = ''.join(output)
        return result.replace('\r\n', '\n').replace('\r', '\n')
    
    def _build_lang_file(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        基于正则表达式的lang语言文件逆向生成
        """
        # 提取模板中的所有键值对信息
        key_info = []
        for match in self.LANG_KV_PATTERN.finditer(template_content):
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
        
        # 确保返回的字符串只使用\n换行符
        result = ''.join(output)
        return result.replace('\r\n', '\n').replace('\r', '\n')
    
    def _build_json_file_robust(self, template_content: str, translations: Dict[str, str]) -> str:
        """
        健壮的JSON文件构建，处理各种特殊情况
        """
        # 提取模板中所有的键值对位置信息
        key_positions = []
        for match in self.JSON_KEY_VALUE_PATTERN.finditer(template_content):
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
                translated_value = translations[key]
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
                    unprocessed_pairs.append(f'    "{key}":"{value}"')
            
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
        """清理文件名"""
        first_line = text.splitlines()[0] if text else ""
        if not first_line.strip():
            return "GeneratedPack"
        return re.sub(r'[\\/*?:"<>|]', "", first_line).strip()
    
    def _get_unique_path(self, target_path: Path) -> Path:
        """获取唯一路径"""
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
    
    def run(
        self, 
        output_dir: Path, 
        translation_result: TranslationResult,
        extraction_result: ExtractionResult,
        pack_settings: PackSettings
    ) -> tuple[bool, str]:
        """
        执行资源包构建流程
        """
        logging.info(f"=== 阶段 3: 开始资源包构建流程 (正则替换模式) ===")
        
        pack_as_zip = pack_settings.pack_as_zip
        pack_description = pack_settings.pack_description
        base_name_raw = pack_settings.pack_base_name
        base_name = self._sanitize_filename(base_name_raw)
        
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            logging.debug(f"在临时目录中构建资源包内容: {temp_dir}")
            
            # 准备翻译数据，转换为适合构建的格式
            final_translations_lookup_by_ns = {}
            for namespace, entries in translation_result.workbench_data.items():
                ns_translations = {}
                for key, entry in entries.items():
                    if entry.zh and entry.zh.strip():
                        ns_translations[key] = entry.zh
                final_translations_lookup_by_ns[namespace] = ns_translations
            
            # 构建每个命名空间的语言文件
            for namespace, translations in final_translations_lookup_by_ns.items():
                template_content = extraction_result.raw_english_files.get(namespace, '{}')
                
                try:
                    # Extract base namespace and format from the namespace string (e.g., "modid:lang" -> base="modid", format="lang")
                    if ":" in namespace:
                        base_namespace, file_format = namespace.split(":", 1)
                    else:
                        base_namespace = namespace
                        # Get file format from namespace info
                        namespace_info = extraction_result.namespace_info.get(namespace, NamespaceInfo(name=namespace))
                        file_format = namespace_info.file_format
                    
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
            
            # 写入pack.mcmeta文件
            try:
                pack_mcmeta_data = {
                    "pack": {
                        "pack_format": pack_settings.pack_format,
                        "description": pack_description
                    }
                }
                (temp_dir / "pack.mcmeta").write_text(
                    json.dumps(pack_mcmeta_data, indent=4, ensure_ascii=False),
                    encoding='utf-8'
                )
                
                # 复制图标文件
                if pack_settings.pack_icon_path and Path(pack_settings.pack_icon_path).is_file():
                    shutil.copy(pack_settings.pack_icon_path, temp_dir / "pack.png")
            except Exception as e:
                logging.error(f"写入元数据时出错: {e}", exc_info=True)
                return False, f"写入元数据时出错: {e}"
            
            # 生成最终资源包
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
            except Exception as e:
                logging.error(f"完成最终资源包时出错: {e}", exc_info=True)
                return False, f"完成最终资源包时出错: {e}"
        
        logging.info("=== 资源包构建成功完成 ===")
        return True, f"资源包构建成功！输出位置: {final_output_path}"
