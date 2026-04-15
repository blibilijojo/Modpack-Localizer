"""跨设备项目同步：中继服务 URL 规范化、健康检查、房间上传/下载。"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import string
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "Modpack-Localizer/ProjectSyncRelay"
_RELAY_LOG_TAG = "[中继同步]"
_RELAY_HTTP_TAG = "[中继HTTP]"
ROOM_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{4,48}$")

RELAY_SERVICE_NAME = "modpack-localizer-project-sync-relay"
# 全量上传单分片 UTF-8 字节上限（须小于 deno 侧 KV_MAX_UPLOAD_PART_BYTES）
RELAY_FULL_UPLOAD_CHUNK_BYTES = 56_000
RELAY_UPLOAD_PART_MAX_WORKERS = 8
RELAY_PREFLIGHT_CACHE_TTL_SEC = 120.0

_relay_preflight_cache: Dict[str, Tuple[float, Tuple[bool, str]]] = {}

_RELAY_LEGACY_HEALTH_HINT = (
    "该 URL 的 /health 仍是旧版 Deno 中继（含 version 字段、且无 capabilities.chunked_upload），"
    "当前仓库的 project_sync_relay.ts 未真正部署到此域名。"
    "请在 Cloudflare Workers 部署新脚本，并将自定义域名指向该 Worker。"
)


def _relay_health_is_legacy_official(data: dict) -> bool:
    """service 为本项目但缺少当前脚本在 /health 中声明的 chunked_upload（典型为线上 0.1.0 旧部署）。"""
    if data.get("service") != RELAY_SERVICE_NAME:
        return False
    caps = data.get("capabilities")
    return not (isinstance(caps, dict) and caps.get("chunked_upload") is True)


def _relay_preview(text: str, limit: int = 900) -> str:
    if not text:
        return ""
    t = text.replace("\r", " ").replace("\n", " ")
    return t if len(t) <= limit else t[:limit] + "…"


def _relay_log_config_context(phase: str, base_raw: str, *, room_id: Optional[str] = None) -> None:
    """记录配置中的中继 URL 与解析后的 API 根（便于排查路径误填）。"""
    try:
        normalized = normalize_project_sync_relay_url(base_raw) if (base_raw or "").strip() else ""
        api_root = _relay_api_root(base_raw) if (base_raw or "").strip() else ""
    except ValueError as e:
        logger.warning(
            "%s 阶段=%s 中继地址解析失败: %s 原始=%r",
            _RELAY_LOG_TAG,
            phase,
            e,
            (base_raw or "")[:300],
        )
        return
    logger.info(
        "%s 阶段=%s 填写地址=%r 规范化=%r API根=%r 房间=%r",
        _RELAY_LOG_TAG,
        phase,
        (base_raw or "")[:400],
        normalized[:400] if normalized else "",
        api_root[:400] if api_root else "",
        room_id,
    )


def _relay_log_tab_state_brief(label: str, tab_state: dict) -> None:
    """不记录完整 JSON，只记体积与命名空间数量。"""
    try:
        raw = json.dumps(tab_state, ensure_ascii=False)
        size_b = len(raw.encode("utf-8"))
    except Exception as e:
        logger.warning("%s %s 无法序列化标签状态: %s", _RELAY_LOG_TAG, label, e)
        return
    wb = tab_state.get("workbench_state") or {}
    wd = wb.get("workbench_data") if isinstance(wb, dict) else None
    n_ns = len(wd) if isinstance(wd, dict) else 0
    logger.info(
        "%s %s 序列化字节=%s 命名空间数=%s 项目名=%r 项目类型=%r",
        _RELAY_LOG_TAG,
        label,
        size_b,
        n_ns,
        tab_state.get("project_name"),
        tab_state.get("project_type"),
    )


def _relay_request_with_log(
    label: str,
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    kw = dict(kwargs)
    session = kw.pop("session", None)
    t0 = time.perf_counter()
    logger.info("%s %s 方法=%s URL=%s 参数键=%s", _RELAY_HTTP_TAG, label, method, url, list(kw.keys()))
    try:
        if method.upper() == "GET":
            resp = (session.get if session else requests.get)(url, **kw)
        elif method.upper() == "POST":
            resp = (session.post if session else requests.post)(url, **kw)
        else:
            raise ValueError(f"不支持的 HTTP 方法: {method}")
    except requests.RequestException as e:
        dt = (time.perf_counter() - t0) * 1000
        logger.warning(
            "%s %s 方法=%s URL=%s 请求异常 耗时毫秒=%.0f 错误=%r",
            _RELAY_HTTP_TAG,
            label,
            method,
            url,
            dt,
            e,
        )
        raise
    dt = (time.perf_counter() - t0) * 1000
    logger.info(
        "%s %s 方法=%s 状态码=%s 最终URL=%s 耗时毫秒=%.0f",
        _RELAY_HTTP_TAG,
        label,
        method,
        resp.status_code,
        getattr(resp, "url", url),
        dt,
    )
    if resp.status_code >= 400:
        logger.warning(
            "%s %s 响应体(截断): %s",
            _RELAY_HTTP_TAG,
            label,
            _relay_preview(resp.text, 1200),
        )
    return resp


def _summarize_publish_plan(plan: Dict[str, Any]) -> str:
    """用于日志：避免打印整份 patch。"""
    mode = plan.get("mode")
    if mode != "incremental":
        return "—"
    patch = plan.get("patch") or {}
    ws = patch.get("workbench_state") if isinstance(patch.get("workbench_state"), dict) else {}
    wd = ws.get("workbench_data") if isinstance(ws.get("workbench_data"), dict) else {}
    ns_keys = list(wd.keys())
    sample = ns_keys[:40]
    return json.dumps(
        {
            "模式": "增量",
            "基准版本": plan.get("base_rev"),
            "删除命名空间数": len(plan.get("remove_namespaces") or []),
            "补丁顶层键": list(patch.keys()),
            "工作台命名空间数": len(ns_keys),
            "命名空间示例": sample,
        },
        ensure_ascii=False,
    )


def normalize_project_sync_relay_url(raw: str) -> str:
    """
    将用户输入整理为「站点根」形式（无末尾 /），便于拼接 /health 等路径。
    若缺少协议则默认补全为 https://。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅支持 http 或 https 地址")
    if not parsed.netloc:
        raise ValueError("无效的网址：缺少主机名")
    # 保留 path/query（子路径部署时 /health 挂在子路径下）
    path = parsed.path or ""
    path = path.rstrip("/")
    rebuilt = urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            path,
            "",  # params
            "",  # query — 健康检查不应依赖查询串
            "",  # fragment
        )
    )
    return rebuilt.rstrip("/") if not path else rebuilt


def _relay_api_root(base_url: str) -> str:
    """
    中继上用于 /rooms、/incremental 等 API 的根 URL。
    若用户误把「健康检查地址」填成根（含 .../health），会去掉末尾 /health，
    避免出现 https://host/health/rooms/... 导致中继返回 not_found。
    """
    u = normalize_project_sync_relay_url(base_url)
    if not u:
        return ""
    parsed = urlparse(u)
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/health"):
        path = path[: -len("/health")].rstrip("/")
    elif path == "/health":
        path = ""
    rebuilt = urlunparse(
        (parsed.scheme, parsed.netloc.lower(), path, "", "", ""),
    )
    return rebuilt.rstrip("/")


def relay_health_url_for_probe(raw: str) -> str:
    """检测连接用的完整 health URL（支持根已含 /health）。"""
    u = normalize_project_sync_relay_url(raw)
    if not u:
        return ""
    pth = (urlparse(u).path or "").rstrip("/")
    if pth == "/health" or pth.endswith("/health"):
        return u.rstrip("/")
    return f"{u.rstrip('/')}/health"


def probe_project_sync_relay(base_url: str, timeout: float = 12.0) -> Tuple[bool, str]:
    """
    请求中继的 /health，判断是否可用。
    返回 (是否成功, 面向用户的说明文字)。
    """
    try:
        url = relay_health_url_for_probe(base_url)
    except ValueError as e:
        return False, str(e)

    if not url:
        return False, "请先填写中继站点地址"
    _relay_log_config_context("健康检查", base_url)
    try:
        resp = _relay_request_with_log(
            "健康检查",
            "GET",
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except requests.RequestException as e:
        logger.warning("%s 健康检查请求失败: %s", _RELAY_LOG_TAG, e)
        return False, f"无法连接中继：{e}"

    if resp.status_code != 200:
        logger.warning(
            "%s 健康检查非200 状态码=%s 响应体=%r",
            _RELAY_LOG_TAG,
            resp.status_code,
            _relay_preview(resp.text, 500),
        )
        return False, f"中继返回 HTTP {resp.status_code}"

    try:
        data: Any = resp.json()
    except ValueError:
        return False, "中继未返回有效的 JSON（请确认地址指向本项目的 Deno 中继）"

    if not isinstance(data, dict):
        return False, "中继响应格式异常"

    if data.get("ok") is not True:
        err = data.get("error") or data.get("message") or "unknown"
        return False, f"中继报告不可用：{err}"

    if _relay_health_is_legacy_official(data):
        logger.warning(
            "%s 健康检查拒绝旧版中继 响应字段=%s",
            _RELAY_LOG_TAG,
            list(data.keys()),
        )
        return False, _RELAY_LEGACY_HEALTH_HINT

    service = data.get("service") or "relay"
    logger.info(
        "%s 健康检查通过 服务=%r 响应字段=%s",
        _RELAY_LOG_TAG,
        service,
        list(data.keys()),
    )
    tail = f" ({service})"
    hint = ""
    try:
        if normalize_project_sync_relay_url(base_url) != _relay_api_root(base_url):
            hint = "（已自动忽略路径中的 /health；房间 API 使用站点根路径）"
    except ValueError:
        pass
    return True, "连接成功" + tail + hint


def relay_preflight_for_upload(base_url: str, timeout: float = 12.0) -> Tuple[bool, str]:
    """
    上传 / 拉取前调用：与 probe_project_sync_relay 相同校验，但对同一 api_root 在 TTL 内只 GET 一次 /health。
    """
    try:
        key = _relay_api_root(base_url)
    except ValueError as e:
        return False, str(e)
    if not key:
        return False, "请先在「设置 → 外部服务」填写中继站点根地址"
    now = time.time()
    hit = _relay_preflight_cache.get(key)
    if hit and (now - hit[0]) < RELAY_PREFLIGHT_CACHE_TTL_SEC:
        return hit[1]
    result = probe_project_sync_relay(base_url, timeout=timeout)
    if result[0]:
        _relay_preflight_cache[key] = (now, result)
    return result


def _relay_upload_part_worker(
    index: int,
    url: str,
    body: bytes,
    headers: Dict[str, str],
    timeout: float,
) -> Tuple[int, Optional[requests.Response], Optional[str]]:
    try:
        resp = requests.post(url, data=body, headers=headers, timeout=timeout)
        return index, resp, None
    except requests.RequestException as e:
        logger.warning("%s 上传分片 索引=%s 请求异常 错误=%r", _RELAY_HTTP_TAG, index, e)
        return index, None, str(e)


def suggest_room_id() -> str:
    """生成可读房间号（小写字母与数字，形如 ab12-cd34）。"""
    alphabet = string.ascii_lowercase + string.digits
    a = "".join(secrets.choice(alphabet) for _ in range(4))
    b = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{a}-{b}"


def parse_room_id(room_id: str) -> Tuple[Optional[str], str]:
    rid = (room_id or "").strip()
    if not ROOM_ID_PATTERN.match(rid):
        return None, "房间号需为 4～48 位：字母、数字、下划线或连字符"
    return rid, ""


def _utf8_byte_chunks(text: str, max_bytes: int = RELAY_FULL_UPLOAD_CHUNK_BYTES) -> List[str]:
    """按 UTF-8 字节切分，不在多字节字符中间截断。默认见 RELAY_FULL_UPLOAD_CHUNK_BYTES（低于 Deno KV 单条上限）。"""
    raw = text.encode("utf-8")
    out: List[str] = []
    i = 0
    n = len(raw)
    while i < n:
        end = min(i + max_bytes, n)
        if end < n:
            while end > i and (raw[end] & 0b1100_0000) == 0b1000_0000:
                end -= 1
            if end == i:
                end = min(i + max_bytes, n)
        out.append(raw[i:end].decode("utf-8"))
        i = end
    return out


def _relay_base_path(base_url: str) -> str:
    return _relay_api_root(base_url).rstrip("/")


def _hash_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def compute_ns_hashes_from_state(tab_state: dict) -> Dict[str, str]:
    wb = tab_state.get("workbench_state") or {}
    wd = wb.get("workbench_data")
    if not isinstance(wd, dict):
        return {}
    return {str(k): _hash_json(v) for k, v in wd.items()}


def _fingerprint_aux(tab_state: dict) -> Dict[str, str]:
    wb = tab_state.get("workbench_state") or {}
    nf = wb.get("namespace_formats") if isinstance(wb.get("namespace_formats"), dict) else {}
    ref = wb.get("raw_english_files") if isinstance(wb.get("raw_english_files"), dict) else {}
    pi = tab_state.get("project_info") if isinstance(tab_state.get("project_info"), dict) else {}
    ns_sum = tab_state.get("namespace_summary")
    return {
        "nf": _hash_json(nf),
        "ref": _hash_json(ref),
        "pi": _hash_json(pi),
        "sum": _hash_json(ns_sum if ns_sum is not None else []),
    }


def tab_relay_fingerprint_write(tab: Any, room_id: str, remote_rev: int, tab_state: dict) -> None:
    """在成功上传/拉取后更新标签页上的中继同步指纹（用于后续增量）。"""
    logger.info(
        "%s 写入同步指纹 房间=%s 远端版本=%s",
        _RELAY_LOG_TAG,
        room_id,
        remote_rev,
    )
    _relay_log_tab_state_brief("指纹写入", tab_state)
    tab._relay_sync_room = room_id
    tab._relay_sync_remote_rev = int(remote_rev)
    tab._relay_ns_hashes = compute_ns_hashes_from_state(tab_state)
    fp = _fingerprint_aux(tab_state)
    tab._relay_nf_hash = fp["nf"]
    tab._relay_ref_hash = fp["ref"]
    tab._relay_pi_hash = fp["pi"]
    tab._relay_sum_hash = fp["sum"]
    tab._relay_project_name = tab_state.get("project_name")
    tab._relay_project_type = tab_state.get("project_type")
    wb = tab_state.get("workbench_state") or {}
    tab._relay_curr_path = wb.get("current_project_path")


def plan_tab_publish_strategy(
    tab: Any,
    room_id: str,
    tab_state: dict,
    *,
    ratio: float = 0.55,
) -> Dict[str, Any]:
    """
    决定本次上传为 full / incremental / noop。
    返回 {"mode":"full"} | {"mode":"noop"} | {"mode":"incremental", "base_rev", "patch", "remove_namespaces"}
    """
    synced = getattr(tab, "_relay_sync_room", None)
    rev = getattr(tab, "_relay_sync_remote_rev", None)
    prev_ns = getattr(tab, "_relay_ns_hashes", None)
    if (
        synced != room_id
        or not isinstance(rev, int)
        or rev < 1
        or not isinstance(prev_ns, dict)
        or len(prev_ns) == 0
    ):
        logger.info(
            "%s 发布策略=全量 原因=无增量上下文 已同步房间=%r 目标房间=%r 远端版本=%r 上次命名空间数=%r",
            _RELAY_LOG_TAG,
            synced,
            room_id,
            rev,
            len(prev_ns) if isinstance(prev_ns, dict) else None,
        )
        return {"mode": "full"}

    curr_hashes = compute_ns_hashes_from_state(tab_state)
    prev_keys = set(prev_ns.keys())
    curr_keys = set(curr_hashes.keys())
    changed = [k for k in curr_keys if prev_ns.get(k) != curr_hashes[k]]
    new_k = [k for k in curr_keys if k not in prev_ns]
    removed = [k for k in prev_keys if k not in curr_keys]
    touch = set(changed) | set(new_k) | set(removed)
    denom = max(len(prev_keys), len(curr_keys), 1)
    if denom >= 6 and len(touch) / denom >= ratio:
        logger.info(
            "%s 发布策略=全量 原因=变更比例过高 变更数=%s 基准数=%s 比例=%s",
            _RELAY_LOG_TAG,
            len(touch),
            denom,
            ratio,
        )
        return {"mode": "full"}
    if len(touch) > 120:
        logger.info("%s 发布策略=全量 原因=变更条目过多 变更数=%s", _RELAY_LOG_TAG, len(touch))
        return {"mode": "full"}

    wb = tab_state.get("workbench_state") or {}
    if not isinstance(wb, dict):
        return {"mode": "full"}

    workbench_data: Dict[str, Any] = {}
    for k in list(changed) + list(new_k):
        wd = wb.get("workbench_data")
        if isinstance(wd, dict) and k in wd:
            workbench_data[k] = wd[k]

    ws_patch: Dict[str, Any] = {}
    if workbench_data:
        ws_patch["workbench_data"] = workbench_data

    fp = _fingerprint_aux(tab_state)
    if fp["nf"] != getattr(tab, "_relay_nf_hash", None):
        ws_patch["namespace_formats"] = wb.get("namespace_formats") or {}
    if fp["ref"] != getattr(tab, "_relay_ref_hash", None):
        ws_patch["raw_english_files"] = wb.get("raw_english_files") or {}
    cp = wb.get("current_project_path")
    if cp != getattr(tab, "_relay_curr_path", None):
        ws_patch["current_project_path"] = cp

    patch: Dict[str, Any] = {}
    if tab_state.get("project_name") != getattr(tab, "_relay_project_name", None):
        patch["project_name"] = tab_state.get("project_name")
    if tab_state.get("project_type") != getattr(tab, "_relay_project_type", None):
        patch["project_type"] = tab_state.get("project_type")
    if fp["pi"] != getattr(tab, "_relay_pi_hash", None):
        patch["project_info"] = tab_state.get("project_info") or {}
    if fp["sum"] != getattr(tab, "_relay_sum_hash", None):
        patch["namespace_summary"] = tab_state.get("namespace_summary") or []

    if ws_patch:
        patch["workbench_state"] = ws_patch

    if not patch and not removed:
        logger.info("%s 发布策略=跳过 原因=无补丁且无命名空间删除", _RELAY_LOG_TAG)
        return {"mode": "noop"}

    inc_plan: Dict[str, Any] = {
        "mode": "incremental",
        "base_rev": rev,
        "patch": patch,
        "remove_namespaces": removed,
    }
    logger.info("%s 发布策略=增量 细节=%s", _RELAY_LOG_TAG, _summarize_publish_plan(inc_plan))
    return inc_plan


def _response_rev(data: dict) -> Optional[int]:
    r = data.get("rev")
    if isinstance(r, int) and r >= 0:
        return r
    return None


def _http_err_message(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except ValueError:
        pass
    t = (resp.text or "")[:200]
    if t:
        return f"HTTP {resp.status_code}: {t}"
    return f"HTTP {resp.status_code}"


def relay_publish_tab_state_full(
    base_url: str,
    room_id: str,
    tab_state: dict,
    timeout: float = 240.0,
) -> Tuple[bool, str, Optional[int]]:
    """全量上传（重置房间为 rev=1）。"""
    rid, err = parse_room_id(room_id)
    if not rid:
        return False, err, None
    try:
        base = _relay_base_path(base_url)
    except ValueError as e:
        return False, str(e), None
    if not base:
        return False, "请先在「设置 → 外部服务」填写中继站点根地址", None

    ok_pf, msg_pf = relay_preflight_for_upload(base_url, timeout=min(timeout, 20.0))
    if not ok_pf:
        return False, msg_pf, None

    raw_str = json.dumps(tab_state, ensure_ascii=False)
    chunks = _utf8_byte_chunks(raw_str, RELAY_FULL_UPLOAD_CHUNK_BYTES)
    headers_json = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers_text = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "text/plain; charset=utf-8",
    }
    enc_rid = quote(rid, safe="")
    _relay_log_config_context("全量上传开始", base_url, room_id=rid)
    _relay_log_tab_state_brief("全量上传开始", tab_state)
    logger.info(
        "%s 全量上传 序列化字节=%s 分片数=%s API根=%r",
        _RELAY_LOG_TAG,
        len(raw_str.encode("utf-8")),
        len(chunks),
        base,
    )

    part_timeout = min(timeout, 120.0)
    n_chunks = len(chunks)
    workers = min(RELAY_UPLOAD_PART_MAX_WORKERS, n_chunks) if n_chunks > 1 else 1

    try:
        with requests.Session() as sess:
            sess.headers.update({"User-Agent": USER_AGENT})
            init_url = f"{base}/rooms/{enc_rid}/upload/init"
            r0 = _relay_request_with_log(
                "初始化上传",
                "POST",
                init_url,
                json={"parts": n_chunks},
                timeout=min(timeout, 60.0),
                headers=headers_json,
                session=sess,
            )
            if r0.status_code != 200:
                err_msg = _http_err_message(r0)
                if r0.status_code == 404 and "not_found" in err_msg.lower():
                    err_msg = f"{err_msg}（若已更新脚本仍如此，请核对域名是否绑定到正确的 Deno Production 项目。）"
                logger.warning(
                    "%s 初始化上传失败 错误=%s",
                    _RELAY_LOG_TAG,
                    err_msg,
                )
                return False, f"初始化上传失败：{err_msg}", None

            t_parts0 = time.perf_counter()
            if workers <= 1:
                for i, piece in enumerate(chunks):
                    part_url = f"{base}/rooms/{enc_rid}/upload/part/{i}"
                    rp = _relay_request_with_log(
                        f"上传分片{i}",
                        "POST",
                        part_url,
                        data=piece.encode("utf-8"),
                        timeout=part_timeout,
                        headers=headers_text,
                        session=sess,
                    )
                    if rp.status_code != 200:
                        logger.warning(
                            "%s 上传分片失败 序号=%s/%s 错误=%s",
                            _RELAY_LOG_TAG,
                            i + 1,
                            n_chunks,
                            _http_err_message(rp),
                        )
                        return False, f"上传分片 {i + 1}/{n_chunks} 失败：{_http_err_message(rp)}", None
            else:
                logger.info(
                    "%s 全量上传 并行分片 并发数=%s 分片总数=%s",
                    _RELAY_LOG_TAG,
                    workers,
                    n_chunks,
                )
                part_futures = []
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for i, piece in enumerate(chunks):
                        u = f"{base}/rooms/{enc_rid}/upload/part/{i}"
                        part_futures.append(
                            pool.submit(
                                _relay_upload_part_worker,
                                i,
                                u,
                                piece.encode("utf-8"),
                                headers_text,
                                part_timeout,
                            )
                        )
                    by_idx: Dict[int, Tuple[Optional[requests.Response], Optional[str]]] = {}
                    for fut in as_completed(part_futures):
                        idx, resp, err = fut.result()
                        by_idx[idx] = (resp, err)
                dt_parts = (time.perf_counter() - t_parts0) * 1000
                logger.info("%s 全量上传 并行分片完成 耗时毫秒=%.0f", _RELAY_LOG_TAG, dt_parts)
                for i in range(n_chunks):
                    pair = by_idx.get(i)
                    if not pair:
                        return False, f"上传分片 {i + 1}/{n_chunks} 失败：未返回结果", None
                    rp, err = pair
                    if err is not None:
                        return False, f"上传分片 {i + 1}/{n_chunks} 失败：{err}", None
                    if rp is None or rp.status_code != 200:
                        em = _http_err_message(rp) if rp is not None else "无响应"
                        logger.warning(
                            "%s 上传分片失败 序号=%s/%s 错误=%s",
                            _RELAY_LOG_TAG,
                            i + 1,
                            n_chunks,
                            em,
                        )
                        return False, f"上传分片 {i + 1}/{n_chunks} 失败：{em}", None

            commit_url = f"{base}/rooms/{enc_rid}/upload/commit"
            rc = _relay_request_with_log(
                "提交全量合并",
                "POST",
                commit_url,
                json={},
                timeout=part_timeout,
                headers=headers_json,
                session=sess,
            )
        if rc.status_code != 200:
            logger.warning("%s 提交全量合并失败 错误=%s", _RELAY_LOG_TAG, _http_err_message(rc))
            return False, f"完成上传失败：{_http_err_message(rc)}", None
        try:
            summary = rc.json()
        except ValueError:
            summary = {}
        rev = _response_rev(summary) or 1
        stored = summary.get("stored_chunks")
        logger.info(
            "%s 全量上传完成 房间=%s 版本=%s 存储块数=%s 响应字段=%s",
            _RELAY_LOG_TAG,
            rid,
            rev,
            stored,
            list(summary.keys()) if isinstance(summary, dict) else None,
        )
        if isinstance(stored, int):
            return True, f"已全量发布到房间「{rid}」（{stored} 块，rev={rev}）", rev
        return True, f"已全量发布到房间「{rid}」（rev={rev}）", rev
    except requests.RequestException as e:
        logger.warning("%s 全量上传网络异常: %s", _RELAY_LOG_TAG, e)
        return False, f"网络错误：{e}", None


def relay_publish_tab_state_incremental(
    base_url: str,
    room_id: str,
    base_rev: int,
    patch: dict,
    remove_namespaces: List[str],
    timeout: float = 120.0,
) -> Tuple[bool, str, Optional[int], bool]:
    """
    增量上传。返回 (成功, 消息, 新 rev, 是否需要改全量重试)。
    """
    rid, err = parse_room_id(room_id)
    if not rid:
        return False, err, None, False
    try:
        base = _relay_base_path(base_url)
    except ValueError as e:
        return False, str(e), None, False
    if not base:
        return False, "请先在「设置 → 外部服务」填写中继站点根地址", None, False

    ok_pf, msg_pf = relay_preflight_for_upload(base_url, timeout=min(timeout, 20.0))
    if not ok_pf:
        return False, msg_pf, None, False

    enc_rid = quote(rid, safe="")
    url = f"{base}/rooms/{enc_rid}/incremental"
    headers_json = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body_obj = {
        "base_rev": base_rev,
        "patch": patch,
        "remove_namespaces": remove_namespaces,
    }
    try:
        body_bytes = len(json.dumps(body_obj, ensure_ascii=False).encode("utf-8"))
    except Exception:
        body_bytes = -1
    _relay_log_config_context("增量上传开始", base_url, room_id=rid)
    logger.info(
        "%s 增量上传 基准版本=%s 删除命名空间数=%s 请求体字节=%s 补丁键=%s",
        _RELAY_LOG_TAG,
        base_rev,
        len(remove_namespaces),
        body_bytes,
        list(patch.keys()),
    )
    try:
        resp = _relay_request_with_log(
            "增量提交",
            "POST",
            url,
            json=body_obj,
            timeout=timeout,
            headers=headers_json,
        )
        if resp.status_code == 409:
            try:
                dj = resp.json()
            except ValueError:
                dj = {}
            logger.warning(
                "%s 增量上传409 版本冲突 响应=%r",
                _RELAY_LOG_TAG,
                dj,
            )
            return False, "中继版本已变（rev 冲突），将自动改为全量上传。", None, True
        if resp.status_code != 200:
            return False, f"增量上传失败：{_http_err_message(resp)}", None, False
        data = resp.json()
        if not isinstance(data, dict) or data.get("ok") is not True:
            logger.warning("%s 增量上传响应异常 ok不为true 响应=%r", _RELAY_LOG_TAG, data)
            return False, "增量上传响应异常", None, False
        if data.get("noop"):
            rev = _response_rev(data)
            logger.info("%s 增量上传 无变更 版本=%s", _RELAY_LOG_TAG, rev or base_rev)
            return True, "中继已是最新（无合并变更）。", rev or base_rev, False
        rev = _response_rev(data)
        ch = data.get("stored_chunks")
        logger.info("%s 增量上传成功 版本=%s 存储块数=%s", _RELAY_LOG_TAG, rev, ch)
        if isinstance(rev, int) and isinstance(ch, int):
            return True, f"已增量同步到房间「{rid}」（rev={rev}，{ch} 块）", rev, False
        if isinstance(rev, int):
            return True, f"已增量同步到房间「{rid}」（rev={rev}）", rev, False
        return True, f"已增量同步到房间「{rid}」", None, False
    except requests.RequestException as e:
        logger.warning("%s 增量上传网络异常: %s", _RELAY_LOG_TAG, e)
        return False, f"网络错误：{e}", None, False


def _publish_plan_mode_zh(plan: Dict[str, Any]) -> str:
    m = plan.get("mode")
    return {"full": "全量", "noop": "跳过", "incremental": "增量"}.get(m, str(m))


def relay_publish_tab_state_smart(
    base_url: str,
    room_id: str,
    tab: Any,
    tab_state: dict,
    timeout: float = 240.0,
) -> Tuple[bool, str, Optional[int], str]:
    """
    首次全量，之后同房间且指纹齐全时走增量（否则全量）。
    返回 (成功, 消息, rev, 模式 full|incremental|noop)。
    """
    rid, err = parse_room_id(room_id)
    if not rid:
        return False, err, None, "error"

    plan = plan_tab_publish_strategy(tab, rid, tab_state)
    logger.info(
        "%s 智能发布 策略=%s 细节=%s 标签已同步房间=%r 标签远端版本=%r",
        _RELAY_LOG_TAG,
        _publish_plan_mode_zh(plan),
        _summarize_publish_plan(plan),
        getattr(tab, "_relay_sync_room", None),
        getattr(tab, "_relay_sync_remote_rev", None),
    )
    mode = plan.get("mode")
    if mode == "noop":
        rev = getattr(tab, "_relay_sync_remote_rev", None)
        if isinstance(rev, int):
            return True, "与上次上传相比无变更，已跳过。", rev, "noop"
        return True, "无变更可同步。", None, "noop"
    if mode == "full":
        logger.info("%s 智能发布 执行=全量上传", _RELAY_LOG_TAG)
        ok, msg, rev = relay_publish_tab_state_full(base_url, rid, tab_state, timeout=timeout)
        return ok, msg, rev, "full"

    base_rev = int(plan["base_rev"])
    patch = plan["patch"]
    remove_ns = plan.get("remove_namespaces") or []
    ok, msg, rev, need_full = relay_publish_tab_state_incremental(
        base_url, rid, base_rev, patch, remove_ns, timeout=min(timeout, 120.0)
    )
    if need_full:
        logger.warning("%s 智能发布 增量冲突 改回全量上传", _RELAY_LOG_TAG)
        ok2, msg2, rev2 = relay_publish_tab_state_full(base_url, rid, tab_state, timeout=timeout)
        return ok2, msg2, rev2, "full"
    return ok, msg, rev, "incremental"


def relay_publish_tab_state(
    base_url: str,
    room_id: str,
    tab_state: dict,
    timeout: float = 240.0,
) -> Tuple[bool, str]:
    """兼容：无 tab 上下文时仅支持全量上传。"""
    ok, msg, _rev = relay_publish_tab_state_full(base_url, room_id, tab_state, timeout=timeout)
    return ok, msg


def relay_fetch_tab_state(
    base_url: str,
    room_id: str,
    *,
    since_rev: Optional[int] = None,
    timeout: float = 120.0,
) -> Tuple[bool, Optional[dict], str, Optional[int], bool]:
    """
    从房间拉取 tab_state。
    返回 (成功, 数据或 None, 消息, 远程 rev, 是否未变化)。
    """
    rid, err = parse_room_id(room_id)
    if not rid:
        return False, None, err, None, False
    try:
        base = _relay_base_path(base_url)
    except ValueError as e:
        return False, None, str(e), None, False
    if not base:
        return False, None, "请先在「设置 → 外部服务」填写中继站点根地址", None, False

    ok_pf, msg_pf = relay_preflight_for_upload(base_url, timeout=min(timeout, 20.0))
    if not ok_pf:
        return False, None, msg_pf, None, False

    enc_rid = quote(rid, safe="")
    url = f"{base}/rooms/{enc_rid}"
    params = {}
    if isinstance(since_rev, int) and since_rev > 0:
        params["since_rev"] = since_rev
    full_url = url + (("?" + urlencode(params)) if params else "")
    _relay_log_config_context("拉取开始", base_url, room_id=rid)
    logger.info("%s 拉取房间 GET URL=%r 本地已知版本=%r", _RELAY_LOG_TAG, full_url, since_rev)
    try:
        resp = _relay_request_with_log(
            "获取房间数据",
            "GET",
            url,
            params=params or None,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except requests.RequestException as e:
        logger.warning("%s 拉取网络异常: %s", _RELAY_LOG_TAG, e)
        return False, None, f"网络错误：{e}", None, False

    if resp.status_code != 200:
        return False, None, f"拉取失败：{_http_err_message(resp)}", None, False

    try:
        data: Any = resp.json()
    except ValueError:
        logger.warning("%s 拉取响应非JSON 文本=%r", _RELAY_LOG_TAG, _relay_preview(resp.text, 400))
        return False, None, "中继返回了非 JSON 数据", None, False

    if not isinstance(data, dict) or data.get("ok") is not True:
        msg = data.get("error") or "unknown"
        logger.warning(
            "%s 拉取失败 ok不为true 错误=%r 响应字段=%s",
            _RELAY_LOG_TAG,
            msg,
            list(data.keys()) if isinstance(data, dict) else None,
        )
        return False, None, f"拉取失败：{msg}", None, False

    if data.get("unchanged"):
        rev = _response_rev(data)
        r = rev if isinstance(rev, int) else (since_rev or 0)
        logger.info("%s 拉取跳过 远端版本未变 版本=%s", _RELAY_LOG_TAG, r)
        return True, None, "远程版本未变化（since_rev）", r, True

    tab_state = data.get("tab_state")
    if not isinstance(tab_state, dict):
        return False, None, "响应中缺少 tab_state", None, False
    if "workbench_state" not in tab_state:
        return False, None, "数据不完整（缺少 workbench_state）", None, False
    rev = _response_rev(data)
    _relay_log_tab_state_brief("拉取成功", tab_state)
    logger.info("%s 拉取成功 远端版本=%s", _RELAY_LOG_TAG, rev)
    return True, tab_state, "拉取成功", rev if isinstance(rev, int) else None, False
