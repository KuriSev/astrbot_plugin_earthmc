"""
EarthMC 插件 — 全服城镇销城风险扫描
每日 18:30 自动扫描 · 手动触发 · 结果缓存
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .api import get, post
from .tools import INACTIVE_DAYS

SCAN_CACHE_FILE = "earthmc_risk_scan.json"
BATCH_SIZE = 100
CONCURRENT = 5
DEEP_SCAN_MAX_RESIDENTS = 10  # 超过此数的城镇视为低风险，不做深度扫描


def _calc_town_risk(town: dict, player_online: dict[str, float | None],
                    now_ms: float) -> dict:
    """
    结合玩家上线数据计算单个城镇的销城剩余天数。
    player_online: { name: lastOnline_ms_or_None }
    """
    residents = town.get("residents", []) or []
    name = town.get("name", "?")
    nation = (town.get("nation") or {}).get("name", "无")

    if not residents:
        return {"name": name, "nation": nation, "defense": "无",
                "days_left": 0, "active_count": 0}

    best = -999
    best_name = "?"
    active_count = 0

    for r in residents:
        rname = r.get("name", "?")
        lo = player_online.get(rname.lower())
        if not lo:
            # 无数据或时间戳无效，跳过
            continue
        days_offline = (now_ms - lo) / 86400000
        dl = INACTIVE_DAYS - days_offline
        if dl <= 0:
            # 已超过 42 天（如不活跃市长），不计入活跃
            continue
        active_count += 1
        if dl > best:
            best = dl
            best_name = r.get("formattedName") or rname

    if active_count == 0:
        return {"name": name, "nation": nation, "defense": "无",
                "days_left": 0, "active_count": 0}

    return {"name": name, "nation": nation, "defense": best_name,
            "days_left": max(best, 0), "active_count": active_count}


class TownRiskScanner:

    def __init__(self, plugin_name: str, send_message,
                 batch_size: int = 100,
                 concurrency: int = 5,
                 deep_scan_max_residents: int = 10,
                 scan_hour: int = 18,
                 scan_minute: int = 30):
        self._plugin_name = plugin_name
        self._send = send_message
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.deep_scan_max_residents = deep_scan_max_residents
        self.scan_hour = scan_hour
        self.scan_minute = scan_minute
        self._data_dir: str = ""
        self._task: asyncio.Task | None = None

    @property
    def data_dir(self) -> str:
        if not self._data_dir:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            self._data_dir = os.path.join(
                str(get_astrbot_data_path()), "plugin_data", self._plugin_name)
            os.makedirs(self._data_dir, exist_ok=True)
        return self._data_dir

    @property
    def cache_path(self) -> str:
        return os.path.join(self.data_dir, SCAN_CACHE_FILE)

    def load_cache(self) -> dict:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[EarthMC] 读取扫描缓存失败: {e}")
        return {"updated_at": "", "total": 0, "towns": []}

    def save_cache(self, data: dict):
        try:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.cache_path)
        except Exception as e:
            logger.error(f"[EarthMC] 保存扫描缓存失败: {e}")

    # ── 扫描主流程 ────────────────────

    async def scan(self, on_done=None) -> int:
        """
        1) 获取全服城镇概况
        2) 筛选需深度扫描的城镇（<=15 活跃居民）
        3) 批量取玩家上线时间
        4) 计算风险 → 缓存
        """
        # ── 阶段 1: 获取所有城镇概况 ──
        all_towns = await get("/towns")
        if not all_towns or not isinstance(all_towns, list):
            logger.error("[EarthMC] 无法获取城镇列表")
            if on_done: await on_done(-1, 0)
            return -1

        names = [t.get("name", "") for t in all_towns if t.get("name")]
        logger.info(f"[EarthMC] 开始扫描 {len(names)} 个城镇...")

        # 按批次并发取详情
        sem = asyncio.Semaphore(self.concurrency)
        town_details: list[dict] = []

        async def fetch_town_batch(batch: list[str]):
            async with sem:
                try:
                    data = await post("/towns", {"query": batch})
                    return data if isinstance(data, list) else []
                except Exception as e:
                    logger.error(f"[EarthMC] 城镇批次查询失败: {e}")
                    return []

        batches = [names[i:i + self.batch_size]
                   for i in range(0, len(names), self.batch_size)]
        results = await asyncio.gather(*[fetch_town_batch(b) for b in batches])
        for r in results:
            town_details.extend(r)

        logger.info(f"[EarthMC] 阶段1完成: 获取 {len(town_details)} 个城镇详情")

        # ── 阶段 2: 收集需要查的玩家名 ──
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        quick_results: list[dict] = []
        names_to_fetch: set[str] = set()
        deep_scan_towns: list[dict] = []

        for t in town_details:
            residents = t.get("residents", []) or []
            rcount = len(residents)

            if rcount == 0:
                quick_results.append({
                    "name": t.get("name", "?"),
                    "nation": (t.get("nation") or {}).get("name", "无"),
                    "defense": "无", "days_left": 0, "active_count": 0,
                })
            elif rcount > self.deep_scan_max_residents:
                quick_results.append({
                    "name": t.get("name", "?"),
                    "nation": (t.get("nation") or {}).get("name", "无"),
                    "defense": f"{rcount}人", "days_left": 999,
                    "active_count": rcount,
                })
            else:
                deep_scan_towns.append(t)
                for r in residents:
                    if r.get("name"):
                        names_to_fetch.add(r["name"])

        logger.info(f"[EarthMC] 阶段2: {len(deep_scan_towns)} 城镇需深度扫描"
                    f" ({len(names_to_fetch)} 个唯一玩家)")

        # ── 阶段 3: 批量取玩家 lastOnline ──
        player_online: dict[str, float | None] = {}
        if names_to_fetch:
            pnames = list(names_to_fetch)
            pbatches = [pnames[i:i + self.batch_size]
                        for i in range(0, len(pnames), self.batch_size)]

            async def fetch_player_batch(batch: list[str]):
                async with sem:
                    try:
                        data = await post("/players", {"query": batch})
                        return data if isinstance(data, list) else []
                    except Exception as e:
                        logger.error(f"[EarthMC] 玩家批次查询失败: {e}")
                        return []

            presults = await asyncio.gather(
                *[fetch_player_batch(b) for b in pbatches])
            for plist in presults:
                for p in plist:
                    lo = (p.get("timestamps") or {}).get("lastOnline")
                    player_online[p.get("name", "").lower()] = lo

            logger.info(f"[EarthMC] 阶段3完成: 获取 {len(player_online)} 个玩家数据")

        # ── 阶段 4: 计算风险 ──
        for t in deep_scan_towns:
            quick_results.append(_calc_town_risk(t, player_online, now_ms))

        quick_results.sort(key=lambda x: x["days_left"])
        logger.info(f"[EarthMC] 阶段4: 风险计算完成")

        # ── 缓存 ──
        cache = {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "total": len(quick_results),
            "towns": quick_results,
        }
        self.save_cache(cache)

        risk_count = sum(1 for t in quick_results
                         if t["days_left"] <= 5)
        logger.info(f"[EarthMC] 扫描完成: {len(quick_results)} 城镇,"
                    f" {risk_count} 中高危(1-5天内)")

        if on_done:
            try:
                await on_done(risk_count, len(quick_results))
            except Exception as e:
                logger.error(f"[EarthMC] 扫描完成回调失败: {e}")

        return risk_count

    # ── 查询缓存 ──────────────────────

    def get_risklist(self, days: int | None = None) -> list[dict]:
        if days is None:
            days = 5
        cache = self.load_cache()
        towns = cache.get("towns", [])
        return [t for t in towns if t["days_left"] <= days]

    def cache_age(self) -> str:
        return self.load_cache().get("updated_at", "从未扫描")

    # ── 定时器 ────────────────────────

    async def start_scheduler(self):
        self._task = asyncio.create_task(self._daily_loop())
        logger.info("[EarthMC] 销城扫描定时器已启动 (每日 %02d:%02d 系统时间)",
                    self.scan_hour, self.scan_minute)

    async def _daily_loop(self):
        while True:
            wait = self._seconds_until_next(self.scan_hour, self.scan_minute)
            logger.info(f"[EarthMC] 下次全服扫描: {wait:.0f} 秒后")
            await asyncio.sleep(wait)
            logger.info("[EarthMC] 执行每日销城扫描...")
            await self.scan()

    async def stop(self):
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
            self._task = None

    @staticmethod
    def _seconds_until_next(hour: int, minute: int) -> float:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour - 8, minute=minute, second=0,
                             microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()
