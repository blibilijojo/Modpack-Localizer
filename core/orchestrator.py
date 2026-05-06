from __future__ import annotations
import logging
from pathlib import Path
from datetime import datetime
from core.workflow import Workflow
from core.models import PackSettings, ExtractionResult, NamespaceInfo, TranslationResult, LanguageEntry, TranslationSource
from core.exceptions import ConfigurationError, ExtractionError, TranslationError, BuildError

DEFAULT_NAME_TEMPLATE = "汉化资源包_{timestamp}"
DEFAULT_DESC_TEMPLATE = (
    "整合包汉化数据分析 (共 {total} 条):\n"
    "▷ AI 翻译贡献: {ai_count} 条 ({ai_percent})\n"
    "▷ 人工及社区贡献: {human_count} 条 ({human_percent})"
)

class Orchestrator:
    def __init__(self, settings, update_progress, log_callback=None, save_data=None, project_path=None,
                 show_error_callback=None, launch_workbench_callback=None):
        self.settings = settings
        self.update_progress = update_progress
        self.log = log_callback or (lambda msg, lvl: logging.info(f"[{lvl}] {msg}"))
        self.save_data = save_data
        self.project_path = project_path
        self.show_error = show_error_callback or (lambda title, msg: logging.error(f"{title}: {msg}"))
        self.launch_workbench = launch_workbench_callback or (lambda data: None)
        self.final_translations = None
        self.final_workbench_data = None
        self.raw_english_files: dict[str, str] = {}
        self.namespace_formats: dict[str, str] = {}
        self.module_names: list[dict] = []
        self.curseforge_names: list[dict] = []
        self.modrinth_names: list[dict] = []
        self.project_name = 'Unnamed_Project'
        self.workflow = Workflow()

    @staticmethod
    def _build_name_lookup(name_list: list[dict]) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        for entry in name_list:
            source = entry['source']
            jar_name = source[:-4] if source.endswith('.jar') else source
            lookup[jar_name.lower()] = entry
        return lookup

    @staticmethod
    def _resolve_mod_metadata(
        ns: str,
        extraction_result: ExtractionResult,
        module_names_lookup: dict[str, dict],
        curseforge_lookup: dict[str, dict],
        modrinth_lookup: dict[str, dict],
    ) -> dict[str, str]:
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

    def _build_workbench_data(
        self,
        translation_result: TranslationResult,
        extraction_result: ExtractionResult,
    ) -> dict:
        module_names_lookup = self._build_name_lookup(self.module_names)
        curseforge_lookup = self._build_name_lookup(self.curseforge_names)
        modrinth_lookup = self._build_name_lookup(self.modrinth_names)

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

            metadata = self._resolve_mod_metadata(
                ns, extraction_result, module_names_lookup, curseforge_lookup, modrinth_lookup
            )

            workbench_data[ns] = {
                **metadata,
                'display_name': ns,
                'items': items
            }

        return workbench_data

    def _handle_error(self, error: Exception, title: str, message: str):
        logging.error(f"{title}：{error}", exc_info=True)
        self.show_error(title, message)
        self.update_progress(f"错误：{error}", -1)

    def _validate_translation_config(self):
        if not self.settings.get('mods_dir'):
            raise ConfigurationError("未配置Mods目录，请先在设置中配置")
        mods_path = Path(self.settings['mods_dir'])
        if not mods_path.exists() or not mods_path.is_dir():
            raise ConfigurationError(f"配置的Mods目录不存在或不是目录: {mods_path}")

    def _create_extraction_progress_callback(self):
        def extraction_progress(phase: str, cur: int, total: int):
            if total <= 0:
                return
            r = min(max(cur / total, 0.0), 1.0)
            if phase == "scan_lang":
                self.update_progress(f"扫描语言文件… ({cur}/{total})", 10 + r * 28)
            elif phase == "fingerprint":
                self.update_progress(f"计算模组指纹… ({cur}/{total})", 38 + r * 10)
            elif phase == "repo_metadata":
                if cur == 0:
                    self.update_progress("正在查询CurseForge平台...", 48)
                elif cur == 1:
                    self.update_progress("正在查询Modrinth平台...", 49)
                else:
                    self.update_progress("平台查询完成", 50)
        return extraction_progress

    def _create_workflow_context(self, extraction_progress):
        context = self.workflow.create_context(
            settings=self.settings,
            progress_callback=lambda msg, p: self.update_progress(msg, 50 + p // 2),
            extraction_progress=extraction_progress,
        )
        if hasattr(self, 'stop_event'):
            context.stop_event = self.stop_event
        return context

    def _run_data_extraction(self, context):
        try:
            extraction_result = self.workflow.run_extraction(context)
            self.module_names = extraction_result.module_names
            self.curseforge_names = getattr(extraction_result, 'curseforge_names', [])
            self.modrinth_names = getattr(extraction_result, 'modrinth_names', [])
            return extraction_result
        except KeyboardInterrupt:
            logging.info("用户取消了操作")
            self.update_progress("操作已取消", -2)
            return None
        except Exception as agg_error:
            logging.error(f"数据提取失败: {agg_error}", exc_info=True)
            raise ExtractionError(f"数据提取失败: {agg_error}")

    def _validate_extraction_result(self, extraction_result):
        master_english_count = len(extraction_result.master_english)
        self.log(f"数据提取完成，共发现 {master_english_count} 个命名空间", "INFO")
        if master_english_count == 0:
            raise ExtractionError("未从模组中提取到任何英文语言文件。请确保下载的模组包含 lang/en_us.lang 或 lang/en_us.json 文件。")
        self.update_progress("数据聚合完成", 50)
        self.raw_english_files = extraction_result.raw_english_files
        self.namespace_formats = {
            ns: info.file_format
            for ns, info in extraction_result.namespace_info.items()
        }

    def _run_translation_decision(self, context):
        try:
            return self.workflow.run_translation(context)
        except KeyboardInterrupt:
            logging.info("用户取消了操作")
            self.update_progress("操作已取消", -2)
            return None
        except Exception as dec_error:
            logging.error(f"翻译决策失败: {dec_error}", exc_info=True)
            raise TranslationError(f"翻译决策失败: {dec_error}")

    def _validate_translation_result(self, translation_result):
        workbench_data_count = len(translation_result.workbench_data)
        logging.info(f"翻译决策完成，共生成 {workbench_data_count} 个命名空间的翻译数据")
        if not translation_result.workbench_data:
            raise TranslationError("翻译决策未生成任何数据。可能是因为模组中的语言文件格式不正确或无法解析。")
        self.update_progress("翻译决策完成", 100)

    def _prepare_and_launch_workbench(self, translation_result, extraction_result):
        workbench_data = self._build_workbench_data(translation_result, extraction_result)
        self.update_progress("决策完成，准备打开工作台", 90)
        self.log("阶段 3/3: 启动翻译工作台...", "INFO")
        self.launch_workbench(workbench_data)

    def run_translation_phase(self):
        try:
            self.log("阶段 1/3: 开始聚合语言数据...", "INFO")
            self.update_progress("正在聚合数据...", 10)
            self._validate_translation_config()

            extraction_progress = self._create_extraction_progress_callback()
            context = self._create_workflow_context(extraction_progress)

            extraction_result = self._run_data_extraction(context)
            if extraction_result is None:
                return
            self._validate_extraction_result(extraction_result)

            self.log("阶段 2/3: 执行翻译决策...", "INFO")
            self.update_progress("正在应用翻译规则...", 60)

            translation_result = self._run_translation_decision(context)
            if translation_result is None:
                return
            self._validate_translation_result(translation_result)

            self._prepare_and_launch_workbench(translation_result, extraction_result)
        except ValueError as ve:
            self._handle_error(ve, "配置错误", f"请检查配置后重试:\n{ve}")
        except ConfigurationError as ce:
            self._handle_error(ce, "配置错误", f"请检查配置后重试:\n{ce}")
        except ExtractionError as ee:
            self._handle_error(ee, "数据提取失败", f"{ee}")
        except TranslationError as te:
            self._handle_error(te, "翻译决策失败", f"{te}")
        except KeyboardInterrupt:
            logging.info("用户取消了操作")
            self.update_progress("操作已取消", -2)
        except Exception as e:
            self._handle_error(e, "处理失败", f"在处理文件时发生错误:\n{e}\n请查看日志获取更多详细信息。")

    def _generate_pack_metadata_values(self) -> dict:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not self.final_workbench_data:
            return {"timestamp": timestamp, "total": 0, "ai_count": 0, "ai_percent": "0.0%", "human_count": 0, "human_percent": "0.0%"}

        ai_count = 0
        human_count = 0
        total_translated = 0
        ai_sources = {TranslationSource.AI_TRANSLATION}

        for ns_data in self.final_workbench_data.values():
            for item in ns_data.get('items', []):
                if item.get('zh', '').strip():
                    total_translated += 1
                    source = item.get('source', '')
                    if source in ai_sources:
                        ai_count += 1
                    else:
                        human_count += 1

        ai_percent = (ai_count / total_translated * 100) if total_translated > 0 else 0
        human_percent = (human_count / total_translated * 100) if total_translated > 0 else 0

        logging.info("--- 最终资源包元数据统计 ---")
        logging.info(f"总翻译条目: {total_translated}")
        logging.info(f"  ▷ AI 翻译贡献: {ai_count} 条 ({ai_percent:.1f}%)")
        logging.info(f"  ▷ 人工及社区贡献: {human_count} 条 ({human_percent:.1f}%)")
        logging.info("-------------------------------")

        return {
            "timestamp": timestamp,
            "total": total_translated,
            "ai_count": ai_count,
            "ai_percent": f"{ai_percent:.1f}%",
            "human_count": human_count,
            "human_percent": f"{human_percent:.1f}%"
        }

    @staticmethod
    def _replace_placeholders(template_str: str, data: dict) -> str:
        for key, value in data.items():
            template_str = template_str.replace(f"{{{key}}}", str(value))
        return template_str

    def run_build_phase(self, pack_settings: dict):
        try:
            if self.final_translations is None:
                raise BuildError("没有可用于构建的翻译数据。请先完成翻译阶段。")
            self.log("开始生成资源包...", "INFO")
            self.update_progress("正在构建资源包...", 10)

            metadata_values = self._generate_pack_metadata_values()
            user_preset_name = pack_settings.get('preset_name', '')
            user_description = pack_settings.get('pack_description', '')
            desc_template = user_description.strip() or DEFAULT_DESC_TEMPLATE
            final_description = self._replace_placeholders(desc_template, metadata_values)

            name_template = ""
            if user_preset_name.strip() and user_preset_name != "默认预案":
                name_template = user_preset_name
            else:
                name_template = DEFAULT_NAME_TEMPLATE
            final_name = self._replace_placeholders(name_template, metadata_values)

            pack_settings['pack_description'] = final_description
            pack_settings['pack_base_name'] = final_name

            builder_pack_settings = PackSettings(
                pack_as_zip=pack_settings.get('pack_as_zip', False),
                pack_description=final_description,
                pack_base_name=final_name,
                pack_format=pack_settings.get('pack_format', 7),
                pack_icon_path=pack_settings.get('pack_icon_path', '')
            )

            context = self.workflow.create_context(settings=self.settings)
            if hasattr(self, 'stop_event'):
                context.stop_event = self.stop_event

            extraction_result = ExtractionResult()
            extraction_result.raw_english_files = self.raw_english_files
            for ns, fmt in self.namespace_formats.items():
                extraction_result.namespace_info[ns] = NamespaceInfo(
                    name=ns,
                    file_format=fmt,
                    raw_content=self.raw_english_files.get(ns, '')
                )

            translation_result = TranslationResult()
            for ns, ns_data in self.final_workbench_data.items():
                translation_result.workbench_data[ns] = {}
                for item in ns_data.get('items', []):
                    entry = LanguageEntry(
                        key=item['key'],
                        en=item['en'],
                        zh=item.get('zh', ''),
                        source=item.get('source', TranslationSource.PENDING),
                        namespace=ns
                    )
                    translation_result.workbench_data[ns][item['key']] = entry

            success, message = self.workflow.builder.run(
                output_dir=Path(self.settings['output_dir']),
                translation_result=translation_result,
                extraction_result=extraction_result,
                pack_settings=builder_pack_settings
            )
            if success:
                self.log(f"资源包生成成功！", "SUCCESS")
                self.update_progress("资源包生成成功！", 99)
            else:
                raise BuildError(message)
        except KeyboardInterrupt:
            logging.info("用户取消了操作")
            self.update_progress("操作已取消", -2)
        except Exception as e:
            logging.error(f"构建资源包阶段失败: {e}", exc_info=True)
            self.show_error("构建失败", f"构建资源包时发生错误:\n{e}")
            self.update_progress(f"错误: {e}", -1)

    def run_workflow(self):
        try:
            if not self.save_data:
                self.log("项目数据未加载，无法直接运行完整工作流。", "ERROR")
                self.update_progress("错误：项目数据未加载", -1)
                return
            self.log("从存档文件加载数据并启动工作台...", "INFO")
            self.update_progress("正在加载项目...", 10)
            self.raw_english_files = self.save_data.get('raw_english_files', {})
            self.namespace_formats = self.save_data.get('namespace_formats', {})
            self.module_names = self.save_data.get('module_names', [])
            self.curseforge_names = self.save_data.get('curseforge_names', [])
            self.modrinth_names = self.save_data.get('modrinth_names', [])
            self.project_name = self.save_data.get('project_name', 'Unnamed_Project')
            workbench_data = self.save_data.get('workbench_data', {})

            if not all([self.raw_english_files, self.namespace_formats, workbench_data]):
                self.log("存档文件不完整，缺少核心数据。", "ERROR")
                self.update_progress("错误：存档文件不完整", -1)
                return

            self.launch_workbench(workbench_data)
        except KeyboardInterrupt:
            logging.info("用户取消了操作")
            self.update_progress("操作已取消", -2)
