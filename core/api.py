"""
EarthMC 插件 — 基础设施
HTTP 请求、缓存、格式化工具
"""
import time as _time
from datetime import datetime

import aiohttp

from astrbot.api import logger

# ════════════════════════════════════════
# 常量
# ════════════════════════════════════════
BASE_URL = "https://api.earthmc.net/v4"
CACHE_TTL = 30.0
HTTP_TIMEOUT = 10.0


def configure(cache_ttl: int | None = None,
              http_timeout: int | None = None,
              api_key: str = ""):
    """运行时覆盖配置。参数单位为毫秒，内部转为秒。"""
    global CACHE_TTL, HTTP_TIMEOUT, _API_KEY
    if cache_ttl is not None:
        CACHE_TTL = cache_ttl / 1000.0
    if http_timeout is not None:
        HTTP_TIMEOUT = http_timeout / 1000.0
    if api_key:
        _API_KEY = api_key.strip()   # 去掉粘贴时带的首尾空白

# ════════════════════════════════════════
# HTTP
# ════════════════════════════════════════
_session: aiohttp.ClientSession | None = None
_cache: dict[str, tuple[dict, float]] = {}
_API_KEY = ""


def _headers() -> dict | None:
    """已配置 API key 时返回请求头，否则 None。"""
    return {"X-API-Key": _API_KEY} if _API_KEY else None


def _key_hint() -> str:
    """调试用：显示 key 是否已配置及掩码，便于确认是否真的发出了 key。"""
    if not _API_KEY:
        return "未配置 API key"
    return f"已发送 key {_API_KEY[:4]}…{_API_KEY[-4:]} (len={len(_API_KEY)})"


def get_api_key() -> str:
    """返回当前配置的 API key（用于放入请求体，如 /mcmmo-top 的 key 字段）。"""
    return _API_KEY


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT))
    return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def get(path: str, *, force: bool = False) -> dict | list | None:
    """带缓存的 GET 请求。force=True 跳过缓存（watch 用）。"""
    if not force:
        cached = _cache.get(path)
        if cached:
            data, ts = cached
            if _time.time() - ts < CACHE_TTL:
                return data
    try:
        session = await _get_session()
        async with session.get(f"{BASE_URL}{path}", headers=_headers()) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.warning(f"[EarthMC] GET {path} → HTTP {resp.status}: {text[:100]} "
                               f"({_key_hint()})")
                return None
            data = await resp.json(content_type=None)
            _cache[path] = (data, _time.time())
            return data
    except Exception as e:
        logger.error(f"[EarthMC] GET {path} → {e}")
        return None


async def post(path: str, body: dict) -> dict | list | None:
    try:
        session = await _get_session()
        async with session.post(f"{BASE_URL}{path}", json=body,
                                headers=_headers()) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.warning(f"[EarthMC] POST {path} → HTTP {resp.status}: {text[:100]} "
                               f"({_key_hint()})")
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[EarthMC] POST {path} → {e}")
        return None


async def post_chunked(path: str, names: list[str], batch: int = 50) -> list[dict]:
    """分批 POST 查询，避开 API 单次 query 数量上限（实测 >100 会被截断）。"""
    out: list[dict] = []
    for i in range(0, len(names), batch):
        data = await post(path, {"query": names[i:i + batch]})
        if isinstance(data, list):
            out.extend(x for x in data if isinstance(x, dict))
    return out


# ════════════════════════════════════════
# 格式化
# ════════════════════════════════════════

def ts_str(ms: int | None) -> str:
    if ms is None: return "?"
    try: return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError): return str(ms)


def mc_time(ticks: int | None) -> str:
    if ticks is None: return "?"
    hours = (ticks + 6000) // 1000 % 24
    minutes = (ticks % 1000) * 60 // 1000
    return f"{hours:02d}:{minutes:02d}"


def moon(phase: str | None) -> str:
    return {
        "FULL_MOON": "🌕 满月", "WANING_GIBBOUS": "🌖 亏凸月",
        "LAST_QUARTER": "🌗 下弦月", "WANING_CRESCENT": "🌘 残月",
        "NEW_MOON": "🌑 新月", "WAXING_CRESCENT": "🌒 蛾眉月",
        "FIRST_QUARTER": "🌓 上弦月", "WAXING_GIBBOUS": "🌔 盈凸月",
    }.get(phase or "", phase or "?")


def weather(has_storm: bool, is_thundering: bool) -> str:
    if is_thundering: return "⛈ 雷暴"
    if has_storm: return "🌧 下雨"
    return "☀ 晴"


def bool_emoji(b: bool | None) -> str:
    if b is None: return "?"
    return "✅" if b else "❌"
