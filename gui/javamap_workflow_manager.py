"""Minecraft Java 版地图汉化工作流管理器（基于 nbtlib）。

从地图存档中提取告示牌、书本、命令方块、容器、实体等文本，
在工作台中翻译后写回地图文件。

支持完全替换：方块实体、实体、刷怪笼、蜂巢、数据包、记分板、Bossbar。
使用 nbtlib 解析 NBT，手动读取 Anvil 区域文件。兼容 Python 3.14+。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import struct
import tempfile
import zlib
from io import BytesIO
from pathlib import Path

from gui import ui_utils

# ---------------------------------------------------------------------------
# 文本组件处理
# ---------------------------------------------------------------------------

def _flatten_json_text(obj) -> str:
    if isinstance(obj, str):
        try:
            return _flatten_json_text(json.loads(obj))
        except (json.JSONDecodeError, TypeError):
            return obj
    if isinstance(obj, list):
        return "".join(_flatten_json_text(item) for item in obj)
    if isinstance(obj, dict):
        parts = []
        if "text" in obj:
            parts.append(str(obj["text"]))
        if "translate" in obj:
            parts.append(str(obj["translate"]))
        if "extra" in obj and isinstance(obj["extra"], list):
            parts.append(_flatten_json_text(obj["extra"]))
        if "with" in obj and isinstance(obj["with"], list):
            parts.append(_flatten_json_text(obj["with"]))
        return "".join(parts)
    return str(obj)


def _is_translatable_text(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    if len(t) < 2:
        return False
    # 命令和注释
    if t.startswith("/") or t.startswith("#"):
        return False
    # 纯数字/标点
    if re.match(r'^[\d\s.,\-]+$', t):
        return False
    # 纯小写字母/数字/下划线/点/冒号（minecraft:stone 等）
    if re.match(r'^[a-z0-9_.:]+$', t):
        return False
    # 房间编号 [数字]
    if re.match(r'^\[\d+\]$', t):
        return False
    # 日期格式 DD/MM/YYYY 或 YY/MM/DD
    if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', t):
        return False
    # 方向符号（如 <<===, ===>）
    if re.match(r'^[<>=\-]+$', t):
        return False
    # 代码标识 [字母数字:]（如 [F3], [E3], [E1:C], [E1L3A3]）
    if re.match(r'^\[[A-Z0-9:]+\]$', t):
        return False
    # 版本标识（如 Concept_35, Reef V1）
    if re.match(r'^[A-Za-z]+[\s_][A-Za-z]*\d+$', t):
        return False
    # 数学/计算表达式（如 8 1 /, 7 X 3, 6 5 \）
    if re.match(r'^[\d\s+\-*/\\xX]+$', t):
        return False
    return True


def _parse_text_component(value) -> str:
    if value is None:
        return ""
    s = str(value)
    if s.startswith("{") or s.startswith("["):
        try:
            return _flatten_json_text(json.loads(s))
        except (json.JSONDecodeError, TypeError):
            pass
    return _flatten_json_text(s)


def _make_json_text(zh_text: str):
    """返回 nbtlib.String 包装的 JSON 文本组件。"""
    try:
        import nbtlib
        return nbtlib.String(json.dumps({"text": zh_text}, ensure_ascii=False))
    except ImportError:
        return json.dumps({"text": zh_text}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 区域文件（Anvil .mca）读写
# ---------------------------------------------------------------------------

def _read_region_chunks(region_path: Path) -> list[tuple[int, int, dict]]:
    try:
        import nbtlib
    except ImportError:
        return []

    data = region_path.read_bytes()
    if len(data) < 8192:
        return []

    parts = region_path.stem.split(".")
    region_x = int(parts[1]) if len(parts) == 3 else 0
    region_z = int(parts[2]) if len(parts) == 3 else 0

    chunks = []
    for lx in range(32):
        for lz in range(32):
            ho = (lx + lz * 32) * 4
            offset = (data[ho] << 16) | (data[ho + 1] << 8) | data[ho + 2]
            sectors = data[ho + 3]
            if offset == 0 or sectors == 0:
                continue
            co = offset * 4096
            if co + 5 > len(data):
                continue
            clen = struct.unpack_from(">I", data, co)[0]
            comp = data[co + 4]
            raw = data[co + 5:co + 5 + clen - 1]
            try:
                if comp == 2:
                    dec = zlib.decompress(raw)
                elif comp == 1:
                    dec = zlib.decompress(raw, 15 + 32)
                elif comp == 3:
                    dec = raw
                else:
                    continue
                nbt = nbtlib.File.parse(BytesIO(dec))
                chunks.append(((region_x << 5) + lx, (region_z << 5) + lz, nbt))
            except Exception:
                continue
    return chunks


def _serialize_nbt(nbt) -> bytes:
    with tempfile.NamedTemporaryFile(suffix='.nbt', delete=False) as f:
        tmp = f.name
    try:
        nbt.save(tmp)
        with open(tmp, 'rb') as f:
            return f.read()
    finally:
        os.unlink(tmp)


def _write_region_file(region_path: Path, chunks: list[tuple[int, int, dict]]):
    original = region_path.read_bytes() if region_path.exists() else bytes(8192)
    if len(original) < 8192:
        original = bytes(8192)

    orig_map = {}
    for lx in range(32):
        for lz in range(32):
            ho = (lx + lz * 32) * 4
            off = (original[ho] << 16) | (original[ho + 1] << 8) | original[ho + 2]
            sec = original[ho + 3]
            if off > 0 and sec > 0:
                orig_map[(lx, lz)] = (off, sec)

    body_map = {}
    for cx, cz, nbt in chunks:
        lx, lz = cx & 31, cz & 31
        ser = _serialize_nbt(nbt)
        comp = zlib.compress(ser, 6)
        body = struct.pack(">IB", len(comp) + 1, 2) + comp
        rem = len(body) % 4096
        if rem:
            body += b"\x00" * (4096 - rem)
        body_map[(lx, lz)] = body

    for (lx, lz), (off, sec) in orig_map.items():
        if (lx, lz) not in body_map:
            start = off * 4096
            end = start + sec * 4096
            if end <= len(original):
                body_map[(lx, lz)] = original[start:end]

    header = bytearray(8192)
    bodies = []
    cur = 2
    for lx in range(32):
        for lz in range(32):
            if (lx, lz) in body_map:
                body = body_map[(lx, lz)]
                ns = len(body) // 4096
                ho = (lx + lz * 32) * 4
                header[ho] = (cur >> 16) & 0xFF
                header[ho + 1] = (cur >> 8) & 0xFF
                header[ho + 2] = cur & 0xFF
                header[ho + 3] = ns & 0xFF
                bodies.append(body)
                cur += ns

    region_path.parent.mkdir(parents=True, exist_ok=True)
    with open(region_path, "wb") as f:
        f.write(bytes(header))
        for b in bodies:
            f.write(b)


# ---------------------------------------------------------------------------
# 方块名称匹配
# ---------------------------------------------------------------------------

_SIGN_NAMES = {"sign", "hanging_sign"}
_CONTAINER_NAMES = {
    "chest", "furnace", "shulker_box", "barrel", "smoker",
    "blast_furnace", "trapped_chest", "hopper", "dispenser",
    "dropper", "brewing_stand", "campfire",
    "chiseled_bookshelf", "decorated_pot",
}
_CMD_BLOCK_NAMES = {"command_block", "chain_command_block", "repeating_command_block"}


def _is_sign(name: str) -> bool:
    return name in _SIGN_NAMES or name.endswith("_sign") or name.endswith("_hanging_sign")


def _is_container(name: str) -> bool:
    return name in _CONTAINER_NAMES


# ---------------------------------------------------------------------------
# 文本提取
# ---------------------------------------------------------------------------

def _extract_sign(nbt, p: str) -> list[dict]:
    entries = []
    for side in ("front_text", "back_text"):
        if side in nbt and "messages" in nbt[side]:
            for i in range(len(nbt[side]["messages"])):
                t = _parse_text_component(nbt[side]["messages"][i])
                if _is_translatable_text(t):
                    entries.append({"location": f"{p}/{side}/messages[{i}]", "text": t})
    for i in range(1, 5):
        k = f"Text{i}"
        if k in nbt:
            t = _parse_text_component(nbt[k])
            if _is_translatable_text(t):
                entries.append({"location": f"{p}/{k}", "text": t})
    return entries


def _extract_command_block(nbt, p: str) -> list[dict]:
    if "Command" not in nbt:
        return []
    entries = []
    cmd = str(nbt["Command"])
    for m in re.finditer(r'\{[^{}]*\}', cmd):
        try:
            d = json.loads(m.group(0))
            t = _flatten_json_text(d)
            if _is_translatable_text(t):
                entries.append({"location": f"{p}/Command", "text": t})
        except json.JSONDecodeError:
            pass
    return entries


def _extract_book_pages(nbt, p: str) -> list[dict]:
    if "pages" not in nbt:
        return []
    entries = []
    for i in range(len(nbt["pages"])):
        t = _parse_text_component(nbt["pages"][i])
        if _is_translatable_text(t):
            entries.append({"location": f"{p}/pages[{i}]", "text": t})
    return entries


def _extract_item(nbt, p: str) -> list[dict]:
    entries = []
    if "tag" not in nbt:
        return entries
    tag = nbt["tag"]
    if "display" in tag:
        d = tag["display"]
        if "Name" in d:
            t = _parse_text_component(d["Name"])
            if _is_translatable_text(t):
                entries.append({"location": f"{p}/display/Name", "text": t})
        if "Lore" in d:
            for i in range(len(d["Lore"])):
                t = _parse_text_component(d["Lore"][i])
                if _is_translatable_text(t):
                    entries.append({"location": f"{p}/display/Lore[{i}]", "text": t})
    if "pages" in tag:
        for i in range(len(tag["pages"])):
            t = _parse_text_component(tag["pages"][i])
            if _is_translatable_text(t):
                entries.append({"location": f"{p}/pages[{i}]", "text": t})
    return entries


def _extract_container(nbt, p: str) -> list[dict]:
    entries = []
    if "CustomName" in nbt:
        t = _parse_text_component(nbt["CustomName"])
        if _is_translatable_text(t):
            entries.append({"location": f"{p}/CustomName", "text": t})
    if "Items" in nbt:
        for i in range(len(nbt["Items"])):
            entries.extend(_extract_item(nbt["Items"][i], f"{p}/Items[{i}]"))
    return entries


def _extract_lectern(nbt, p: str) -> list[dict]:
    if "Book" not in nbt:
        return []
    return _extract_item(nbt["Book"], f"{p}/Book")


def _extract_entity(nbt, p: str) -> list[dict]:
    entries = []
    if "CustomName" in nbt:
        t = _parse_text_component(nbt["CustomName"])
        if _is_translatable_text(t):
            entries.append({"location": f"{p}/CustomName", "text": t})
    for slot in ("ArmorItems", "HandItems"):
        if slot in nbt:
            for i in range(len(nbt[slot])):
                entries.extend(_extract_item(nbt[slot][i], f"{p}/{slot}[{i}]"))
    if "Inventory" in nbt:
        for i in range(len(nbt["Inventory"])):
            entries.extend(_extract_item(nbt["Inventory"][i], f"{p}/Inventory[{i}]"))
    if "Offers" in nbt and "Recipes" in nbt["Offers"]:
        for i, r in enumerate(nbt["Offers"]["Recipes"]):
            for k in ("buy", "buyB", "sell"):
                if k in r:
                    entries.extend(_extract_item(r[k], f"{p}/Offers/Recipes[{i}]/{k}"))
    # 展示实体
    if "text" in nbt:
        t = _parse_text_component(nbt["text"])
        if _is_translatable_text(t):
            entries.append({"location": f"{p}/text", "text": t})
    return entries


def _extract_spawner(nbt, p: str) -> list[dict]:
    entries = []
    try:
        sd = nbt.get("SpawnData", {})
        entity = sd.get("entity", sd)
        if "id" in entity:
            entries.extend(_extract_entity(entity, f"{p}/SpawnData"))
    except Exception:
        pass
    return entries


def _extract_beehive(nbt, p: str) -> list[dict]:
    entries = []
    if "Bees" in nbt:
        for i, bee in enumerate(nbt["Bees"]):
            if "EntityData" in bee:
                entries.extend(_extract_entity(bee["EntityData"], f"{p}/Bees[{i}]"))
    return entries


def _extract_block_entity(nbt, cx: int, cz: int) -> list[dict]:
    be_id = str(nbt.get("id", ""))
    name = be_id.replace("minecraft:", "") if "minecraft:" in be_id else be_id
    x, y, z = int(nbt.get("x", 0)), int(nbt.get("y", 0)), int(nbt.get("z", 0))
    p = f"chunk[{cx},{cz}]/[{x},{y},{z}]"

    if _is_sign(name):
        return _extract_sign(nbt, p)
    if _is_container(name):
        return _extract_container(nbt, p)
    if name in _CMD_BLOCK_NAMES:
        return _extract_command_block(nbt, p)
    if name == "lectern":
        return _extract_lectern(nbt, p)
    if name == "spawner":
        return _extract_spawner(nbt, p)
    if name in ("beehive", "bee_nest"):
        return _extract_beehive(nbt, p)
    return []


def _extract_chunk_texts(nbt, cx: int, cz: int) -> list[dict]:
    entries = []

    def _process_be_list(bes):
        for be in bes:
            try:
                entries.extend(_extract_block_entity(be, cx, cz))
            except Exception:
                continue

    if "block_entities" in nbt:
        _process_be_list(nbt["block_entities"])
    if "sections" in nbt:
        for s in nbt["sections"]:
            if "block_entities" in s:
                _process_be_list(s["block_entities"])
    if "Level" in nbt:
        if "TileEntities" in nbt["Level"]:
            _process_be_list(nbt["Level"]["TileEntities"])
        if "Entities" in nbt["Level"]:
            for e in nbt["Level"]["Entities"]:
                try:
                    eid = str(e.get("id", ""))
                    x, y, z = int(e.get("x", 0)), int(e.get("y", 0)), int(e.get("z", 0))
                    entries.extend(_extract_entity(e, f"chunk[{cx},{cz}]/entity[{x},{y},{z}]"))
                except Exception:
                    continue
    return entries


# ---------------------------------------------------------------------------
# 数据包提取
# ---------------------------------------------------------------------------

def _extract_from_datapacks(dp_dir: Path, map_dir: Path) -> list[dict]:
    entries = []
    cmd_re = re.compile(r'^\s*(tellraw|title|execute)\b', re.IGNORECASE)
    json_re = re.compile(r'\{[^{}]*\}')

    for f in sorted(dp_dir.rglob("*")):
        if not f.is_file() or f.suffix != ".mcfunction":
            continue
        rel = str(f.relative_to(map_dir))
        try:
            for ln, line in enumerate(f.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
                if not cmd_re.match(line):
                    continue
                for m in json_re.finditer(line):
                    try:
                        d = json.loads(m.group(0))
                        t = _flatten_json_text(d)
                        if _is_translatable_text(t):
                            entries.append({"location": f"{rel}:{ln}", "text": t})
                    except json.JSONDecodeError:
                        pass
        except Exception:
            continue
    return entries


# ---------------------------------------------------------------------------
# 记分板提取/写回
# ---------------------------------------------------------------------------

def _extract_scoreboard(dat_path: Path) -> list[dict]:
    entries = []
    try:
        import nbtlib
        nbt = nbtlib.load(str(dat_path))
        data = nbt.get("data", {})
        for obj in data.get("Objectives", []):
            name = str(obj.get("Name", ""))
            disp = obj.get("DisplayName", "")
            t = _parse_text_component(disp)
            if _is_translatable_text(t):
                entries.append({"location": f"scoreboard/Objective/{name}/DisplayName", "text": t})
        for team in data.get("Teams", []):
            name = str(team.get("Name", ""))
            for field in ("DisplayName", "MemberNamePrefix", "MemberNameSuffix"):
                val = team.get(field, "")
                t = _parse_text_component(val)
                if _is_translatable_text(t):
                    entries.append({"location": f"scoreboard/Team/{name}/{field}", "text": t})
    except Exception:
        pass
    return entries


def _apply_scoreboard_translations(dat_path: Path, translations: dict[str, str]) -> bool:
    changed = False
    try:
        import nbtlib
        nbt = nbtlib.load(str(dat_path))
        data = nbt.get("data", {})
        for obj in data.get("Objectives", []):
            name = str(obj.get("Name", ""))
            loc = f"scoreboard/Objective/{name}/DisplayName"
            if loc in translations:
                obj["DisplayName"] = _make_json_text(translations[loc])
                changed = True
        for team in data.get("Teams", []):
            name = str(team.get("Name", ""))
            for field in ("DisplayName", "MemberNamePrefix", "MemberNameSuffix"):
                loc = f"scoreboard/Team/{name}/{field}"
                if loc in translations:
                    team[field] = _make_json_text(translations[loc])
                    changed = True
        if changed:
            nbt.save(str(dat_path))
    except Exception:
        pass
    return changed


# ---------------------------------------------------------------------------
# Bossbar 提取/写回
# ---------------------------------------------------------------------------

def _extract_bossbar(level_dat: Path) -> list[dict]:
    entries = []
    try:
        import nbtlib
        nbt = nbtlib.load(str(level_dat))
        data = nbt.get("data", {})
        for name, ev in data.get("BossEvent", {}).items():
            if "Name" in ev:
                t = _parse_text_component(ev["Name"])
                if _is_translatable_text(t):
                    entries.append({"location": f"bossbar/{name}/Name", "text": t})
    except Exception:
        pass
    return entries


def _apply_bossbar_translations(level_dat: Path, translations: dict[str, str]) -> bool:
    changed = False
    try:
        import nbtlib
        nbt = nbtlib.load(str(level_dat))
        data = nbt.get("data", {})
        for name, ev in data.get("BossEvent", {}).items():
            loc = f"bossbar/{name}/Name"
            if loc in translations and "Name" in ev:
                ev["Name"] = _make_json_text(translations[loc])
                changed = True
        if changed:
            nbt.save(str(level_dat))
    except Exception:
        pass
    return changed


# ---------------------------------------------------------------------------
# 写回：方块实体
# ---------------------------------------------------------------------------

def _apply_sign(nbt, p: str, tr: dict[str, str]) -> bool:
    changed = False
    for side in ("front_text", "back_text"):
        if side in nbt and "messages" in nbt[side]:
            msgs = nbt[side]["messages"]
            for i in range(len(msgs)):
                loc = f"{p}/{side}/messages[{i}]"
                if loc in tr:
                    msgs[i] = _make_json_text(tr[loc])
                    changed = True
    for i in range(1, 5):
        k = f"Text{i}"
        loc = f"{p}/{k}"
        if loc in tr and k in nbt:
            nbt[k] = _make_json_text(tr[loc])
            changed = True
    return changed


def _apply_command(nbt, p: str, tr: dict[str, str]) -> bool:
    import nbtlib
    loc = f"{p}/Command"
    if loc not in tr or "Command" not in nbt:
        return False
    cmd = str(nbt["Command"])
    zh = tr[loc]
    for m in re.finditer(r'\{[^{}]*\}', cmd):
        try:
            d = json.loads(m.group(0))
            if "text" in d:
                d["text"] = zh
                nbt["Command"] = nbtlib.String(cmd[:m.start()] + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + cmd[m.end():])
                return True
        except json.JSONDecodeError:
            pass
    return False


def _apply_book(nbt, p: str, tr: dict[str, str]) -> bool:
    if "pages" not in nbt:
        return False
    changed = False
    for i in range(len(nbt["pages"])):
        loc = f"{p}/pages[{i}]"
        if loc in tr:
            nbt["pages"][i] = _make_json_text(tr[loc])
            changed = True
    return changed


def _apply_item(nbt, p: str, tr: dict[str, str]) -> bool:
    changed = False
    if "tag" not in nbt:
        return False
    tag = nbt["tag"]
    if "display" in tag:
        d = tag["display"]
        loc = f"{p}/display/Name"
        if loc in tr and "Name" in d:
            d["Name"] = _make_json_text(tr[loc])
            changed = True
        if "Lore" in d:
            for i in range(len(d["Lore"])):
                loc = f"{p}/display/Lore[{i}]"
                if loc in tr:
                    d["Lore"][i] = _make_json_text(tr[loc])
                    changed = True
    if "pages" in tag:
        for i in range(len(tag["pages"])):
            loc = f"{p}/pages[{i}]"
            if loc in tr:
                tag["pages"][i] = _make_json_text(tr[loc])
                changed = True
    return changed


def _apply_container(nbt, p: str, tr: dict[str, str]) -> bool:
    changed = False
    loc = f"{p}/CustomName"
    if loc in tr and "CustomName" in nbt:
        nbt["CustomName"] = _make_json_text(tr[loc])
        changed = True
    if "Items" in nbt:
        for i in range(len(nbt["Items"])):
            changed |= _apply_item(nbt["Items"][i], f"{p}/Items[{i}]", tr)
    return changed


def _apply_entity(nbt, p: str, tr: dict[str, str]) -> bool:
    changed = False
    loc = f"{p}/CustomName"
    if loc in tr and "CustomName" in nbt:
        nbt["CustomName"] = _make_json_text(tr[loc])
        changed = True
    for slot in ("ArmorItems", "HandItems"):
        if slot in nbt:
            for i in range(len(nbt[slot])):
                changed |= _apply_item(nbt[slot][i], f"{p}/{slot}[{i}]", tr)
    if "Inventory" in nbt:
        for i in range(len(nbt["Inventory"])):
            changed |= _apply_item(nbt["Inventory"][i], f"{p}/Inventory[{i}]", tr)
    if "Offers" in nbt and "Recipes" in nbt["Offers"]:
        for i, r in enumerate(nbt["Offers"]["Recipes"]):
            for k in ("buy", "buyB", "sell"):
                if k in r:
                    changed |= _apply_item(r[k], f"{p}/Offers/Recipes[{i}]/{k}", tr)
    # 展示实体
    loc = f"{p}/text"
    if loc in tr and "text" in nbt:
        nbt["text"] = _make_json_text(tr[loc])
        changed = True
    return changed


def _apply_spawner(nbt, p: str, tr: dict[str, str]) -> bool:
    try:
        sd = nbt.get("SpawnData", {})
        entity = sd.get("entity", sd)
        if "id" in entity:
            return _apply_entity(entity, f"{p}/SpawnData", tr)
    except Exception:
        pass
    return False


def _apply_beehive(nbt, p: str, tr: dict[str, str]) -> bool:
    changed = False
    if "Bees" in nbt:
        for i, bee in enumerate(nbt["Bees"]):
            if "EntityData" in bee:
                changed |= _apply_entity(bee["EntityData"], f"{p}/Bees[{i}]", tr)
    return changed


# ---------------------------------------------------------------------------
# 写回：数据包
# ---------------------------------------------------------------------------

def _apply_datapack_translations(dp_dir: Path, map_dir: Path, translations: dict[str, str]) -> int:
    cmd_re = re.compile(r'^\s*(tellraw|title|execute)\b', re.IGNORECASE)
    json_re = re.compile(r'\{[^{}]*\}')
    modified = 0

    for f in sorted(dp_dir.rglob("*")):
        if not f.is_file() or f.suffix != ".mcfunction":
            continue
        rel = str(f.relative_to(map_dir))
        try:
            lines = f.read_text(encoding="utf-8-sig", errors="replace").splitlines(keepends=True)
        except Exception:
            continue

        file_changed = False
        for i, line in enumerate(lines):
            if not cmd_re.match(line):
                continue
            for m in json_re.finditer(line):
                loc = f"{rel}:{i + 1}"
                if loc not in translations:
                    continue
                try:
                    d = json.loads(m.group(0))
                    if "text" in d:
                        d["text"] = translations[loc]
                        new_json = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
                        lines[i] = line[:m.start()] + new_json + line[m.end():]
                        line = lines[i]
                        file_changed = True
                except json.JSONDecodeError:
                    pass

        if file_changed:
            f.write_text("".join(lines), encoding="utf-8")
            modified += 1
    return modified


# ---------------------------------------------------------------------------
# 写回：chunk 级别分发
# ---------------------------------------------------------------------------

def _apply_translations_to_chunk(nbt, cx: int, cz: int, tr: dict[str, str]) -> bool:
    changed = False

    def _process(bes):
        nonlocal changed
        for be in bes:
            try:
                be_id = str(be.get("id", ""))
                name = be_id.replace("minecraft:", "") if "minecraft:" in be_id else be_id
                x, y, z = int(be.get("x", 0)), int(be.get("y", 0)), int(be.get("z", 0))
                p = f"chunk[{cx},{cz}]/[{x},{y},{z}]"

                if _is_sign(name):
                    changed |= _apply_sign(be, p, tr)
                elif name in _CMD_BLOCK_NAMES:
                    changed |= _apply_command(be, p, tr)
                elif name == "lectern":
                    changed |= _apply_book(be, p, tr)
                elif _is_container(name):
                    changed |= _apply_container(be, p, tr)
                elif name == "spawner":
                    changed |= _apply_spawner(be, p, tr)
                elif name in ("beehive", "bee_nest"):
                    changed |= _apply_beehive(be, p, tr)
            except Exception:
                continue

    if "block_entities" in nbt:
        _process(nbt["block_entities"])
    if "sections" in nbt:
        for s in nbt["sections"]:
            if "block_entities" in s:
                _process(s["block_entities"])
    if "Level" in nbt:
        if "TileEntities" in nbt["Level"]:
            _process(nbt["Level"]["TileEntities"])
        # 实体写回
        if "Entities" in nbt["Level"]:
            for e in nbt["Level"]["Entities"]:
                try:
                    eid = str(e.get("id", ""))
                    x, y, z = int(e.get("x", 0)), int(e.get("y", 0)), int(e.get("z", 0))
                    p = f"chunk[{cx},{cz}]/entity[{x},{y},{z}]"
                    changed |= _apply_entity(e, p, tr)
                except Exception:
                    continue
    return changed


# ---------------------------------------------------------------------------
# 工作流管理器主类
# ---------------------------------------------------------------------------

class JavamapWorkflowManager:

    def __init__(self, project_info: dict, main_window):
        self.project_info = project_info
        self.main_window = main_window
        self.map_dir = Path(project_info["source_dir"])
        self._extracted_entries: list[dict] = []
        self._region_chunks: dict[Path, list[tuple[int, int, dict]]] = {}

    def _log(self, msg: str, level: str = "INFO"):
        self.main_window.log_message(msg, level)

    def _update_status(self, msg: str):
        def _do():
            wb = getattr(self.main_window, "workbench_instance", None)
            if wb and hasattr(wb, "status_label"):
                try:
                    wb.status_label.config(text=msg)
                except Exception:
                    pass
        try:
            self.main_window.root.after(0, _do)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 提取阶段
    # ------------------------------------------------------------------

    def _resolve_map_dir(self) -> Path:
        """解析地图目录：支持 zip 文件、嵌套目录、saves 目录。"""
        p = self.map_dir

        # 1. 如果是 zip 文件，解压到同名目录
        if p.is_file() and p.suffix.lower() == '.zip':
            extract_dir = p.parent / p.stem
            if not extract_dir.exists():
                self._log(f"正在解压 {p.name}...", "INFO")
                import zipfile
                with zipfile.ZipFile(str(p), 'r') as zf:
                    zf.extractall(str(extract_dir))
            p = extract_dir

        if not p.is_dir():
            return p

        # 2. 检查当前目录是否有 region/
        if (p / "region").is_dir():
            return p

        # 3. 检查是否是 saves 目录（包含多个世界）
        saves_worlds = [d for d in p.iterdir() if d.is_dir() and (d / "region").is_dir()]
        if len(saves_worlds) == 1:
            self._log(f"自动检测到地图: {saves_worlds[0].name}", "INFO")
            return saves_worlds[0]

        # 4. 检查子目录（zip 解压后常见一层嵌套）
        sub_dirs = [d for d in p.iterdir() if d.is_dir()]
        for sd in sub_dirs:
            if (sd / "region").is_dir():
                self._log(f"自动检测到地图: {sd.name}", "INFO")
                return sd

        return p

    def run_extraction_phase(self):
        try:
            # 检查路径是否有效
            if not self.map_dir or str(self.map_dir) == '.':
                self._log("错误：未指定地图路径。请在上方输入框中选择地图文件夹或 .zip 文件。", "CRITICAL")
                self.main_window.root.after(
                    0, lambda: ui_utils.show_error(
                        "路径为空",
                        "请先选择地图存档文件夹或 .zip 文件。\n\n"
                        "点击输入框右侧的「浏览」按钮选择路径。"))
                self.main_window.root.after(0, self.main_window._show_welcome_view)
                return

            # 自动解析地图目录
            self.map_dir = self._resolve_map_dir()

            if not self.map_dir.is_dir():
                raise FileNotFoundError(f"地图文件夹不存在: {self.map_dir}")

            self._log(f"正在扫描地图: {self.map_dir.name}", "INFO")

            try:
                import nbtlib
            except ImportError:
                self._log("错误: nbtlib 未安装。请运行 pip install nbtlib", "CRITICAL")
                self.main_window.root.after(0, self.main_window._show_welcome_view)
                return

            # 区域文件
            region_files = []
            for rd in self.map_dir.rglob("region"):
                if rd.is_dir():
                    region_files.extend(rd.glob("*.mca"))

            if not region_files:
                raise FileNotFoundError(
                    f"未在 {self.map_dir} 中找到区域文件 (.mca)。\n\n"
                    "请确认路径指向以下之一：\n"
                    "  1. 地图存档文件夹（包含 region/ 子目录）\n"
                    "  2. .zip 压缩包（会自动解压）\n"
                    "  3. saves 目录（包含地图文件夹）"
                )

            self._log(f"找到 {len(region_files)} 个区域文件", "INFO")
            all_entries = []
            self._region_chunks = {}

            for i, rp in enumerate(sorted(region_files)):
                rel = rp.relative_to(self.map_dir)
                self._log(f"  扫描 {rel} ...", "INFO")
                self._update_status(f"正在扫描区域文件 ({i + 1}/{len(region_files)})...")
                try:
                    chunks = _read_region_chunks(rp)
                    self._region_chunks[rp] = chunks
                    for cx, cz, nbt in chunks:
                        for e in _extract_chunk_texts(nbt, cx, cz):
                            e["region_file"] = str(rel)
                            all_entries.append(e)
                except Exception as ex:
                    self._log(f"    跳过 {rel}: {ex}", "WARNING")

            # 数据包
            dp_dir = self.map_dir / "datapacks"
            if dp_dir.is_dir():
                self._log("  扫描数据包...", "INFO")
                all_entries.extend(_extract_from_datapacks(dp_dir, self.map_dir))

            # 记分板
            sb_path = self.map_dir / "data" / "scoreboard.dat"
            if sb_path.is_file():
                self._log("  扫描记分板...", "INFO")
                all_entries.extend(_extract_scoreboard(sb_path))

            # Bossbar
            lv_path = self.map_dir / "level.dat"
            if lv_path.is_file():
                self._log("  扫描 Bossbar...", "INFO")
                all_entries.extend(_extract_bossbar(lv_path))

            self._extracted_entries = all_entries
            self._log(f"共提取到 {len(all_entries)} 条可翻译文本", "SUCCESS")

            if not all_entries:
                self._log("未在地图中发现需要翻译的文本内容。", "WARNING")
                self.main_window.root.after(
                    0, lambda: ui_utils.show_info("扫描完成", "未在地图中发现需要翻译的文本内容。"))
                self.main_window.root.after(0, self.main_window._show_welcome_view)
                return

            self._log("正在打开工作台...", "INFO")
            self.main_window.root.after(
                0, self.main_window._launch_javamap_workbench, self._build_workbench_data())

        except Exception as e:
            logging.error(f"地图扫描失败: {e}", exc_info=True)
            self._log(f"错误: {e}", "CRITICAL")
            self.main_window.root.after(
                0, lambda err=e: ui_utils.show_error("扫描失败", f"扫描地图时发生错误:\n{err}"))
            self.main_window.root.after(0, self.main_window._show_welcome_view)

    def _build_workbench_data(self) -> dict:
        seen = set()
        items = []
        for e in self._extracted_entries:
            k = (e.get("region_file", ""), e["location"], e["text"])
            if k in seen:
                continue
            seen.add(k)
            items.append({"key": e["location"], "en": e["text"], "zh": "", "source": e.get("region_file", "")})
        return {"map_texts": {"display_name": f"{self.map_dir.name} / 地图文本", "jar_name": self.map_dir.name, "items": items}}

    # ------------------------------------------------------------------
    # 写回阶段
    # ------------------------------------------------------------------

    def run_build_phase(self, final_workbench_data: dict):
        try:
            self._log("开始写入翻译到地图文件...", "INFO")
            self._update_status("正在写入翻译...")

            tr = {}
            for ns in final_workbench_data.values():
                for item in ns.get("items", []):
                    zh, key, en = item.get("zh", "").strip(), item.get("key", "").strip(), item.get("en", "").strip()
                    if zh and key and zh != en:
                        tr[key] = zh

            if not tr:
                self._log("没有需要写入的翻译。", "WARNING")
                self.main_window.root.after(0, lambda: ui_utils.show_info("提示", "没有需要写入的翻译。"))
                return

            self._log(f"共 {len(tr)} 条翻译需要写入", "INFO")

            # 直接原地替换
            base = self.map_dir

            # --- 区域文件写回 ---
            region_groups = self._group_by_region(tr)
            modified_regions = 0
            for rel, region_tr in region_groups.items():
                rp = base / rel
                if not rp.exists():
                    rp = self.map_dir / rel
                chunks = self._region_chunks.get(rp, [])
                if not chunks:
                    continue
                chunk_changed = False
                for cx, cz, nbt in chunks:
                    chunk_changed |= _apply_translations_to_chunk(nbt, cx, cz, region_tr)
                if chunk_changed:
                    _write_region_file(rp, chunks)
                    modified_regions += 1
                    self._log(f"  已写入区域: {rel}", "INFO")

            # --- 数据包写回 ---
            dp_dir = base / "datapacks"
            dp_modified = 0
            if dp_dir.is_dir():
                dp_modified = _apply_datapack_translations(dp_dir, base, tr)
                if dp_modified:
                    self._log(f"  已写入 {dp_modified} 个数据包文件", "INFO")

            # --- 记分板写回 ---
            sb_path = base / "data" / "scoreboard.dat"
            sb_changed = False
            if sb_path.is_file():
                sb_changed = _apply_scoreboard_translations(sb_path, tr)
                if sb_changed:
                    self._log("  已写入记分板", "INFO")

            # --- Bossbar 写回 ---
            lv_path = base / "level.dat"
            bb_changed = False
            if lv_path.is_file():
                bb_changed = _apply_bossbar_translations(lv_path, tr)
                if bb_changed:
                    self._log("  已写入 Bossbar", "INFO")

            total = modified_regions + dp_modified + (1 if sb_changed else 0) + (1 if bb_changed else 0)
            self._log(f"写入完成！共修改 {total} 个文件/区域", "SUCCESS")
            self._update_status(f"翻译完成！修改 {total} 个文件/区域")

            self.main_window.root.after(
                0, lambda: ui_utils.show_info(
                    "完成",
                    f"已将翻译原地写入地图文件。\n\n"
                    f"修改区域文件: {modified_regions}\n"
                    f"修改数据包: {dp_modified}\n"
                    f"记分板: {'已更新' if sb_changed else '无变更'}\n"
                    f"Bossbar: {'已更新' if bb_changed else '无变更'}\n"
                    f"翻译条目: {len(tr)}\n"
                    f"地图路径: {base}"))

        except Exception as e:
            logging.error(f"写入翻译失败: {e}", exc_info=True)
            self._log(f"写入失败: {e}", "CRITICAL")
            self._update_status(f"写入失败: {e}")
            self.main_window.root.after(
                0, lambda err=e: ui_utils.show_error("写入失败", f"写入翻译时发生错误:\n{err}"))

    def _group_by_region(self, tr: dict[str, str]) -> dict[str, dict[str, str]]:
        groups: dict[str, dict[str, str]] = {}
        dp_tr: dict[str, str] = {}

        for loc, zh in tr.items():
            m = re.match(r'chunk\[(-?\d+),(-?\d+)\]', loc)
            if not m:
                dp_tr[loc] = zh
                continue
            cx, cz = int(m.group(1)), int(m.group(2))
            rname = f"r.{cx >> 5}.{cz >> 5}.mca"
            for rp in self._region_chunks:
                if rp.name == rname:
                    rel = str(rp.relative_to(self.map_dir))
                    groups.setdefault(rel, {})[loc] = zh
                    break

        # 数据包/记分板/bossbar 翻译也加入 map_dir 对应的组
        if dp_tr:
            groups.setdefault("__datapack__", {}).update(dp_tr)

        return groups
