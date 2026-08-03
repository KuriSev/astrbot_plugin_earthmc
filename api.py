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
              http_timeout: int | None = None):
    """运行时覆盖配置。参数单位为毫秒，内部转为秒。"""
    global CACHE_TTL, HTTP_TIMEOUT
    if cache_ttl is not None:
        CACHE_TTL = cache_ttl / 1000.0
    if http_timeout is not None:
        HTTP_TIMEOUT = http_timeout / 1000.0

# ════════════════════════════════════════
# HTTP
# ════════════════════════════════════════
_session: aiohttp.ClientSession | None = None
_cache: dict[str, tuple[dict, float]] = {}


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
        async with session.get(f"{BASE_URL}{path}") as resp:
            data = await resp.json(content_type=None)
            _cache[path] = (data, _time.time())
            return data
    except Exception as e:
        logger.error(f"[EarthMC] GET {path} → {e}")
        return None


async def post(path: str, body: dict) -> dict | list | None:
    try:
        session = await _get_session()
        async with session.post(f"{BASE_URL}{path}", json=body) as resp:
            return await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[EarthMC] POST {path} → {e}")
        return None


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
