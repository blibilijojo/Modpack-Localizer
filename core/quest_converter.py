from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any


class BaseQuestConverter:

    def convert_to_ftbq(self, input_dir: Path, output_dir: Path) -> bool:
        raise NotImplementedError


class FTBQuestConverter(BaseQuestConverter):

    def convert_to_ftbq(self, input_dir: Path, output_dir: Path) -> bool:
        logging.info(f"开始转换 BetterQuesting -> FTB Quests: {input_dir} -> {output_dir}")

        try:
            bq_dir = input_dir / "bq"
            if not bq_dir.exists():
                logging.error(f"BetterQuesting 目录不存在: {bq_dir}")
                return False

            default_lang_file = bq_dir / "default_lang.json"
            if not default_lang_file.exists():
                logging.error(f"默认语言文件不存在: {default_lang_file}")
                return False

            with open(default_lang_file, 'r', encoding='utf-8') as f:
                bq_data = json.load(f)

            ftbq_data = self._transform_bq_data(bq_data)

            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "snippets" / "ftbq_quests.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(ftbq_data, f, indent=2, ensure_ascii=False)

            logging.info(f"转换完成: {output_file}")
            return True

        except Exception as e:
            logging.error(f"转换失败: {e}", exc_info=True)
            return False

    def _transform_bq_data(self, bq_data: dict) -> dict:
        ftbq_data: dict[str, Any] = {
            "chapters": [],
            "version": 2
        }

        quest_lists = bq_data.get("questLists:9", {})
        quests_data = bq_data.get("quests:9", {})

        if not quests_data:
            return ftbq_data

        for quest_list_id, quest_list in quest_lists.items():
            chapter = self._convert_quest_list_to_chapter(quest_list_id, quest_list, quests_data)
            if chapter:
                ftbq_data["chapters"].append(chapter)

        return ftbq_data

    def _convert_quest_list_to_chapter(self, quest_list_id: str, quest_list: dict, quests_data: dict) -> dict | None:
        chapter: dict[str, Any] = {
            "title": quest_list.get("name:8", f"Chapter {quest_list_id}"),
            "quests": [],
            "reward": [],
            "subtitle": quest_list.get("desc:8", ""),
            "hide": False,
            "visibility": "ALWAYS",
            "default_quest_shape": "CIRCLE"
        }

        quest_ids = quest_list.get("quests:11", [])
        if not quest_ids:
            return chapter

        for quest_id in quest_ids:
            quest_key = str(quest_id)
            if quest_key in quests_data:
                quest = quests_data[quest_key]
                ftbq_quest = self._convert_quest(quest)
                if ftbq_quest:
                    chapter["quests"].append(ftbq_quest)

        return chapter

    def _convert_quest(self, bq_quest: dict) -> dict | None:
        ftbq_quest: dict[str, Any] = {
            "title": bq_quest.get("name:8", ""),
            "subtitle": bq_quest.get("desc:8", ""),
            "tasks": [],
            "reward": [],
            "x": bq_quest.get("x:3", 0),
            "y": bq_quest.get("y:3", 0),
            "hide": not bq_quest.get("visibility:5", True),
            "description": [],
            "dependencies": [],
            "id": bq_quest.get("questID:3", 0),
            "shape": "CIRCLE"
        }

        tasks = bq_quest.get("tasks:9", {})
        for task_id, task in tasks.items():
            ftbq_task = self._convert_task(task)
            if ftbq_task:
                ftbq_quest["tasks"].append(ftbq_task)

        return ftbq_quest

    def _convert_task(self, bq_task: dict) -> dict | None:
        task_type = bq_task.get("taskID:8", "")

        if "retrieval" in task_type.lower():
            return {
                "type": "item",
                "items": self._convert_task_items(bq_task)
            }
        elif "kill" in task_type.lower():
            return {
                "type": "kill",
                "entity": bq_task.get("entity:8", "minecraft:zombie"),
                "value": bq_task.get("required:3", 1)
            }
        elif "location" in task_type.lower():
            return {
                "type": "location",
                "dimension": bq_task.get("dimension:3", 0)
            }
        elif "checkbox" in task_type.lower():
            return {
                "type": "checkmark"
            }
        else:
            return None

    def _convert_task_items(self, bq_task: dict) -> list[dict]:
        items = []
        required_items = bq_task.get("requiredItems:9", {})

        for item_id, item in required_items.items():
            items.append({
                "item": item.get("id:8", "minecraft:air"),
                "count": item.get("Amount:3", 1)
            })

        return items if items else [{"item": "minecraft:air", "count": 1}]


class BQMQuestConverter(BaseQuestConverter):

    def convert_to_ftbq(self, input_dir: Path, output_dir: Path) -> bool:
        logging.info(f"BQM 转换暂未实现: {input_dir} -> {output_dir}")
        return False


class LANGConverter:

    def convert_json_to_lang(self, data: dict[str, str]) -> str:
        lines = []
        for key, value in data.items():
            escaped_value = value.replace('\n', '\\n')
            lines.append(f"{key}={escaped_value}")
        return '\n'.join(lines)

    def convert_lang_to_json(self, lang_content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in lang_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                result[key.strip()] = value.replace('\\n', '\n')
        return result


class ConversionManager:

    def __init__(self, converter: BaseQuestConverter | None = None):
        self._converters: dict[str, BaseQuestConverter] = {
            "ftbq": FTBQuestConverter(),
            "bqm": BQMQuestConverter(),
        }
        self._converter = converter

    def get_converter(self, quest_type: str) -> BaseQuestConverter | None:
        if self._converter:
            return self._converter
        return self._converters.get(quest_type.lower())

    def convert(self, quest_type: str, input_dir: Path, output_dir: Path) -> bool:
        converter = self.get_converter(quest_type)
        if converter is None:
            logging.error(f"不支持的任务类型: {quest_type}")
            return False
        return converter.convert_to_ftbq(input_dir, output_dir)
