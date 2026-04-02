"""
持久化缓存：以整包 SHA1（与 Modrinth 一致）为键 → CurseForge 指纹及从 JAR 内解析的元数据。

不依赖修改时间：同一 jar 重复下载、仅 mtime 不同仍可命中。
读盘后仍需算 SHA1 才能查表；命中时可跳过 Murmur 与 ZIP 元数据解析。

与仅内存的 Extractor._mod_info_cache、会话 tab 缓存等无关。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from utils import config_manager

MOD_FINGERPRINT_CACHE_VERSION = 2
CACHE_FILENAME = "mod_fingerprint_cache.json"


def cache_path() -> Path:
    return config_manager.APP_DATA_PATH / CACHE_FILENAME


def cache_key_sha1(modrinth_sha1_hex: str) -> str:
    """缓存主键：40 位小写十六进制 SHA1（与 hashlib.sha1(...).hexdigest() 一致）。"""
    return modrinth_sha1_hex.lower()


class ModFingerprintDiskCache:
    def __init__(self):
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._dirty = False

    def load(self) -> None:
        path = cache_path()
        if not path.is_file():
            self._entries = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("root must be object")
            ver = data.get("version")
            if ver != MOD_FINGERPRINT_CACHE_VERSION:
                logging.info(
                    "模组指纹缓存版本不匹配或缺失，已忽略旧文件: %s (version=%s)",
                    path,
                    ver,
                )
                self._entries = {}
                return
            raw = data.get("entries")
            if not isinstance(raw, dict):
                self._entries = {}
                return
            self._entries = {
                cache_key_sha1(str(k)): dict(v)
                for k, v in raw.items()
                if isinstance(v, dict)
            }
        except Exception as e:
            logging.warning("读取模组指纹缓存失败，将重新建立: %s — %s", path, e)
            self._entries = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        rec = self._entries.get(cache_key_sha1(key))
        if not rec:
            return None
        required = ("mod_name", "curseforge_hash", "modrinth_hash")
        if not all(k in rec for k in required):
            return None
        return rec

    def put(self, key: str, record: Dict[str, Any]) -> None:
        self._entries[cache_key_sha1(key)] = {
            "mod_name": record.get("mod_name", ""),
            "curseforge_hash": record.get("curseforge_hash", ""),
            "modrinth_hash": record.get("modrinth_hash", ""),
            "game_version": record.get("game_version", "") or "",
        }
        self._dirty = True

    def save_if_dirty(self) -> None:
        if not self._dirty:
            return
        path = cache_path()
        payload = {
            "version": MOD_FINGERPRINT_CACHE_VERSION,
            "entries": self._entries,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=0)
                f.write("\n")
            os.replace(tmp, path)
            self._dirty = False
            logging.debug("已写入模组指纹缓存: %s (%d 条)", path, len(self._entries))
        except Exception as e:
            logging.warning("写入模组指纹缓存失败: %s — %s", path, e)
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
