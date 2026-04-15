/**
 * Modpack Localizer — Cloudflare Workers 项目同步中继（KV）
 *
 * 部署方式：
 * 1. 创建 KV namespace，绑定到 Worker
 * 2. wrangler deploy 或在 Dashboard 上传
 *
 * 与桌面端 utils/project_sync_relay.py 约定保持一致（路径、JSON 字段、状态码）。
 */

/** @type {string} */
const SERVICE_NAME = "modpack-localizer-project-sync-relay";

/** 用于区分本脚本与旧版 Deno 中继 */
const RELAY_CAPABILITIES = {
  chunked_upload: true,
  incremental_merge: true,
};

const TTL_SEC = 7 * 24 * 60 * 60; // 7 days
const STORE_CHUNK_BYTES = 95_000; // 增大单条 KV 大小，减少分片数
const KV_MAX_UPLOAD_PART_BYTES = 100_000; // 增大单次上传大小
const UPLOAD_MAX_PARTS = 500;
const ROOM_ID_RE = /^[a-zA-Z0-9_-]{4,48}$/;

/**
 * @typedef {Object} Env
 * @property {KVNamespace} MY_BINDING
 */

/** @type {Env} */
// @ts-ignore
const ENV = {};

function corsHeaders() {
  const h = new Headers();
  h.set("access-control-allow-origin", "*");
  h.set("access-control-allow-methods", "GET, POST, OPTIONS");
  h.set("access-control-allow-headers", "authorization, content-type");
  return h;
}

/**
 * @param {Record<string, unknown>} body
 * @param {ResponseInit} [init]
 * @returns {Response}
 */
function json(body, init = {}) {
  const h = corsHeaders();
  for (const [k, v] of new Headers(init.headers ?? {})) h.set(k, v);
  h.set("content-type", "application/json; charset=utf-8");
  return new Response(JSON.stringify(body), { ...init, headers: h });
}

function optionsResponse() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

/**
 * @param {string} pathname
 * @returns {string}
 */
function normalizeRoutePath(pathname) {
  let p = pathname;
  if (p.length > 1 && p.endsWith("/")) p = p.slice(0, -1);
  const ri = p.indexOf("/rooms/");
  if (ri > 0) p = p.slice(ri);
  return p;
}

/**
 * @param {string} path
 * @returns {boolean}
 */
function isHealthPath(path) {
  return path === "/health" || path.endsWith("/health");
}

/**
 * @param {string} seg
 * @returns {string|null}
 */
function parseRoomIdSegment(seg) {
  try {
    const id = decodeURIComponent(seg);
    return ROOM_ID_RE.test(id) ? id : null;
  } catch {
    return null;
  }
}

// KV keys
function kMeta(room) {
  return `ml_room:${room}:meta`;
}
function kChunk(room, i) {
  return `ml_room:${room}:c:${i}`;
}
function kUpN(room) {
  return `ml_room:${room}:up:n`;
}
function kUpPart(room, i) {
  return `ml_room:${room}:up:p:${i}`;
}

/**
 * @param {Uint8Array[]} chunks
 * @returns {Uint8Array}
 */
function concatBytes(chunks) {
  let n = 0;
  for (const c of chunks) n += c.length;
  const out = new Uint8Array(n);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

const textDecoder = new TextDecoder();
const textEncoder = new TextEncoder();

/**
 * @param {Record<string, unknown>|null} meta
 * @returns {number}
 */
function readRev(meta) {
  const r = Number(meta?.rev ?? 1);
  return Number.isFinite(r) && r >= 1 ? r : 1;
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @returns {Promise<Record<string, unknown>|null>}
 */
async function loadTabState(kv, room) {
  const metaStr = await kv.get(kMeta(room), "text");
  if (!metaStr) return null;
  const meta = JSON.parse(metaStr);
  const chunkCount = Number(meta.chunks ?? 0);
  if (!Number.isFinite(chunkCount) || chunkCount < 1) return null;

  const parts = [];
  for (let i = 0; i < chunkCount; i++) {
    const chunkStr = await kv.get(kChunk(room, i), "arrayBuffer");
    if (!chunkStr) return null;
    parts.push(new Uint8Array(chunkStr));
  }
  try {
    return JSON.parse(textDecoder.decode(concatBytes(parts)));
  } catch {
    return null;
  }
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @param {Record<string, unknown>} tab
 * @returns {Promise<number>}
 */
async function saveTabState(kv, room, tab) {
  const bytes = textEncoder.encode(JSON.stringify(tab));
  const n = Math.max(1, Math.ceil(bytes.length / STORE_CHUNK_BYTES));
  for (let i = 0; i < n; i++) {
    const start = i * STORE_CHUNK_BYTES;
    const end = Math.min(start + STORE_CHUNK_BYTES, bytes.length);
    const chunk = bytes.subarray(start, end);
    await kv.put(kChunk(room, i), chunk, { expirationTtl: TTL_SEC });
  }
  return n;
}

/**
 * @param {Record<string, unknown>} current
 * @param {Record<string, unknown>} patch
 * @param {string[]} removeNamespaces
 * @returns {Record<string, unknown>}
 */
function mergeTabState(current, patch, removeNamespaces) {
  const out = { ...current };

  const curWb =
    typeof current["workbench_state"] === "object" && current["workbench_state"]
      ? current["workbench_state"]
      : {};
  const mergedWb = { ...curWb };

  const curWd =
    typeof curWb["workbench_data"] === "object" && curWb["workbench_data"]
      ? curWb["workbench_data"]
      : {};
  const nextWd = { ...curWd };

  const pw = patch["workbench_state"];
  if (pw && typeof pw === "object") {
    const pws = pw;
    if (pws["workbench_data"] && typeof pws["workbench_data"] === "object") {
      const upd = pws["workbench_data"];
      for (const [key, val] of Object.entries(upd)) nextWd[key] = val;
    }
    if (pws["namespace_formats"] && typeof pws["namespace_formats"] === "object") {
      const prev =
        typeof mergedWb["namespace_formats"] === "object"
          ? mergedWb["namespace_formats"]
          : {};
      mergedWb["namespace_formats"] = {
        ...prev,
        ...pws["namespace_formats"],
      };
    }
    if (pws["raw_english_files"] && typeof pws["raw_english_files"] === "object") {
      const prev =
        typeof mergedWb["raw_english_files"] === "object"
          ? mergedWb["raw_english_files"]
          : {};
      mergedWb["raw_english_files"] = {
        ...prev,
        ...pws["raw_english_files"],
      };
    }
    if (typeof pws["current_project_path"] === "string") {
      mergedWb["current_project_path"] = pws["current_project_path"];
    }
  }

  for (const ns of removeNamespaces) {
    if (typeof ns === "string" && ns) delete nextWd[ns];
  }
  mergedWb["workbench_data"] = nextWd;
  out["workbench_state"] = mergedWb;

  if (patch["project_info"] && typeof patch["project_info"] === "object") {
    const base =
      typeof current["project_info"] === "object" && current["project_info"]
        ? current["project_info"]
        : {};
    out["project_info"] = { ...base, ...patch["project_info"] };
  }
  if (typeof patch["project_name"] === "string") out["project_name"] = patch["project_name"];
  if (typeof patch["project_type"] === "string") out["project_type"] = patch["project_type"];
  if (Array.isArray(patch["namespace_summary"])) {
    out["namespace_summary"] = patch["namespace_summary"];
  }
  return out;
}

/**
 * @typedef {Object} RouteHealth
 * @property {string} kind
 */
/**
 * @typedef {Object} RouteIndex
 * @property {string} kind
 */
/**
 * @typedef {Object} RouteRoomGet
 * @property {string} kind
 * @property {string} room
 */
/**
 * @typedef {Object} RouteIncremental
 * @property {string} kind
 * @property {string} room
 */
/**
 * @typedef {Object} RouteUploadInit
 * @property {string} kind
 * @property {string} room
 */
/**
 * @typedef {Object} RouteUploadPart
 * @property {string} kind
 * @property {string} room
 * @property {number} index
 */
/**
 * @typedef {Object} RouteUploadCommit
 * @property {string} kind
 * @property {string} room
 */
/**
 * @typedef {Object} RouteUnknown
 * @property {string} kind
 */

/**
 * @typedef {RouteHealth|RouteIndex|RouteRoomGet|RouteIncremental|RouteUploadInit|RouteUploadPart|RouteUploadCommit|RouteUnknown} Route
 */

/**
 * @param {string} method
 * @param {string} path
 * @returns {Route}
 */
function matchRoute(method, path) {
  if (method === "GET" && isHealthPath(path)) return { kind: "health" };
  if (method === "GET" && path === "/") return { kind: "index" };

  const mRoomOnly = path.match(/^\/rooms\/([^/]+)$/);
  if (method === "GET" && mRoomOnly) {
    const room = parseRoomIdSegment(mRoomOnly[1]);
    if (room) return { kind: "room_get", room };
  }

  const mInc = path.match(/^\/rooms\/([^/]+)\/incremental$/);
  if (method === "POST" && mInc) {
    const room = parseRoomIdSegment(mInc[1]);
    if (room) return { kind: "incremental", room };
  }

  const mInit = path.match(/^\/rooms\/([^/]+)\/upload\/init$/);
  if (method === "POST" && mInit) {
    const room = parseRoomIdSegment(mInit[1]);
    if (room) return { kind: "upload_init", room };
  }

  const mPart = path.match(/^\/rooms\/([^/]+)\/upload\/part\/(\d+)$/);
  if (method === "POST" && mPart) {
    const room = parseRoomIdSegment(mPart[1]);
    const idx = parseInt(mPart[2], 10);
    if (room && idx >= 0 && idx <= UPLOAD_MAX_PARTS) {
      return { kind: "upload_part", room, index: idx };
    }
  }

  const mCommit = path.match(/^\/rooms\/([^/]+)\/upload\/commit$/);
  if (method === "POST" && mCommit) {
    const room = parseRoomIdSegment(mCommit[1]);
    if (room) return { kind: "upload_commit", room };
  }

  return { kind: "unknown" };
}

/**
 * @returns {Promise<Response>}
 */
async function handleHealth() {
  return json({
    ok: true,
    service: SERVICE_NAME,
    capabilities: { ...RELAY_CAPABILITIES },
  });
}

/**
 * @returns {Promise<Response>}
 */
async function handleIndex() {
  return json({
    ok: true,
    service: SERVICE_NAME,
    capabilities: { ...RELAY_CAPABILITIES },
    message: "Modpack Localizer project sync relay (Cloudflare Workers)",
    health: "/health",
    rooms_get: "/rooms/:roomId?since_rev=",
    rooms_upload: "/rooms/:roomId/upload/…",
    rooms_incremental: "/rooms/:roomId/incremental",
  });
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @param {URLSearchParams} searchParams
 * @returns {Promise<Response>}
 */
async function handleRoomGet(kv, room, searchParams) {
  const metaStr = await kv.get(kMeta(room), "text");
  if (!metaStr) {
    return json({ ok: false, error: "room_empty" }, { status: 404 });
  }

  const meta = JSON.parse(metaStr);
  const serverRev = readRev(meta);

  const sinceRaw = searchParams.get("since_rev");
  const sinceRev = sinceRaw != null ? Number(sinceRaw) : NaN;
  if (Number.isFinite(sinceRev) && sinceRev > 0 && sinceRev === serverRev) {
    return json({ ok: true, unchanged: true, rev: serverRev });
  }

  const tabState = await loadTabState(kv, room);
  if (!tabState) {
    return json({ ok: false, error: "corrupt_data" }, { status: 500 });
  }
  return json({ ok: true, tab_state: tabState, rev: serverRev });
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @param {Request} req
 * @returns {Promise<Response>}
 */
async function handleIncremental(kv, room, req) {
  /** @type {{base_rev?: number, patch?: Record<string, unknown>, remove_namespaces?: string[]}} */
  let body;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const baseRev = Number(body.base_rev);
  if (!Number.isFinite(baseRev) || baseRev < 1) {
    return json({ ok: false, error: "bad_base_rev" }, { status: 400 });
  }
  const patch = body.patch;
  if (!patch || typeof patch !== "object") {
    return json({ ok: false, error: "bad_patch" }, { status: 400 });
  }
  const removeNs = Array.isArray(body.remove_namespaces)
    ? body.remove_namespaces.filter((x) => typeof x === "string")
    : [];

  const metaStr = await kv.get(kMeta(room), "text");
  if (!metaStr) {
    return json({ ok: false, error: "room_empty" }, { status: 404 });
  }
  const meta = JSON.parse(metaStr);
  const serverRev = readRev(meta);
  if (baseRev !== serverRev) {
    return json({ ok: false, error: "rev_mismatch", server_rev: serverRev }, { status: 409 });
  }

  if (Object.keys(patch).length === 0 && removeNs.length === 0) {
    return json({ ok: true, noop: true, rev: serverRev });
  }

  const current = await loadTabState(kv, room);
  if (!current) {
    return json({ ok: false, error: "corrupt_data" }, { status: 500 });
  }

  const merged = mergeTabState(current, patch, removeNs);
  const chunkCount = await saveTabState(kv, room, merged);
  const newRev = serverRev + 1;
  await kv.put(
    kMeta(room),
    JSON.stringify({
      v: 1,
      chunks: chunkCount,
      updated: new Date().toISOString(),
      project_name: String(merged.project_name ?? ""),
      rev: newRev,
    }),
    { expirationTtl: TTL_SEC },
  );
  return json({
    ok: true,
    mode: "incremental",
    rev: newRev,
    stored_chunks: chunkCount,
  });
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @param {Request} req
 * @returns {Promise<Response>}
 */
async function handleUploadInit(kv, room, req) {
  /** @type {{parts?: number}} */
  let body;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const parts = Number(body.parts);
  if (!Number.isFinite(parts) || parts < 1 || parts > UPLOAD_MAX_PARTS) {
    return json({ ok: false, error: "bad_parts" }, { status: 400 });
  }

  // 删除旧的待上传数据
  for (let i = 0; i < parts; i++) {
    await kv.delete(kUpPart(room, i)).catch(() => {});
  }
  await kv.delete(kUpN(room)).catch(() => {});

  await kv.put(kUpN(room), String(parts), { expirationTtl: TTL_SEC });
  return json({ ok: true, room, parts });
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @param {number} index
 * @param {Request} req
 * @returns {Promise<Response>}
 */
async function handleUploadPart(kv, room, index, req) {
  const nStr = await kv.get(kUpN(room), "text");
  if (!nStr) {
    return json({ ok: false, error: "upload_not_started" }, { status: 400 });
  }
  const n = parseInt(nStr, 10);
  if (index >= n) {
    return json({ ok: false, error: "part_index_oob" }, { status: 400 });
  }

  /** @type {ArrayBuffer} */
  let buf;
  try {
    buf = await req.arrayBuffer();
  } catch (e) {
    console.error("[relay] upload_part body", e);
    return json({ ok: false, error: "bad_body" }, { status: 400 });
  }
  if (buf.byteLength > KV_MAX_UPLOAD_PART_BYTES) {
    return json(
      {
        ok: false,
        error: "part_too_large",
        max_bytes: KV_MAX_UPLOAD_PART_BYTES,
        got_bytes: buf.byteLength,
      },
      { status: 413 },
    );
  }

  await kv.put(kUpPart(room, index), new Uint8Array(buf), { expirationTtl: TTL_SEC });
  return json({ ok: true, received: index });
}

/**
 * @param {KVNamespace} kv
 * @param {string} room
 * @returns {Promise<Response>}
 */
async function handleUploadCommit(kv, room) {
  const nStr = await kv.get(kUpN(room), "text");
  if (!nStr) {
    return json({ ok: false, error: "upload_not_started" }, { status: 400 });
  }
  const n = parseInt(nStr, 10);
  if (!Number.isFinite(n) || n < 1) {
    return json({ ok: false, error: "upload_not_started" }, { status: 400 });
  }

  const pieces = [];
  for (let i = 0; i < n; i++) {
    const p = await kv.get(kUpPart(room, i), "arrayBuffer");
    if (!p) {
      return json({ ok: false, error: "part_missing", index: i }, { status: 400 });
    }
    pieces.push(new Uint8Array(p));
  }
  const joinedBytes = concatBytes(pieces);

  /** @type {Record<string, unknown>} */
  let tabState;
  try {
    tabState = JSON.parse(textDecoder.decode(joinedBytes));
  } catch {
    return json({ ok: false, error: "json_parse_failed" }, { status: 400 });
  }
  if (!tabState || typeof tabState !== "object" || !("workbench_state" in tabState)) {
    return json({ ok: false, error: "invalid_tab_state" }, { status: 400 });
  }

  const chunkCount = await saveTabState(kv, room, tabState);
  await kv.put(
    kMeta(room),
    JSON.stringify({
      v: 1,
      chunks: chunkCount,
      updated: new Date().toISOString(),
      project_name: String(tabState.project_name ?? ""),
      rev: 1,
    }),
    { expirationTtl: TTL_SEC },
  );

  // 清理上传缓存
  for (let i = 0; i < n; i++) {
    await kv.delete(kUpPart(room, i)).catch(() => {});
  }
  await kv.delete(kUpN(room)).catch(() => {});

  return json({ ok: true, stored_chunks: chunkCount, rev: 1, mode: "full" });
}

/**
 * @param {Request} req
 * @param {KVNamespace} kv
 * @param {string} path
 * @returns {Promise<Response>}
 */
async function dispatch(req, kv, path) {
  const route = matchRoute(req.method, path);
  const kind = route.kind;

  if (kind === "health") {
    return await handleHealth();
  }
  if (kind === "index") {
    return await handleIndex();
  }
  if (kind === "room_get") {
    return await handleRoomGet(kv, route.room, new URL(req.url).searchParams);
  }
  if (kind === "incremental") {
    return await handleIncremental(kv, route.room, req);
  }
  if (kind === "upload_init") {
    return await handleUploadInit(kv, route.room, req);
  }
  if (kind === "upload_part") {
    return await handleUploadPart(kv, route.room, route.index, req);
  }
  if (kind === "upload_commit") {
    return await handleUploadCommit(kv, route.room);
  }
  return json({ ok: false, error: "not_found" }, { status: 404 });
}

/**
 * @param {Request} request
 * @param {Env} env
 * @param {Object} ctx
 * @returns {Promise<Response>}
 */
async function handleRequest(request, env, ctx) {
  const kv = env.MY_BINDING;
  const path = normalizeRoutePath(new URL(request.url).pathname);

  if (request.method === "OPTIONS") {
    return optionsResponse();
  }

  return dispatch(request, kv, path);
}

export default {
  fetch: handleRequest,
};
