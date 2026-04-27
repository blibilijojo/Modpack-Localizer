from __future__ import annotations
import hashlib
import logging
import re
from pathlib import Path

_VERSION_PATTERN = re.compile(r'^\d+\.\d+(\.\d+)?$')
_WHITESPACE_BYTES = frozenset({9, 10, 13, 32})


def curseforge_fingerprint_from_jar_bytes(file_data: bytes) -> str:
    filtered_data = bytes(b for b in file_data if b not in _WHITESPACE_BYTES)
    length = len(filtered_data)
    if length == 0:
        return "0"

    m = 0x5BD1E995
    r = 24
    h = 1 ^ length

    for i in range(0, length - (length % 4), 4):
        k = filtered_data[i] | (filtered_data[i + 1] << 8) | (filtered_data[i + 2] << 16) | (filtered_data[i + 3] << 24)
        k = (k * m) & 0xFFFFFFFF
        k = (k ^ (k >> r)) & 0xFFFFFFFF
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h = (h ^ k) & 0xFFFFFFFF

    remaining = length % 4
    if remaining > 0:
        pos = length - remaining
        if remaining >= 3:
            h = (h ^ (filtered_data[pos + 2] << 16)) & 0xFFFFFFFF
        if remaining >= 2:
            h = (h ^ (filtered_data[pos + 1] << 8)) & 0xFFFFFFFF
        if remaining >= 1:
            h = (h ^ filtered_data[pos]) & 0xFFFFFFFF
            h = (h * m) & 0xFFFFFFFF

    h = (h ^ (h >> 13)) & 0xFFFFFFFF
    h = (h * m) & 0xFFFFFFFF
    h = (h ^ (h >> 15)) & 0xFFFFFFFF
    return str(h)


def jar_mod_fingerprints_and_meta(
    jar_file: Path, file_data: bytes, modrinth_hash: str | None = None
) -> tuple[str, str, str]:
    if modrinth_hash is None:
        modrinth_hash = hashlib.sha1(file_data).hexdigest()
    curseforge_hash = curseforge_fingerprint_from_jar_bytes(file_data)
    return jar_file.name, curseforge_hash, modrinth_hash


def is_version_string(value: str) -> bool:
    return bool(_VERSION_PATTERN.match(value.strip()))


def _version_to_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split('.') if p.isdigit())
    except Exception:
        return ()


def _version_diff(v1: str, v2: str) -> int:
    t1 = _version_to_tuple(v1)
    t2 = _version_to_tuple(v2)
    min_len = min(len(t1), len(t2))
    for i in range(min_len):
        if t1[i] != t2[i]:
            return abs(t1[i] - t2[i])
    return abs(len(t1) - len(t2))


def _get_main_version(version: str) -> str:
    parts = version.split('.')
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return version


def match_github_version(game_version: str, loaders: str, github_versions: list[str]) -> str:
    if not github_versions:
        return ""

    version_info = []
    for gh_version in github_versions:
        if '-' in gh_version:
            v, l = gh_version.rsplit('-', 1)
            version_info.append((v, l, gh_version))
        else:
            version_info.append((gh_version, '', gh_version))

    main_game_version = _get_main_version(game_version)

    for v, l, full_version in version_info:
        if v == main_game_version and l == loaders:
            return full_version

    for v, l, full_version in version_info:
        if v == main_game_version and l == "":
            return full_version

    for v, l, full_version in version_info:
        if v == main_game_version:
            return full_version

    version_info.sort(key=lambda x: (_version_diff(main_game_version, x[0]), 0 if x[1] == "" else 1))

    return version_info[0][2] if version_info else ""
