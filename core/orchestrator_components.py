import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable

from core.workflow import Workflow
from core.models import PackSettings


DEFAULT_NAME_TEMPLATE = "汉化资源包_{timestamp}"
DEFAULT_DESC_TEMPLATE = (
    "整合包汉化数据分析 (共 {total} 条):\n"
    "▷ AI 翻译贡献: {ai_count} 条 ({ai_percent})\n"
    "▷ 人工及社区贡献: {human_count} 条 ({human_percent})"
)


class ExtractionOrchestrator:
    """负责数据提取阶段的协调器"""
    
    def __init__(self, settings: Dict, update_progress: Callable, workflow: Workflow):
        self.settings = settings
        self.update_progress = update_progress
        self.workflow = workflow
    
    def run(self, context):
        """执行数据提取阶段"""
        logging.info("阶段 1/3: 开始聚合语言数据...")
        self.update_progress("正在聚合数据...", 10)
        
        if not self.settings.get('mods_dir'):
            raise ValueError("未配置Mods目录，请先在设置中配置")
        
        mods_path = Path(self.settings['mods_dir'])
        if not mods_path.exists() or not mods_path.is_dir():
            raise ValueError(f"配置的Mods目录不存在或不是目录: {mods_path}")
        
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
        
        context.extraction_progress = extraction_progress
        
        extraction_result = self.workflow.run_extraction(context)
        master_english_count = len(extraction_result.master_english)
        logging.info(f"数据提取完成，共发现 {master_english_count} 个命名空间")
        
        if master_english_count == 0:
            raise Exception("未从模组中提取到任何英文语言文件。请确保下载的模组包含 lang/en_us.lang 或 lang/en_us.json 文件。")
        
        self.update_progress("数据聚合完成", 50)
        return extraction_result


class TranslationOrchestrator:
    """负责翻译决策阶段的协调器"""
    
    def __init__(self, settings: Dict, update_progress: Callable, workflow: Workflow):
        self.settings = settings
        self.update_progress = update_progress
        self.workflow = workflow
    
    def run(self, context):
        """执行翻译决策阶段"""
        logging.info("阶段 2/3: 执行翻译决策...")
        self.update_progress("正在应用翻译规则...", 60)
        
        translation_result = self.workflow.run_translation(context)
        workbench_data_count = len(translation_result.workbench_data)
        logging.info(f"翻译决策完成，共生成 {workbench_data_count} 个命名空间的翻译数据")
        
        if not translation_result.workbench_data:
            raise Exception("翻译决策未生成任何数据。可能是因为模组中的语言文件格式不正确或无法解析。")
        
        self.update_progress("翻译决策完成", 100)
        return translation_result


class BuildOrchestrator:
    """负责资源包构建阶段的协调器"""
    
    def __init__(self, settings: Dict, update_progress: Callable, workflow: Workflow, log_callback: Callable):
        self.settings = settings
        self.update_progress = update_progress
        self.workflow = workflow
        self.log = log_callback
    
    def run(self, context, final_workbench_data, raw_english_files, namespace_formats):
        """执行资源包构建阶段"""
        self.log("开始生成资源包...", "INFO")
        self.update_progress("正在构建资源包...", 10)
        
        metadata_values = self._generate_pack_metadata_values(final_workbench_data)
        return metadata_values
    
    def _generate_pack_metadata_values(self, final_workbench_data) -> dict:
        """生成资源包元数据值"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not final_workbench_data:
            return {"timestamp": timestamp, "total": 0, "ai_count": 0, "ai_percent": "0.0%", "human_count": 0, "human_percent": "0.0%"}
        
        ai_count = 0
        human_count = 0
        total_translated = 0
        ai_sources = {"AI翻译"}
        
        for ns_data in final_workbench_data.values():
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
        """替换模板中的占位符"""
        for key, value in data.items():
            template_str = template_str.replace(f"{{{key}}}", str(value))
        return template_str
