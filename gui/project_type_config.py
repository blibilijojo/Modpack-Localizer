from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PathField:
    label: str
    var_attr: str
    config_key: str
    required: bool = True
    browse_mode: str = "directory"
    filetypes: tuple = ()


@dataclass
class ProjectTypeConfig:
    type_id: str
    display_name: str
    description: str
    setup_title: str
    setup_tab_title: str
    finish_button_text: str
    output_mode: str = "resource_pack"
    path_fields: list[PathField] = field(default_factory=list)
    project_name_source: str = "source_dir_name"
    project_name_fixed: str = ""
    project_info_keys: list[str] = field(default_factory=list)
    setup_log_message: str = ""
    finish_log_message: str = ""
    finish_progress_message: str = ""
    validation_error_title: str = "路径不能为空"
    validation_error_message: str = ""
    enable_github_upload: bool = True
    enable_translation_console: bool = True
    enable_export_json: bool = True
    enable_export_lang: bool = True
    enable_import_json: bool = True
    enable_save_project: bool = True
    enable_find_replace: bool = True
    enable_dictionary_search: bool = True
    enable_add_to_dictionary: bool = True
    enable_ai_translation: bool = True
    enable_batch_operations: bool = True
    enable_undo_redo: bool = True
    custom_features: dict = field(default_factory=dict)
    hidden: bool = False


PROJECT_TYPE_REGISTRY: dict[str, ProjectTypeConfig] = {}


def register_project_type(config: ProjectTypeConfig):
    PROJECT_TYPE_REGISTRY[config.type_id] = config


def get_project_type_config(type_id: str) -> ProjectTypeConfig:
    if type_id in PROJECT_TYPE_REGISTRY:
        return PROJECT_TYPE_REGISTRY[type_id]
    return PROJECT_TYPE_REGISTRY.get("mod", _DEFAULT_CONFIG)


_DEFAULT_CONFIG = ProjectTypeConfig(
    type_id="mod",
    display_name="模组汉化",
    description="推荐流程。扫描Mods文件夹，生成标准汉化资源包。",
    setup_title="配置模组汉化项目",
    setup_tab_title="模组汉化设置",
    finish_button_text="完成并生成资源包",
    output_mode="resource_pack",
    path_fields=[
        PathField("Mods 文件夹:", "mods_dir_var", "mods_dir"),
        PathField("输出文件夹:", "output_dir_var", "output_dir"),
    ],
    project_name_source="source_dir_parent",
    project_info_keys=["mods_dir", "output_dir"],
    setup_log_message="模组汉化项目已配置，开始执行...",
    finish_log_message="翻译工作台已关闭，数据已准备好生成资源包。",
    finish_progress_message="翻译处理完成，现在可以生成资源包",
    validation_error_message="请同时指定 Mods 文件夹和输出文件夹。",
    enable_github_upload=True,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=True,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
)

register_project_type(_DEFAULT_CONFIG)

register_project_type(ProjectTypeConfig(
    type_id="modsearch",
    display_name="模组搜索",
    description="从Modrinth和CurseForge平台搜索模组，自动下载并启动汉化流程。",
    setup_title="配置模组搜索项目",
    setup_tab_title="模组搜索设置",
    finish_button_text="完成并生成资源包",
    output_mode="resource_pack",
    path_fields=[
        PathField("汉化包输出:", "output_dir_var", "output_dir"),
        PathField("JAR 下载:", "jar_dir_var", "jar_dir"),
    ],
    project_name_source="fixed",
    project_name_fixed="模组搜索",
    project_info_keys=["output_dir", "jar_dir"],
    setup_log_message="模组搜索项目已配置，开始搜索界面...",
    finish_log_message="翻译工作台已关闭，数据已准备好生成资源包。",
    finish_progress_message="翻译处理完成，现在可以生成资源包",
    validation_error_message="请指定汉化包输出文件夹和JAR下载文件夹。",
    enable_github_upload=True,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=True,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
))

register_project_type(ProjectTypeConfig(
    type_id="quest",
    display_name="任务汉化",
    description="特定流程。处理FTB Quests或BQM任务文件。",
    setup_title="配置任务汉化项目",
    setup_tab_title="任务汉化设置",
    finish_button_text="完成",
    output_mode="in_place",
    path_fields=[
        PathField("MC 实例文件夹:", "instance_dir_var", "instance_dir"),
        PathField("输出文件夹:", "output_dir_var", "output_dir", required=False),
    ],
    project_name_source="fixed",
    project_name_fixed="任务汉化",
    project_info_keys=["instance_dir", "output_dir"],
    setup_log_message="任务汉化项目已配置，开始提取文本...",
    finish_log_message="任务汉化已完成，准备生成最终文件。",
    finish_progress_message="",
    validation_error_title="输入不能为空",
    validation_error_message="请指定实例文件夹。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=True,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
))

register_project_type(ProjectTypeConfig(
    type_id="github",
    display_name="获取我的GitHub汉化PR",
    description="从GitHub汉化仓库下载项目并创建标签页。",
    setup_title="获取GitHub汉化PR",
    setup_tab_title="GitHub汉化PR",
    finish_button_text="完成",
    output_mode="resource_pack",
    path_fields=[],
    project_name_source="fixed",
    project_name_fixed="GitHub PR",
    project_info_keys=[],
    setup_log_message="",
    finish_log_message="",
    finish_progress_message="",
    enable_github_upload=True,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=True,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
))

register_project_type(ProjectTypeConfig(
    type_id="javamap",
    display_name="JAVA地图",
    description="汉化Java版冒险地图。处理进度文本、告示牌、命令文本、书籍等NBT数据。",
    setup_title="配置JAVA地图汉化项目",
    setup_tab_title="JAVA地图汉化设置",
    finish_button_text="完成并替换文件",
    output_mode="in_place",
    path_fields=[
        PathField("地图存档文件夹:", "source_dir_var", "javamap_dir"),
        PathField("输出文件夹:", "output_dir_var", "output_dir"),
    ],
    project_name_source="source_dir_name",
    project_info_keys=["source_dir", "output_dir"],
    setup_log_message="JAVA地图汉化项目已配置，开始扫描...",
    finish_log_message="JAVA地图汉化已完成，数据已准备好替换文件。",
    finish_progress_message="翻译处理完成，现在可以替换文件",
    validation_error_message="请同时指定地图存档文件夹和输出文件夹。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=False,
    enable_export_lang=False,
    enable_import_json=False,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    custom_features={
        "scan_targets": ["advancements", "datapacks", "region", "data"],
        "file_patterns": ["*.json", "*.nbt", "*.dat"],
    },
    hidden=True,
))

register_project_type(ProjectTypeConfig(
    type_id="datapack",
    display_name="数据包",
    description="汉化数据包。扫描advancements、functions等目录中JSON和mcfunction文件的文本内容。",
    setup_title="配置数据包汉化项目",
    setup_tab_title="数据包汉化设置",
    finish_button_text="完成并替换文件",
    output_mode="in_place",
    path_fields=[
        PathField("数据包文件夹:", "source_dir_var", "datapack_dir"),
    ],
    project_name_source="source_dir_name",
    project_info_keys=["datapack_dir"],
    setup_log_message="数据包汉化项目已配置，开始扫描...",
    finish_log_message="数据包汉化已完成。",
    finish_progress_message="翻译处理完成，现在可以替换文件",
    validation_error_message="请指定数据包文件夹。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=False,
    enable_export_lang=False,
    enable_import_json=False,
    enable_save_project=False,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    hidden=False,
))

register_project_type(ProjectTypeConfig(
    type_id="shader",
    display_name="光影",
    description="汉化光影包。扫描 shaders/lang/ 下的 .lang 语言文件，生成 zh_cn.lang。",
    setup_title="配置光影汉化项目",
    setup_tab_title="光影汉化设置",
    finish_button_text="完成并替换文件",
    output_mode="in_place",
    path_fields=[
        PathField("光影包文件夹:", "shader_dir_var", "shader_dir"),
    ],
    project_name_source="source_dir_name",
    project_info_keys=["shader_dir"],
    setup_log_message="光影汉化项目已配置，开始扫描...",
    finish_log_message="光影汉化已完成。",
    finish_progress_message="翻译处理完成，现在可以生成汉化文件",
    validation_error_message="请指定光影包文件夹路径。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=False,
    enable_export_lang=False,
    enable_import_json=False,
    enable_save_project=False,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    hidden=False,
))

register_project_type(ProjectTypeConfig(
    type_id="plugin",
    display_name="插件",
    description="汉化服务端插件。处理lang/目录下的YAML/Properties语言文件及plugin.yml描述。",
    setup_title="配置插件汉化项目",
    setup_tab_title="插件汉化设置",
    finish_button_text="完成并替换文件",
    output_mode="in_place",
    path_fields=[
        PathField("插件JAR/文件夹:", "source_dir_var", "plugin_dir"),
        PathField("输出文件夹:", "output_dir_var", "output_dir"),
    ],
    project_name_source="source_dir_name",
    project_info_keys=["source_dir", "output_dir"],
    setup_log_message="插件汉化项目已配置，开始扫描...",
    finish_log_message="插件汉化已完成，数据已准备好替换文件。",
    finish_progress_message="翻译处理完成，现在可以替换文件",
    validation_error_message="请同时指定插件JAR/文件夹和输出文件夹。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=True,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    custom_features={
        "scan_targets": ["lang", "languages", "messages", "i18n", "locale"],
        "file_patterns": ["*.yml", "*.yaml", "*.properties", "*.json"],
        "has_plugin_yml": True,
    },
    hidden=True,
))

register_project_type(ProjectTypeConfig(
    type_id="palladium",
    display_name="Palladium 能力汉化",
    description="汉化 Palladium 框架的能力文件。自动去重翻译文本，完成后再写回 JAR 文件。",
    setup_title="配置 Palladium 能力汉化",
    setup_tab_title="Palladium 汉化设置",
    finish_button_text="完成并写入 JAR",
    output_mode="in_place",
    path_fields=[
        PathField("JAR 文件:", "jar_path_var", "jar_path", browse_mode="file", filetypes=(("JAR 文件", "*.jar"), ("所有文件", "*.*"))),
    ],
    project_name_source="source_dir_name",
    project_info_keys=["jar_path"],
    setup_log_message="Palladium 能力汉化项目已配置，开始扫描...",
    finish_log_message="Palladium 能力汉化已完成。",
    finish_progress_message="翻译处理完成，现在可以写入 JAR",
    validation_error_message="请指定 JAR 文件路径。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=True,
    enable_export_lang=False,
    enable_import_json=True,
    enable_save_project=True,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    hidden=False,
))

register_project_type(ProjectTypeConfig(
    type_id="decompile",
    display_name="JAR反编译翻译",
    description="反编译 JAR 文件，提取语言文件和硬编码字符串进行翻译，完成后直接替换原 JAR。",
    setup_title="配置 JAR 反编译翻译",
    setup_tab_title="反编译翻译设置",
    finish_button_text="完成并替换 JAR",
    output_mode="in_place",
    path_fields=[
        PathField("JAR 文件:", "jar_path_var", "jar_path", browse_mode="file", filetypes=(("JAR 文件", "*.jar"), ("所有文件", "*.*"))),
    ],
    project_name_source="jar_path",
    project_info_keys=["jar_path"],
    setup_log_message="JAR 反编译翻译项目已配置，开始扫描...",
    finish_log_message="翻译已完成，准备写入 JAR 文件。",
    finish_progress_message="翻译处理完成，现在可以替换 JAR 文件",
    validation_error_message="请指定 JAR 文件路径。",
    enable_github_upload=False,
    enable_translation_console=True,
    enable_export_json=False,
    enable_export_lang=False,
    enable_import_json=False,
    enable_save_project=False,
    enable_find_replace=True,
    enable_dictionary_search=True,
    enable_add_to_dictionary=True,
    enable_ai_translation=True,
    enable_batch_operations=True,
    enable_undo_redo=True,
    hidden=False,
))


def get_all_project_types() -> list[ProjectTypeConfig]:
    return [cfg for cfg in PROJECT_TYPE_REGISTRY.values() if not cfg.hidden]
