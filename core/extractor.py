from __future__ import annotations
import zipfile
import logging
import hashlib
import threading
import os
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import file_utils, config_manager, mod_scan_cache
from core.models import (
    LanguageEntry, NamespaceInfo, ExtractionResult, ZipFileResult,
    JSON_KEY_VALUE_PATTERN, LANG_KV_PATTERN
)
from core.mod_fingerprint import jar_mod_fingerprints_and_meta
from core.mod_repository import ModrinthClient, CurseForgeClient
from core.constants import EXTRACTOR_SCAN_MAX_WORKERS, EXTRACTOR_FINGERPRINT_MAX_WORKERS, JAR_READ_CHUNK_SIZE
from utils.file_utils import decode_json_value_with_unicode


class Extractor:

    def __init__(self):
        self._modrinth_client = ModrinthClient()
        self._curseforge_client = CurseForgeClient()

    def _extract_from_text(self, content: str, file_format: str, file_path_for_log: str) -> dict[str, str]:
        data: dict[str, str] = {}
        comment_counter = 0
        if file_format == 'json':
            for match in JSON_KEY_VALUE_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2)
                temp_value = decode_json_value_with_unicode(value)
                if key == '_comment':
                    comment_counter += 1
                    data[f'_comment_{comment_counter}'] = temp_value
                else:
                    data[key] = temp_value
        elif file_format == 'lang':
            for match in LANG_KV_PATTERN.finditer(content):
                key = match.group(1)
                value = match.group(2).strip()
                if key == '_comment':
                    comment_counter += 1
                    data[f'_comment_{comment_counter}'] = value
                else:
                    data[key] = value
        return data

    def _get_namespace_from_path(self, path_str: str) -> str:
        parts = Path(path_str).parts
        if 'assets' in parts:
            try:
                return parts[parts.index('assets') + 1]
            except (ValueError, IndexError):
                pass
        return 'minecraft'

    def _process_zip_file(self, zf: zipfile.ZipFile, file_info: zipfile.ZipInfo, source_zip_name: str) -> ZipFileResult:
        path_str_lower = file_info.filename.lower()
        is_english = 'lang/en_us' in path_str_lower
        is_chinese = 'lang/zh_cn' in path_str_lower

        if not (is_english or is_chinese):
            return ZipFileResult.empty()

        base_namespace = self._get_namespace_from_path(file_info.filename)
        file_format = 'lang' if path_str_lower.endswith('.lang') else 'json'

        namespace = base_namespace
        log_path = f"{source_zip_name} -> {file_info.filename}"

        try:
            with zf.open(file_info) as f:
                content = f.read().decode('utf-8-sig')
        except UnicodeDecodeError as e:
            logging.warning(f"文件编码不是UTF-8，跳过处理: {log_path} - {e}")
            return ZipFileResult.empty()
        except Exception as e:
            logging.warning(f"读取zip内文件失败: {log_path} - {e}")
            return ZipFileResult.empty()

        extracted_data = self._extract_from_text(content, file_format, log_path)

        return ZipFileResult(
            namespace=namespace,
            file_format=file_format,
            content=content,
            extracted_data=extracted_data,
            is_english=is_english,
            is_chinese=is_chinese,
        )

    def extract_from_mods(self, mods_dir: Path, extraction_progress_callback=None, stop_event=None) -> ExtractionResult:
        logging.debug(f"正在扫描Mods文件夹: {mods_dir}")

        result = ExtractionResult()

        jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar") if mods_dir.exists() else []

        if not jar_files:
            return result

        def _process_one_jar_lang(jar_file: Path) -> tuple[str, list[ZipFileResult]]:
            local_lang_files: list[ZipFileResult] = []
            try:
                with zipfile.ZipFile(jar_file, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang' not in file_info.filename or not file_info.filename.startswith('assets/'):
                            continue
                        result = self._process_zip_file(zf, file_info, jar_file.name)
                        if result.is_valid:
                            local_lang_files.append(result)
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取JAR文件: {jar_file.name} - 错误: {e}")
            return jar_file.name, local_lang_files

        max_workers = min(EXTRACTOR_SCAN_MAX_WORKERS, len(jar_files), max(1, (os.cpu_count() or 1)))
        all_results: list[tuple[str, list[ZipFileResult]]] = []

        if len(jar_files) <= 4:
            for i, jar_file in enumerate(jar_files):
                if extraction_progress_callback:
                    extraction_progress_callback("scan_lang", i + 1, len(jar_files))
                all_results.append(_process_one_jar_lang(jar_file))
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_one_jar_lang, jf): jf for jf in jar_files}
                completed = 0
                for future in as_completed(futures):
                    if stop_event and stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise KeyboardInterrupt("用户取消了操作")
                    completed += 1
                    if extraction_progress_callback:
                        extraction_progress_callback("scan_lang", completed, len(jar_files))
                    try:
                        all_results.append(future.result())
                    except Exception as e:
                        logging.error(f"处理JAR文件时发生错误: {e}")

        formats_by_namespace: dict[str, set[str]] = {}
        for jar_name, language_files in all_results:
            for r in language_files:
                if r.namespace not in formats_by_namespace:
                    formats_by_namespace[r.namespace] = set()
                formats_by_namespace[r.namespace].add(r.file_format)

        for jar_name, language_files in all_results:
            for r in language_files:
                if len(formats_by_namespace[r.namespace]) > 1:
                    final_namespace = f"{r.namespace}:{r.file_format}"
                else:
                    final_namespace = r.namespace

                if final_namespace not in result.namespace_info:
                    jar_name_with_suffix = jar_name + " (both formats)" if len(formats_by_namespace[r.namespace]) > 1 else jar_name
                    result.namespace_info[final_namespace] = NamespaceInfo(
                        name=final_namespace,
                        jar_name=jar_name_with_suffix,
                        file_format=r.file_format
                    )

                if r.file_format == 'json':
                    result.namespace_info[final_namespace].file_format = r.file_format

                if r.is_english:
                    result.raw_english_files[final_namespace] = r.content
                    result.namespace_info[final_namespace].raw_content = r.content
                    for key, value in r.extracted_data.items():
                        result.master_english[final_namespace][key] = LanguageEntry(
                            key=key,
                            en=value,
                            namespace=final_namespace
                        )
                elif r.is_chinese:
                    for key, value in r.extracted_data.items():
                        en_value = result.master_english[final_namespace][key].en if final_namespace in result.master_english and key in result.master_english[final_namespace] else ""
                        result.internal_chinese[final_namespace][key] = LanguageEntry(
                            key=key,
                            en=en_value,
                            zh=value,
                            namespace=final_namespace
                        )

        logging.info(f"扫描完成: {len(jar_files)}个JAR, {len(result.master_english)}个命名空间")
        return result

    def extract_from_packs(self, zip_paths: list[Path], master_english: dict[str, dict[str, LanguageEntry]]) -> dict[str, str]:
        final_pack_chinese_dict: dict[str, str] = {}

        if not zip_paths:
            logging.debug("未提供第三方汉化包，跳过处理。")
            return final_pack_chinese_dict

        logging.info(f"  - 正在读取 {len(zip_paths)} 个第三方汉化包...")

        namespace_map: dict[str, list[str]] = {}
        for full_namespace in master_english.keys():
            if ":" in full_namespace:
                base_namespace = full_namespace.split(":", 1)[0]
            else:
                base_namespace = full_namespace
            if base_namespace not in namespace_map:
                namespace_map[base_namespace] = []
            namespace_map[base_namespace].append(full_namespace)

        for zip_path in reversed(zip_paths):
            if not zip_path.exists() or not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
                logging.warning(f"  - 无效的ZIP文件，已跳过: {zip_path}")
                continue

            current_zip_chinese_dict: dict[str, dict] = defaultdict(dict)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or 'lang/zh_cn' not in file_info.filename.lower() or not file_info.filename.startswith('assets/'):
                            continue

                        r = self._process_zip_file(zf, file_info, zip_path.name)
                        if not r.is_valid:
                            continue

                        for key, zh_value in r.extracted_data.items():
                            if key == '_comment':
                                continue

                            en_value = master_english.get(r.namespace, {}).get(key, None)
                            if en_value and en_value.en != zh_value:
                                final_pack_chinese_dict[key] = zh_value
                            else:
                                if r.namespace in namespace_map:
                                    for full_namespace in namespace_map[r.namespace]:
                                        en_value = master_english.get(full_namespace, {}).get(key, None)
                                        if en_value and en_value.en != zh_value:
                                            final_pack_chinese_dict[key] = zh_value
                                            break
            except (zipfile.BadZipFile, OSError) as e:
                logging.error(f"无法读取汉化包: {zip_path.name} - 错误: {e}")

        logging.info(f"  - {len(zip_paths)} 个第三方汉化包处理完毕，共聚合 {len(final_pack_chinese_dict)} 条有效汉化。")
        return final_pack_chinese_dict

    def _collect_mod_fingerprints(
        self,
        jars_to_process: list[Path],
        fingerprint_cache: mod_scan_cache.ModFingerprintDiskCache,
        extraction_progress_callback,
        stop_event,
    ) -> tuple[list[tuple], int, dict[str, dict], list[str], list[str], dict[str, str]]:
        mod_info_by_jar: dict[str, dict] = {}
        curseforge_hashes: list[str] = []
        modrinth_hashes: list[str] = []
        hash_to_jar: dict[str, str] = {}
        cache_hits = 0
        data_lock = threading.Lock()  # 保护所有共享数据结构
        completed = 0
        total_jars = len(jars_to_process)

        def _register_jar_mod_info(
            jar_path: Path,
            jar_name: str,
            curseforge_hash: str,
            modrinth_hash: str,
        ) -> None:
            nonlocal completed
            with data_lock:
                mod_info_by_jar[jar_name] = {
                    'curseforge_hash': curseforge_hash,
                    'modrinth_hash': modrinth_hash,
                }
                if curseforge_hash:
                    curseforge_hashes.append(curseforge_hash)
                    hash_to_jar[curseforge_hash] = jar_name
                if modrinth_hash:
                    modrinth_hashes.append(modrinth_hash)
                    hash_to_jar[modrinth_hash] = jar_name
                completed += 1
                c = completed
            if extraction_progress_callback:
                extraction_progress_callback("fingerprint", c, total_jars)
            if c % 10 == 0 or c == total_jars:
                logging.info(f"模组指纹进度 {c}/{total_jars}")

        def _process_one_jar(jf: Path):
            try:
                # 流式计算 SHA1，避免大文件一次性读入内存
                sha1 = hashlib.sha1()
                with open(jf, 'rb') as f:
                    while True:
                        chunk = f.read(JAR_READ_CHUNK_SIZE)
                        if not chunk:
                            break
                        sha1.update(chunk)
                data = None  # 不保留完整数据
            except OSError as e:
                logging.warning("无法读取 JAR: %s — %s", jf, e)
                return None
            modrinth_hash = sha1.hexdigest()
            with data_lock:
                rec = fingerprint_cache.get(modrinth_hash)
            if rec is not None:
                return (
                    True,
                    jf,
                    jf.name,
                    rec["curseforge_hash"],
                    rec["modrinth_hash"],
                )
            # 缓存未命中，需要读取完整数据计算 MurmurHash
            try:
                with open(jf, 'rb') as f:
                    data = f.read()
            except OSError as e:
                logging.warning("无法读取 JAR: %s — %s", jf, e)
                return None
            jar_name, curseforge_hash, mr = jar_mod_fingerprints_and_meta(
                jf, data, modrinth_hash
            )
            with data_lock:
                fingerprint_cache.put(modrinth_hash, {
                    'curseforge_hash': curseforge_hash,
                })
            return (False, jf, jar_name, curseforge_hash, mr)

        max_workers = min(EXTRACTOR_FINGERPRINT_MAX_WORKERS, len(jars_to_process), max(1, (os.cpu_count() or 1) * 4))
        logging.debug(
            "模组指纹：%d 个线程；键为整包 SHA1，命中则跳过 MurmurHash 计算",
            max_workers,
        )

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_jar = {executor.submit(_process_one_jar, jf): jf for jf in jars_to_process}
                for future in as_completed(future_to_jar):
                    if stop_event and stop_event.is_set():
                        logging.info("收到停止信号，停止处理...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        fingerprint_cache.save_if_dirty()
                        raise KeyboardInterrupt("用户取消了操作")
                    try:
                        row = future.result()
                        if row is None:
                            continue
                        hit, jf, jar_name, cf_h, mr_h = row
                        if hit:
                            with data_lock:
                                cache_hits += 1
                        _register_jar_mod_info(jf, jar_name, cf_h, mr_h)
                    except Exception as e:
                        logging.error(f"处理JAR文件时发生错误: {e}")
        finally:
            fingerprint_cache.save_if_dirty()

        if jars_to_process:
            logging.info(
                "模组指纹缓存（SHA1）命中 %d / %d；未命中项已解析并写入 %s",
                cache_hits,
                len(jars_to_process),
                mod_scan_cache.cache_path(),
            )

        return (mod_info_by_jar, cache_hits, hash_to_jar, curseforge_hashes, modrinth_hashes, completed)

    def _resolve_mod_names(
        self,
        mod_info_by_jar: dict[str, dict],
        curseforge_hashes: list[str],
        modrinth_hashes: list[str],
        extraction_progress_callback,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        module_names: list[dict[str, str]] = []
        curseforge_names: list[dict[str, str]] = []
        modrinth_names: list[dict[str, str]] = []

        if extraction_progress_callback:
            extraction_progress_callback("repo_metadata", 0, 2)

        curseforge_info = self._curseforge_client.get_mod_info(curseforge_hashes)

        unmatched_modrinth_hashes: list[str] = []
        for jar_name, info in mod_info_by_jar.items():
            if info['curseforge_hash'] not in curseforge_info and info['modrinth_hash']:
                unmatched_modrinth_hashes.append(info['modrinth_hash'])

        modrinth_info: dict[str, dict] = {}
        if unmatched_modrinth_hashes:
            if extraction_progress_callback:
                extraction_progress_callback("repo_metadata", 1, 2)

            logging.info(f"CurseForge未匹配 {len(unmatched_modrinth_hashes)} 个模组，尝试从Modrinth获取...")
            modrinth_info = self._modrinth_client.get_mod_info(unmatched_modrinth_hashes)
        else:
            logging.info("所有模组已通过CurseForge匹配，无需调用Modrinth")

        if extraction_progress_callback:
            extraction_progress_callback("repo_metadata", 2, 2)

        for jar_name, info in mod_info_by_jar.items():
            mod_name = Path(jar_name).stem
            game_version = ''
            source = 'JAR'

            if info['curseforge_hash'] in curseforge_info:
                cf_info = curseforge_info[info['curseforge_hash']]
                mod_name = cf_info.get('name', mod_name)
                if cf_info.get('game_version'):
                    game_version = cf_info.get('game_version', '')
                    source = 'CurseForge'

            if not game_version and info['modrinth_hash'] in modrinth_info:
                mr_info = modrinth_info[info['modrinth_hash']]
                mod_name = mr_info.get('name', mod_name)
                if mr_info.get('game_version'):
                    game_version = mr_info.get('game_version', '')
                    source = 'Modrinth'

            loaders_info = ""
            if source == 'CurseForge' and info['curseforge_hash'] in curseforge_info:
                loaders_info = curseforge_info[info['curseforge_hash']].get('loaders', "")
            elif info['modrinth_hash'] in modrinth_info:
                loaders_info = modrinth_info[info['modrinth_hash']].get('loaders', "")

            logging.info(f"模组: {mod_name}, 版本: {game_version}, 加载器: {loaders_info}, 来源: {source}")

            module_names.append({
                'name': mod_name,
                'source': jar_name,
                'game_version': game_version
            })

            if info['curseforge_hash']:
                curseforge_entry: dict[str, str] = {
                    'curseforge_name': info['curseforge_hash'],
                    'source': jar_name,
                    'game_version': game_version,
                    'loaders': ""
                }
                if info['curseforge_hash'] in curseforge_info:
                    curseforge_entry['name'] = curseforge_info[info['curseforge_hash']].get('name')
                    curseforge_entry['slug'] = curseforge_info[info['curseforge_hash']].get('slug')
                    curseforge_entry['url'] = curseforge_info[info['curseforge_hash']].get('url')
                    curseforge_entry['loaders'] = curseforge_info[info['curseforge_hash']].get('loaders', "")
                curseforge_names.append(curseforge_entry)

            if info['modrinth_hash']:
                modrinth_entry: dict[str, str] = {
                    'modrinth_name': info['modrinth_hash'],
                    'source': jar_name,
                    'game_version': game_version,
                    'loaders': ""
                }
                if info['modrinth_hash'] in modrinth_info:
                    modrinth_entry['name'] = modrinth_info[info['modrinth_hash']].get('name')
                    modrinth_entry['slug'] = modrinth_info[info['modrinth_hash']].get('slug')
                    modrinth_entry['url'] = modrinth_info[info['modrinth_hash']].get('url')
                    modrinth_entry['loaders'] = modrinth_info[info['modrinth_hash']].get('loaders', "")
                modrinth_names.append(modrinth_entry)

        return module_names, curseforge_names, modrinth_names

    def run(self, mods_dir: Path, zip_paths: list[Path], community_dict_dir: str, extraction_progress_callback=None, stop_event=None) -> ExtractionResult:
        logging.info("语言数据聚合开始")

        result = self.extract_from_mods(mods_dir, extraction_progress_callback, stop_event)

        result.pack_chinese = self.extract_from_packs(zip_paths, result.master_english)

        logging.debug("开始提取模组信息...")

        jars_with_language_files: set[str] = set()
        for ns_info in result.namespace_info.values():
            jar_name = ns_info.jar_name
            if " (both formats)" in jar_name:
                jar_name = jar_name.replace(" (both formats)", "")
            jars_with_language_files.add(jar_name)

        logging.debug(f"发现 {len(jars_with_language_files)} 个含语言文件的模组")

        if mods_dir.exists():
            jar_files = file_utils.find_files_in_dir(mods_dir, "*.jar")

            jars_to_process = [
                jar_file for jar_file in jar_files
                if jar_file.name in jars_with_language_files
            ]

            fingerprint_cache = mod_scan_cache.ModFingerprintDiskCache()
            fingerprint_cache.load()

            mod_info_by_jar, cache_hits, hash_to_jar, curseforge_hashes, modrinth_hashes, _ = \
                self._collect_mod_fingerprints(jars_to_process, fingerprint_cache, extraction_progress_callback, stop_event)

            module_names, curseforge_names, modrinth_names = \
                self._resolve_mod_names(mod_info_by_jar, curseforge_hashes, modrinth_hashes, extraction_progress_callback)

            result.module_names = module_names
            result.curseforge_names = curseforge_names
            result.modrinth_names = modrinth_names

        total_en = sum(len(d) for d in result.master_english.values())
        total_zh_internal = sum(len(d) for d in result.internal_chinese.values())

        logging.info(f"数据聚合完成: {len(result.master_english)}个命名空间, {total_en}条英文, {total_zh_internal}条自带中文, {len(result.module_names)}个模组")

        return result
