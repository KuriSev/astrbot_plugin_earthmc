"""Nostra 地图截图 — Squaremap 瓦片下载 + 拼接 + 坐标转换"""
import asyncio
import json
import os
import re
import tempfile
import time
from html import unescape
from io import BytesIO

import aiohttp

from astrbot.api import logger

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# ── 地图参数 ────────────────────────
TILE_URL = "https://map.earthmc.net/tiles/minecraft_overworld/{zoom}/{x}_{z}.png"
MARKERS_URL = "https://map.earthmc.net/tiles/minecraft_overworld/markers.json"
PLAYERS_URL = "https://map.earthmc.net/tiles/players.json"
TILE_SIZE = 256
ZOOM_MIN, ZOOM_MAX = 0, 7
ZOOM_DEFAULT = 3  # 拍玩家/坐标时的默认 zoom
MAX_TILES = 6     # 单边最多瓦片数
HTTP_TIMEOUT = 30
TOTAL_TIMEOUT = 60


# ── 坐标转换 ────────────────────────

def _zoom_scale(zoom: int) -> int:
    """zoom=0 最高清(256块/tile)，zoom=7 最远。返回每 tile 覆盖的 MC 块数。"""
    return TILE_SIZE << zoom  # 256 * 2^zoom


def mc_to_tile(mc_x: int, mc_z: int, zoom: int) -> tuple[int, int]:
    """MC 坐标 → tile 坐标 (x, z)"""
    scale = _zoom_scale(zoom)
    return mc_x // scale, mc_z // scale


def tile_to_mc(tile_x: int, tile_z: int, zoom: int) -> tuple[int, int]:
    """tile 左上角 → MC 坐标"""
    scale = _zoom_scale(zoom)
    return tile_x * scale, tile_z * scale


def bounds_to_tiles(min_x: int, min_z: int, max_x: int, max_z: int,
                    zoom: int) -> tuple[int, int, int, int]:
    """MC 边界框 → tile 范围 (x1, z1, x2, z2) 含两端"""
    x1, z1 = mc_to_tile(min_x, min_z, zoom)
    x2, z2 = mc_to_tile(max_x, max_z, zoom)
    return x1, z1, x2, z2


def auto_zoom(min_x: int, min_z: int, max_x: int, max_z: int,
              min_tiles: int = 3) -> int:
    """根据边界框选择合适的 zoom 级别。"""
    for z in range(ZOOM_MAX, ZOOM_MIN - 1, -1):
        x1, z1, x2, z2 = bounds_to_tiles(min_x, min_z, max_x, max_z, z)
        w, h = x2 - x1 + 1, z2 - z1 + 1
        if w <= MAX_TILES and h <= MAX_TILES and max(w, h) >= min_tiles:
            return z
    return ZOOM_MIN


# ── 瓦片下载 ────────────────────────

async def download_tiles(zoom: int, tile_x1: int, tile_z1: int,
                         tile_x2: int, tile_z2: int,
                         session: aiohttp.ClientSession | None = None
                         ) -> list[tuple[int, int, bytes]]:
    """下载指定范围的瓦片 PNG。失败时用 None 占位，调用方决定如何处理。"""
    tiles = []
    own_session = session is None
    if own_session:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        session = aiohttp.ClientSession(timeout=timeout)

    try:
        tasks = {}
        for x in range(tile_x1, tile_x2 + 1):
            for z in range(tile_z1, tile_z2 + 1):
                url = TILE_URL.format(zoom=zoom, x=x, z=z)
                tasks[(x, z)] = _fetch(session, url)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (x, z), data in zip(tasks, results):
            if isinstance(data, Exception):
                logger.debug(f"[EarthMC] 瓦片下载异常 ({x},{z}): {data}")
            elif data is not None:
                tiles.append((x, z, data))
    finally:
        if own_session:
            await session.close()

    return tiles


async def _fetch(session, url: str) -> bytes | None:
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception:
        return None


# ── 拼接 ────────────────────────────

def stitch(tiles: list[tuple[int, int, bytes]]) -> BytesIO:
    """拼接瓦片为 PNG，返回 BytesIO。"""
    if not HAS_PILLOW:
        raise RuntimeError("未安装 Pillow，无法生成地图截图。请执行: pip install Pillow")
    if not tiles:
        raise ValueError("无瓦片数据")

    xs = [t[0] for t in tiles]
    zs = [t[1] for t in tiles]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)

    cols = max_x - min_x + 1
    rows = max_z - min_z + 1

    out = Image.new("RGBA", (cols * TILE_SIZE, rows * TILE_SIZE))
    for x, z, data in tiles:
        img = Image.open(BytesIO(data))
        out.paste(img, ((x - min_x) * TILE_SIZE, (max_z - z) * TILE_SIZE))

    buf = BytesIO()
    out.save(buf, "PNG")
    buf.seek(0)
    return buf


# ── 高层接口 ────────────────────────

async def screenshot_area(min_x: int, min_z: int, max_x: int, max_z: int,
                          zoom: int | None = None) -> BytesIO:
    """给定 MC 边界框，自动选 zoom 并返回截图 PNG。超时抛异常。"""
    if zoom is None:
        zoom = auto_zoom(min_x, min_z, max_x, max_z)
    x1, z1, x2, z2 = bounds_to_tiles(min_x, min_z, max_x, max_z, zoom)
    tile_count = (x2 - x1 + 1) * (z2 - z1 + 1)

    try:
        tiles = await asyncio.wait_for(
            download_tiles(zoom, x1, z1, x2, z2), timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        raise RuntimeError(f"下载 {tile_count} 个瓦片超时（>{TOTAL_TIMEOUT}s），地图服务可能繁忙")

    if not tiles:
        raise RuntimeError("所有瓦片下载失败，地图服务可能不可用")

    return stitch(tiles)


async def screenshot_center(center_x: int, center_z: int, zoom: int,
                            tiles_wide: int = 3, tiles_high: int = 3
                            ) -> BytesIO:
    """以 MC 坐标为中心，下载固定数量瓦片截图。"""
    cx, cz = mc_to_tile(center_x, center_z, zoom)
    hw, hh = tiles_wide // 2, tiles_high // 2
    try:
        tiles = await asyncio.wait_for(
            download_tiles(zoom, cx - hw, cz - hh, cx + hw, cz + hh),
            timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        raise RuntimeError(f"瓦片下载超时（>{TOTAL_TIMEOUT}s）")
    if not tiles:
        raise RuntimeError("所有瓦片下载失败，地图服务可能不可用")
    return stitch(tiles)


def screenshot_path() -> str:
    """生成 AstrBot 可访问的临时文件路径。"""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
    base = os.path.join(str(get_astrbot_data_path()), "temp", "earthmc")
    os.makedirs(base, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".png", prefix="map_", dir=base)
    os.close(fd)
    return path


# ── 地图数据 ────────────────────────

_markers_cache: dict | None = None
_markers_cache_ts: float = 0


async def fetch_markers() -> dict:
    """下载并解析 markers.json（缓存 60s），返回 {town_name_lower: {name, nation, boundary}}"""
    global _markers_cache, _markers_cache_ts
    now = time.time()
    if _markers_cache is not None and now - _markers_cache_ts < 60:
        return _markers_cache

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(MARKERS_URL) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"[EarthMC] 获取 markers 失败: {e}")
            return _markers_cache or {}

    towns = {}
    for marker in data:
        if marker.get("type") != "polygon":
            continue
        name = _parse_marker_name(marker)
        if not name:
            continue
        nation = _parse_marker_nation(marker)
        points = marker.get("points", [])
        if points and points[0]:
            vertices = points[0][0]  # [[[{x,z},...]]]
            xs = [v["x"] for v in vertices]
            zs = [v["z"] for v in vertices]
            towns[name.lower()] = {
                "name": name,
                "nation": nation,
                "min_x": min(xs), "max_x": max(xs),
                "min_z": min(zs), "max_z": max(zs),
            }
    _markers_cache = towns
    _markers_cache_ts = now
    return towns


async def fetch_players() -> dict:
    """下载 players.json，返回 {player_name_lower: {name, x, z, world}}"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(PLAYERS_URL) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"[EarthMC] 获取 players 失败: {e}")
            return {}
    return {p["name"].lower(): p for p in data.get("players", [])}


def _parse_marker_name(marker: dict) -> str | None:
    """从 tooltip/popup HTML 提取纯城镇名。"""
    text = unescape(marker.get("tooltip", "") + marker.get("popup", ""))
    # 优先 <b>...</b>
    m = re.search(r'<b>(.+?)</b>', text)
    if m:
        return m.group(1)
    # Fallback: <span style="font-size:120%;">Name (Nation)</span>
    m = re.search(r'font-size:120%;">(.+?)</span>', text)
    if m:
        name = m.group(1).strip()
        # 去掉末尾的括号备注 "(Ming)"
        name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
        return name if name else None
    return None


def _parse_marker_nation(marker: dict) -> str:
    """从 tooltip HTML 提取所属国家/首都。"""
    text = unescape(marker.get("tooltip", ""))
    m = re.search(r'\(Member of (.+?)\)', text)
    if m:
        return m.group(1)
    m = re.search(r'\(Capital of (.+?)\)', text)
    return m.group(1) if m else ""
