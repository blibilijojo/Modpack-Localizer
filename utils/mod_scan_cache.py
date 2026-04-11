"""
持久化缓存：根对象为「整包 SHA1 → {curseforge_hash}」，无 version 包裹。

对象键即 Modrinth 整包 SHA1，条目中不再重复写入 modrinth_hash。

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

CACHE_FILENAME = "mod_fingerprint_cache.json"


def cache_path() -> Path:
    return config_manager.APP_DATA_PATH / CACHE_FILENAME


def cache_key_sha1(modrinth_sha1_hex: str) -> str:
    """缓存主键：40 位小写十六进制 SHA1（与 hashlib.sha1(...).hexdigest() 一致）。"""
    return modrinth_sha1_hex.lower()


def _storage_from_value(key: str, v: Any) -> Optional[Dict[str, str]]:
    """从磁盘上的 value 解析为内存存储形态（仅 curseforge_hash）。"""
    if not isinstance(v, dict):
        return None
    cf = v.get("curseforge_hash")
    if not isinstance(cf, str) or not cf:
        return None
    return {"curseforge_hash": cf}


def _disk_value_needs_compact(v: Any) -> bool:
    """是否含除 curseforge_hash 以外的字段（旧冗余格式，需重写）。"""
    if not isinstance(v, dict):
        return False
    return set(v.keys()) != {"curseforge_hash"}


class ModFingerprintDiskCache:
    def __init__(self):
        self._entries: Dict[str, Dict[str, str]] = {}
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

            merged: Dict[str, Dict[str, str]] = {}
            migrated = False

            inner = data.get("entries")
            legacy_wrapped = isinstance(inner, dict) and (
                "version" in data or list(data.keys()) == ["entries"]
            )
            if legacy_wrapped:
                for k, v in inner.items():
                    st = _storage_from_value(str(k), v)
                    if st:
                        merged[cache_key_sha1(str(k))] = st
                migrated = True
                logging.info("已自旧版（version/entries 包裹）迁移模组指纹缓存为扁平格式: %s", path)
            else:
                for k, v in data.items():
                    if k in ("version", "entries"):
                        continue
                    if _disk_value_needs_compact(v):
                        migrated = True
                    st = _storage_from_value(str(k), v)
                    if st:
                        merged[cache_key_sha1(str(k))] = st

            self._entries = merged
            if migrated:
                self._dirty = True
        except Exception as e:
            logging.warning("读取模组指纹缓存失败，将重新建立: %s — %s", path, e)
            self._entries = {}

    def get(self, key: str) -> Optional[Dict[str, str]]:
        key_norm = cache_key_sha1(key)
        rec = self._entries.get(key_norm)
        if not rec:
            return None
        cf = rec.get("curseforge_hash")
        if not isinstance(cf, str) or not cf:
            return None
        return {
            "curseforge_hash": cf,
            "modrinth_hash": key_norm,
        }

    def put(self, key: str, record: Dict[str, Any]) -> None:
        key_norm = cache_key_sha1(key)
        self._entries[key_norm] = {
            "curseforge_hash": str(record.get("curseforge_hash", "")),
        }
        self._dirty = True

    def save_if_dirty(self) -> None:
        if not self._dirty:
            return
        path = cache_path()
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=0)
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
