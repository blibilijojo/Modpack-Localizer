from __future__ import annotations
import logging
import re
import requests

from utils import config_manager
from utils.retry_logic import api_retry
from utils.api_urls import MODRINTH_API_BASE, CURSEFORGE_API_BASE

_KNOWN_LOADERS = frozenset({"forge", "fabric", "quilt", "neoforge"})


def _extract_game_version(game_versions: list) -> str | None:
    for v in game_versions:
        if isinstance(v, dict):
            if v.get("gameVersionName", "").lower() == "minecraft":
                return v.get("version")
        elif isinstance(v, str):
            if re.match(r'^\d+\.\d+', v):
                return v
    return None


def _extract_loaders(game_versions: list) -> str:
    loaders = []
    for v in game_versions:
        if isinstance(v, dict):
            name = v.get("gameVersionName", "").lower()
        elif isinstance(v, str):
            name = v.lower()
        else:
            continue
        if name in _KNOWN_LOADERS:
            loaders.append(name)
    return loaders[0] if loaders else ""


class ModrinthClient:

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def fetch_version_files(self, modrinth_hashes: list[str]) -> dict:
        url = f"{MODRINTH_API_BASE}/version_files"
        headers = {"Content-Type": "application/json"}
        data = {"hashes": modrinth_hashes, "algorithm": "sha1"}
        logging.info(f"从Modrinth API获取 {len(modrinth_hashes)} 个模组的信息...")
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def fetch_projects(self, project_ids: list[str]) -> list[dict]:
        ids_str = ','.join([f'"{pid}"' for pid in project_ids])
        url = f"{MODRINTH_API_BASE}/projects?ids=[{ids_str}]"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_mod_info(self, modrinth_hashes: list[str]) -> dict[str, dict]:
        if not modrinth_hashes:
            return {}

        try:
            modrinth_version = self.fetch_version_files(modrinth_hashes)
            logging.info(f"从Modrinth获取到 {len(modrinth_version)} 个本地模组的对应信息")

            if not modrinth_version:
                return {}

            project_ids = []
            hash_to_project: dict[str, str] = {}
            hash_to_game_version: dict[str, str] = {}
            hash_to_loaders: dict[str, str] = {}

            for hash_value, info in modrinth_version.items():
                project_id = info.get("project_id")
                if project_id:
                    project_ids.append(project_id)
                    hash_to_project[hash_value] = project_id
                game_versions = info.get("game_versions", [])
                if game_versions:
                    hash_to_game_version[hash_value] = game_versions[0]
                loaders = info.get("loaders", [])
                hash_to_loaders[hash_value] = loaders[0] if loaders else ""

            if not project_ids:
                return {}

            project_info = self.fetch_projects(project_ids)

            project_map: dict[str, dict] = {}
            for project in project_info:
                project_id = project.get("id")
                if project_id:
                    project_map[project_id] = {
                        "name": project.get("title"),
                        "slug": project.get("slug"),
                        "url": f"https://modrinth.com/mod/{project.get('slug')}",
                        "game_versions": project.get("game_versions", [])
                    }

            result: dict[str, dict] = {}
            for hash_value, project_id in hash_to_project.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id].copy()
                    if hash_value in hash_to_game_version:
                        result[hash_value]["game_version"] = hash_to_game_version[hash_value]
                    elif result[hash_value].get("game_versions"):
                        result[hash_value]["game_version"] = result[hash_value]["game_versions"][0]
                    result[hash_value]["loaders"] = hash_to_loaders.get(hash_value, "")

            return result
        except Exception as e:
            logging.error(f"从Modrinth获取模组信息失败: {e}")
            return {}


class CurseForgeClient:

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def fetch_fingerprints(self, base_url: str, curseforge_hashes: list[str], api_key: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        fingerprint_url = f"{base_url}/v1/fingerprints/432"
        data = {"fingerprints": [int(h) for h in curseforge_hashes]}
        logging.info(f"从CurseForge API ({base_url})获取 {len(curseforge_hashes)} 个模组的信息...")
        response = requests.post(fingerprint_url, json=data, headers=headers, timeout=30)

        if response.status_code == 403:
            logging.error("CurseForge API密钥无效或已过期，请在设置中更新API密钥")
            raise requests.exceptions.HTTPError("API密钥无效", response=response)
        elif response.status_code == 429:
            logging.warning("CurseForge API请求频率超限")
            raise requests.exceptions.HTTPError("请求频率超限 (429)", response=response)

        response.raise_for_status()
        return response.json()

    @api_retry(max_retries=3, initial_delay=1.0, max_delay=30.0)
    def fetch_mods(self, base_url: str, project_ids: list[int], api_key: str) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        url = f"{base_url}/v1/mods"
        data = {"modIds": project_ids}
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        return response_data.get("data", [])

    def _process_exact_matches(self, exact_matches: list[dict]) -> tuple[dict[str, int], dict[str, str], dict[str, str]]:
        hash_to_project_id: dict[str, int] = {}
        hash_to_game_version: dict[str, str] = {}
        hash_to_loaders: dict[str, str] = {}

        for match in exact_matches:
            project_id = match.get("id")
            file_info = match.get("file", {})
            fingerprint = str(file_info.get("fileFingerprint", ""))

            if not (project_id and fingerprint):
                continue

            hash_to_project_id[fingerprint] = project_id

            game_versions = file_info.get("gameVersions", [])
            mc_version = _extract_game_version(game_versions)
            if mc_version:
                hash_to_game_version[fingerprint] = mc_version
                logging.debug(f"从CurseForge获取游戏版本: fingerprint={fingerprint[:20]}... -> {mc_version}")

            loader = _extract_loaders(game_versions)
            hash_to_loaders[fingerprint] = loader

        return hash_to_project_id, hash_to_game_version, hash_to_loaders

    def get_mod_info(self, curseforge_hashes: list[str]) -> dict[str, dict]:
        if not curseforge_hashes:
            return {}

        try:
            config = config_manager.load_config()
            api_key = config.get('curseforge_api_key', '')

            if not api_key:
                logging.warning("CurseForge API密钥未配置，请在设置中配置")
                return {}

            base_urls = [CURSEFORGE_API_BASE]

            exact_matches: list[dict] = []
            hash_to_project_id: dict[str, int] = {}
            hash_to_game_version: dict[str, str] = {}
            hash_to_loaders: dict[str, str] = {}
            project_map: dict[int, dict] = {}

            for base_url in base_urls:
                try:
                    response_data = self.fetch_fingerprints(base_url, curseforge_hashes, api_key)
                    exact_matches = response_data.get("data", {}).get("exactMatches", [])

                    if not exact_matches:
                        logging.info(f"CurseForge API响应: {response_data}")
                        partial_matches = response_data.get("data", {}).get("partialMatches", [])
                        if partial_matches:
                            logging.info(f"CurseForge找到 {len(partial_matches)} 个部分匹配")

                    logging.info(f"从CurseForge获取到 {len(exact_matches)} 个本地模组的对应信息")

                    if exact_matches:
                        hash_to_project_id, hash_to_game_version, hash_to_loaders = \
                            self._process_exact_matches(exact_matches)

                        project_ids = list(set(hash_to_project_id.values()))

                        if project_ids:
                            project_info = self.fetch_mods(base_url, project_ids, api_key)

                            for project in project_info:
                                project_id = project.get("id")
                                if project_id:
                                    project_map[project_id] = {
                                        "name": project.get("name"),
                                        "slug": project.get("slug"),
                                        "url": f"https://www.curseforge.com/minecraft/mc-mods/{project.get('slug')}"
                                    }
                        break
                except requests.exceptions.HTTPError as e:
                    if "API密钥无效" in str(e) or "请求频率超限" in str(e):
                        return {}
                    logging.error(f"从CurseForge API ({base_url})获取模组信息失败: {e}")
                    continue
                except Exception as e:
                    logging.error(f"从CurseForge API ({base_url})获取模组信息失败: {e}")
                    continue

            if not exact_matches:
                return {}

            result: dict[str, dict] = {}
            for hash_value, project_id in hash_to_project_id.items():
                if project_id in project_map:
                    result[hash_value] = project_map[project_id].copy()
                    if hash_value in hash_to_game_version:
                        result[hash_value]["game_version"] = hash_to_game_version[hash_value]
                    result[hash_value]["loaders"] = hash_to_loaders.get(hash_value, "")

            return result
        except Exception as e:
            logging.error(f"从CurseForge获取模组信息失败: {e}")
            return {}
