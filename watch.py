"""
EarthMC 插件 — 自动监控
VP 多级提醒 · 玩家上线检测 · 城镇变动监控 · 配置持久化
"""
import asyncio
import json
import os
import time

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .api import get, post

WATCH_POLL_SECONDS = 20
WATCH_CONFIG_FILE = "earthmc_watch.json"
TOWN_CHECK_INTERVAL = 3  # 城镇监控每 3 个轮询周期(60s)检查一次


class WatchManager:
    """管理所有群的 VP 提醒和玩家上线监控"""

    def __init__(self, plugin_name: str, send_message,
                 poll_seconds: float = 20,
                 town_check_interval: int = 3):
        """
        plugin_name: 插件名（用于路径）
        send_message: async callable(umo, message_chain) → 发送群消息
        poll_seconds: 轮询间隔（秒）
        town_check_interval: 城镇检查间隔（轮询周期数）
        """
        self._plugin_name = plugin_name
        self._send = send_message
        self.poll_seconds = poll_seconds
        self.town_check_interval = town_check_interval
        self._data_dir: str = ""
        self._task: asyncio.Task | None = None

    # ── 配置文件 ──────────────────────

    @property
    def data_dir(self) -> str:
        if not self._data_dir:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            self._data_dir = os.path.join(
                str(get_astrbot_data_path()), "plugin_data", self._plugin_name)
            os.makedirs(self._data_dir, exist_ok=True)
        return self._data_dir

    @property
    def config_path(self) -> str:
        return os.path.join(self.data_dir, WATCH_CONFIG_FILE)

    def load_config(self) -> dict:
        path = self.config_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[EarthMC] 读取 watch 配置失败: {e}")
        return {}

    def save_config(self, config: dict):
        """原子写入：先写临时文件再 rename，防止容器被 kill 时文件截断损坏。"""
        path = self.config_path
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)  # 原子操作（同文件系统内）
        except Exception as e:
            logger.error(f"[EarthMC] 保存 watch 配置失败: {e}")

    # ── 生命周期 ──────────────────────

    def start(self):
        config = self.load_config()
        if config and self._task is None:
            self._task = asyncio.create_task(self._poll_loop())
            logger.info(f"[EarthMC] 已恢复 {len(config)} 个群的 watch 监控")
            return True
        return False

    def ensure_running(self):
        """确保轮询在运行（首次设置时调用）"""
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("[EarthMC] Watch 轮询已通过 ensure_running 启动")
        else:
            logger.info("[EarthMC] Watch 轮询已在运行中，跳过重复启动")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ── 轮询主循环 ────────────────────

    async def _poll_loop(self):
        logger.info("[EarthMC] Watch 后台轮询已启动 (间隔 %.0fs)", self.poll_seconds)
        tick = 0
        while True:
            await asyncio.sleep(self.poll_seconds)
            tick += 1
            try:
                config = self.load_config()
                if not config:
                    continue

                needs_vp = any(w.get("vp_thresholds") for w in config.values())
                needs_player = any(w.get("players") for w in config.values())
                needs_towns = (tick % self.town_check_interval == 0 and
                               any(w.get("towns") for w in config.values()))

                logger.debug("[EarthMC] Watch tick #%d: vp=%s player=%s towns=%s",
                             tick, needs_vp, needs_player, needs_towns)

                server_data = await get("/", force=True) if needs_vp else None
                online_data = await get("/online", force=True) if needs_player else None

                if needs_vp:
                    logger.debug("[EarthMC] server_data keys: %s",
                                 list(server_data.keys()) if server_data else "None")
                if needs_player:
                    logger.debug("[EarthMC] online_data: %d players",
                                 len(online_data.get("players", [])) if online_data else 0)

                for group_id, w in list(config.items()):
                    umo = w.get("umo", "")
                    if not umo:
                        logger.warning("[EarthMC] Watch 群 %s 缺少 umo，跳过", group_id)
                        continue
                    if server_data and w.get("vp_thresholds"):
                        await self._check_vp(group_id, umo, w, server_data)
                    if online_data and w.get("players"):
                        await self._check_players(group_id, umo, w, online_data)
                    if needs_towns and w.get("towns"):
                        await self._check_towns(group_id, umo, w)

            except Exception as e:
                logger.error(f"[EarthMC] Watch 轮询异常: {e}")

    # ── VP 检查 ────────────────────────

    async def _check_vp(self, group_id: str, umo: str,
                        w: dict, data: dict):
        thresholds = w.get("vp_thresholds")
        if not thresholds:
            return
        vp = data.get("voteParty", {})
        if not vp or "numRemaining" not in vp:
            return  # API 响应不完整（如 scan 高并发时），跳过本次
        target = vp.get("target", 0) or 1
        remaining = vp.get("numRemaining", 0)
        current = target - remaining
        vp_last = w.get("vp_last")

        if vp_last is None:
            config = self.load_config()
            gw = config.get(group_id)
            if gw:
                gw["vp_last"] = remaining
                self.save_config(config)
            return

        changed = False
        for t in sorted(thresholds, reverse=True):
            if remaining <= t < vp_last:
                msg = f"🗳 VoteParty 剩余 {remaining} 票"
                try:
                    await self._send(umo, MessageChain().message(msg))
                except Exception as e:
                    logger.error(f"[EarthMC] Watch VP 发送失败: {e}")
                changed = True
                break

        if changed or remaining != vp_last:
            config = self.load_config()
            gw = config.get(group_id)
            if gw:
                gw["vp_last"] = remaining
                self.save_config(config)

    # ── 玩家上下线检查 ──────────────────

    async def _check_players(self, group_id: str, umo: str,
                              w: dict, data: dict):
        watched: dict = w.get("players", {})
        if not watched:
            return

        online_names = {p.get("name", "").lower()
                        for p in data.get("players", [])}
        now = time.time()
        changed = False

        for name, state in list(watched.items()):
            is_online = name.lower() in online_names
            was_online = state.get("online", False)

            if is_online == was_online:
                continue

            changed = True
            if is_online:
                state["online_since"] = now
                msg = f"🟢 {name} 上线"
            else:
                since = state.get("online_since")
                if since:
                    secs = int(now - since)
                    h, m = secs // 3600, (secs % 3600) // 60
                    dur = f"{h}小时{m}分钟" if h else f"{m}分钟"
                    state.pop("online_since", None)
                else:
                    dur = "?"
                msg = f"🔴 {name} 下线（在线{dur}）"

            try:
                await self._send(umo, MessageChain().message(msg))
            except Exception as e:
                logger.error(f"[EarthMC] Watch 玩家发送失败: {e}")

            state["online"] = is_online

        if changed:
            # 从磁盘重新加载，合并变更，避免覆盖并发命令修改
            config = self.load_config()
            gw = config.get(group_id)
            if gw:
                gw["players"] = watched
                self.save_config(config)

    # ── 城镇变动检查 ──────────────────

    async def _check_towns(self, group_id: str, umo: str, w: dict):
        watched: dict = w.get("towns", {})
        if not watched:
            return

        # 一次批量查所有被监控的城镇
        tnames = list(watched.keys())
        data = await post("/towns", {"query": tnames})
        if not data or not isinstance(data, list):
            return

        t_map = {t.get("name", "").lower(): t for t in data}
        changed = False

        for name, old in list(watched.items()):
            td = t_map.get(name.lower(), {})
            if not td:
                continue
            stats = td.get("stats") or {}
            mayor = (td.get("mayor") or {}).get("name", "?")
            nation = (td.get("nation") or {}).get("name", "无")
            residents = stats.get("numResidents", 0)
            blocks = stats.get("numTownBlocks", 0)
            max_blocks = stats.get("maxTownBlocks", 0)
            balance = stats.get("balance", 0)
            is_open = (td.get("status") or {}).get("isOpen", False)
            is_ruined = (td.get("status") or {}).get("isRuined", False)

            # 当前居民名单
            cur_names = {r.get("name", "") for r in (td.get("residents") or [])}
            old_residents = old.get("residents", [])
            is_migrate = isinstance(old_residents, int)  # 旧格式（整型人数）
            if is_migrate:
                old_names = set(cur_names)  # 首次初始化，不报变动
            else:
                old_names = set(old_residents)

            msgs = []
            # 人数 + 成员变化
            # 兼容旧格式（residents 存的是 int 而非 list）
            if is_migrate:
                old_r = residents  # 首次不报人数变化
            else:
                old_r = old.get("resident_count", 0)
            if residents != old_r:
                diff = residents - old_r
                sign = "+" if diff >= 0 else ""
                parts = [f"👥 {name} 人数 {old_r}→{residents} ({sign}{diff})"]
                added = cur_names - old_names
                removed = old_names - cur_names
                if added:
                    parts.append(f"  加入: {', '.join(sorted(added))}")
                if removed:
                    parts.append(f"  退出: {', '.join(sorted(removed))}")
                msgs.append("\n".join(parts))
                old["resident_count"] = residents
                old["residents"] = sorted(cur_names)

            # 方块
            old_b = old.get("blocks", 0)
            if blocks != old_b:
                diff = blocks - old_b
                sign = "+" if diff >= 0 else ""
                msgs.append(f"🧱 {name} 方块 {old_b}→{blocks}/{max_blocks} ({sign}{diff})")
                old["blocks"] = blocks
                old["maxBlocks"] = max_blocks

            # 余额
            old_bal = old.get("balance", 0)
            if balance != old_bal:
                diff = balance - old_bal
                sign = "+" if diff >= 0 else ""
                msgs.append(f"💰 {name} 余额 {old_bal}→{balance}G ({sign}{diff}G)")
                old["balance"] = balance

            # 市长
            old_mayor = old.get("mayor", "")
            if mayor != old_mayor:
                msgs.append(f"👤 {name} 市长 {old_mayor}→{mayor}")
                old["mayor"] = mayor

            # 国家
            old_nation = old.get("nation", "")
            if nation != old_nation:
                msgs.append(f"🏰 {name} 国家 {old_nation}→{nation}")
                old["nation"] = nation

            # 开放/废墟状态
            is_open_old = old.get("is_open", None)
            if is_open_old is not None and is_open != is_open_old:
                msgs.append(f"🚪 {name} {'开放' if is_open else '关闭'}")

            is_ruined_old = old.get("is_ruined", None)
            if is_ruined_old is not None and is_ruined != is_ruined_old:
                msgs.append(f"💀 {name} 已变为废墟！")

            old["is_open"] = is_open
            old["is_ruined"] = is_ruined

            if msgs:
                changed = True
                try:
                    await self._send(
                        umo, MessageChain().message("\n".join(msgs)))
                except Exception as e:
                    logger.error(f"[EarthMC] Watch 城镇发送失败: {e}")

        if changed:
            config = self.load_config()
            gw = config.get(group_id)
            if gw:
                gw["towns"] = watched
                self.save_config(config)
