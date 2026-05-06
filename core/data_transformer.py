"""数据转换工具：将核心数据结构转换为工作台可用的格式。"""

from __future__ import annotations
import logging
from core.models import ExtractionResult, TranslationResult, LanguageEntry


def build_name_lookup(name_list: list[dict]) -> dict[str, dict]:
    """构建名称查找表，以 jar 文件名为键。"""
    lookup: dict[str, dict] = {}
    for entry in name_list:
        source = entry['source']
        jar_name = source[:-4] if source.endswith('.jar') else source
        lookup[jar_name.lower()] = entry
    return lookup


def resolve_mod_metadata(
    ns: str,
    extraction_result: ExtractionResult,
    module_names_lookup: dict[str, dict],
    curseforge_lookup: dict[str, dict],
    modrinth_lookup: dict[str, dict],
) -> dict[str, str]:
    """解析命名空间对应的模组元数据。"""
    jar_name_info = extraction_result.namespace_info.get(ns)
    jar_name = jar_name_info.jar_name if jar_name_info else 'Unknown'

    jar_name_without_ext = jar_name
    if " (both formats)" in jar_name_without_ext:
        jar_name_without_ext = jar_name_without_ext.replace(" (both formats)", "")
    if jar_name_without_ext.endswith('.jar'):
        jar_name_without_ext = jar_name_without_ext[:-4]

    curseforge_entry = curseforge_lookup.get(jar_name_without_ext.lower())
    modrinth_entry = modrinth_lookup.get(jar_name_without_ext.lower())

    mod_name = ""
    curseforge_name = ""
    modrinth_name = ""
    git_name = ""
    game_version = ""
    loaders = ""

    if curseforge_entry:
        curseforge_name = curseforge_entry.get('curseforge_name', '')
        if 'slug' in curseforge_entry:
            git_name = curseforge_entry['slug']
        if 'game_version' in curseforge_entry:
            game_version = curseforge_entry['game_version']

    if modrinth_entry:
        modrinth_name = modrinth_entry.get('modrinth_name', '')
        if 'slug' in modrinth_entry:
            git_name = f"modrinth-{modrinth_entry['slug']}"
        if not game_version and 'game_version' in modrinth_entry:
            game_version = modrinth_entry['game_version']

    if not mod_name:
        module_entry = module_names_lookup.get(jar_name_without_ext.lower())
        if module_entry:
            mod_name = module_entry.get('name', '')

    if curseforge_entry and 'loaders' in curseforge_entry:
        loaders = curseforge_entry.get('loaders', "")
    elif modrinth_entry and 'loaders' in modrinth_entry:
        loaders = modrinth_entry.get('loaders', "")

    return {
        'mod_name': mod_name,
        'jar_name': jar_name,
        'curseforge_name': curseforge_name,
        'modrinth_name': modrinth_name,
        'git_name': git_name,
        'game_version': game_version,
        'loaders': loaders,
    }


def build_workbench_data(
    translation_result: TranslationResult,
    extraction_result: ExtractionResult,
    module_names: list[dict],
    curseforge_names: list[dict],
    modrinth_names: list[dict],
) -> dict:
    """将翻译结果转换为工作台可用的数据格式。"""
    module_names_lookup = build_name_lookup(module_names)
    curseforge_lookup = build_name_lookup(curseforge_names)
    modrinth_lookup = build_name_lookup(modrinth_names)

    workbench_data: dict[str, dict] = {}

    for ns, entries in translation_result.workbench_data.items():
        items = []
        for key, entry in entries.items():
            items.append({
                'key': entry.key,
                'en': entry.en,
                'zh': entry.zh,
                'source': entry.source
            })

        metadata = resolve_mod_metadata(
            ns, extraction_result, module_names_lookup, curseforge_lookup, modrinth_lookup
        )

        workbench_data[ns] = {
            **metadata,
            'display_name': ns,
            'items': items
        }

    return workbench_data
