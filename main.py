"""
AstrBot 插件：EarthMC 服务器信息查询 v1.15.1
/em 命令 · LLM Agent 工具 · 自动监控 · 销城评估 · 全服扫描 · 地图截图
"""
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .core import store
from .core.api import close_session, configure as api_configure
from .core.texts import HELP_TEXT, RISK_HELP
from .commands.query import (
    ALL_TOOLS, TOOL_MAP, _run_tool, _first_token, _run_location,
)
from .commands.vp import VPMixin
from .commands.watch import WatchCommandMixin
from .commands.risk import RiskMixin
from .commands.market import MarketMixin
from .commands.map import MapMixin
from .commands.wp import WpMixin
from .webapi import WebAPIMixin
from .tools import TownTool, NationTool, PlayerTool, LocationTool, VotePartyTool
from .features.mcmmo import McMMOTopTool
from .features.watch import WatchManager
from .features.ruins_watch import RuinsWatchManager, RuinsChecker
from .features.market import MarketManager, set_market_manager
from .features.waypoints import WaypointManager, set_waypoint_manager

class EarthMCPlugin(
    Star, VPMixin, WatchCommandMixin, RiskMixin,
    MarketMixin, MapMixin, WpMixin, WebAPIMixin,
):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # ── 读取配置（毫秒值在 main.py 转为秒） ──
        api_configure(
            cache_ttl=config.get("cache_ttl", 30000),
            http_timeout=config.get("http_timeout", 10000),
            api_key=config.get("api_key", ""),
        )

        watch_interval_ms = config.get("watch_interval", 20000)

        self._pending_confirm: dict = {}   # group_key → {user, ts, kind}，/em confirm 二次确认用

        self.watch = WatchManager(
            self.name or "astrbot_plugin_earthmc",
            self.context.send_message,
            poll_seconds=watch_interval_ms / 1000,
            town_check_interval=config.get("town_check_interval", 3),
        )
        self.ruins_watch = RuinsWatchManager(self.name or "astrbot_plugin_earthmc")
        self.ruins_checker = RuinsChecker(
            self.context.send_message,
            self.ruins_watch,
            alert_days=config.get("ruins_alert_days", 7),
            push_hour=config.get("ruins_push_hour", 18),
            push_minute=config.get("ruins_push_minute", 0),
        )

        self.market = MarketManager(self.name or "astrbot_plugin_earthmc")
        set_market_manager(self.market)

        self.waypoints = WaypointManager(self.name or "astrbot_plugin_earthmc")
        set_waypoint_manager(self.waypoints)

        # ── WebUI 配置管理 API ──
        context.register_web_api(
            "/astrbot_plugin_earthmc/configs/list",
            self._api_configs_list, ["GET"], "列出所有群/私聊配置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/configs/get",
            self._api_configs_get, ["GET"], "获取单个配置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/configs/save",
            self._api_configs_save, ["POST"], "保存配置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/configs/del",
            self._api_configs_del, ["POST"], "删除配置")

        # ── WebUI VP 提醒 API（独立于 watch） ──
        context.register_web_api(
            "/astrbot_plugin_earthmc/vp/status",
            self._api_vp_status, ["GET"], "获取某群 VP 配置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/vp/save",
            self._api_vp_save, ["POST"], "保存 VP 设置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/vp/off",
            self._api_vp_off, ["POST"], "清除 VP 提醒线")

        # ── WebUI Watch 管理 API（玩家/城镇） ──
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/groups",
            self._api_watch_groups, ["GET"], "列出有 watch 的群")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/status",
            self._api_watch_status, ["GET"], "获取某群 watch 配置")
        # 兼容：旧 VP 保存路径（浏览器缓存旧 app.js 时仍可用）
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/vp/save",
            self._api_vp_save, ["POST"], "保存 VP 设置（兼容旧路径）")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/player/add",
            self._api_watch_player_add, ["POST"], "添加玩家监控")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/player/del",
            self._api_watch_player_del, ["POST"], "删除玩家监控")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/town/add",
            self._api_watch_town_add, ["POST"], "添加城镇监控")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/town/del",
            self._api_watch_town_del, ["POST"], "删除城镇监控")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/off",
            self._api_watch_off, ["POST"], "关闭某群 watch")

        try:
            self.context.add_llm_tools(*ALL_TOOLS)
            logger.info("[EarthMC] 已注册 16 个 LLM 工具")
        except Exception as e:
            logger.warning(f"[EarthMC] LLM 工具注册失败: {e}")

        # watch 在 __init__ 直接启动，确保重载插件后也能恢复
        self.watch.start()

    # ── 命令调度 ──────────────────────

    def _cmd_prelude(self, event: AstrMessageEvent, names: tuple):
        """命令公共前置：记录会话、检查功能开关、剥离命令前缀（兼容带不带 /）。
        返回 (uid, 剩余文本)；返回 None 表示该会话已关闭 /em 命令，应直接跳过。"""
        uid = str(event.message_obj.group_id or event.message_obj.session_id)
        store.record_conversation(uid, "group" if event.message_obj.group_id else "friend")
        if not store.feature_enabled(store.load_feature_config(uid), "commands"):
            return None
        t = event.message_str.strip()
        if t.startswith("/"):
            t = t[1:]
        low = t.lower()
        for n in names:
            if low == n:
                return uid, ""
            if low.startswith(n + " "):
                return uid, t[len(n) + 1:].strip()
        return uid, t

    @filter.command("em", priority=10)
    async def cmd_em(self, event: AstrMessageEvent):
        """EarthMC 查询：/em status|vp|town|nation|player|online|nearby|location|quarter|mm|watch"""
        pre = self._cmd_prelude(event, ("em",))
        if not pre:
            return
        uid, text = pre

        if not text:
            yield event.plain_result(HELP_TEXT)
            event.stop_event()
            return

        parts = text.split(maxsplit=3)
        sub = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""
        arg3 = parts[3] if len(parts) > 3 else ""

        # 执行 confirm/cancel 以外的命令时，自动取消本群待确认的操作
        if sub not in ("confirm", "cancel"):
            self._pending_confirm.pop(uid, None)

        if sub == "help":
            yield event.plain_result(HELP_TEXT)
            event.stop_event()
            return

        if sub in ("confirm", "cancel"):
            result = (self._handle_confirm(event) if sub == "confirm"
                      else self._handle_cancel(event))
            yield event.plain_result(result)
            event.stop_event()
            return

        if sub == "vp":
            # 裸 /em vp → 查询投票派对进度（任意会话可用）
            if not arg:
                yield event.plain_result(await VotePartyTool().call(None))
                event.stop_event()
                return
            # 带参 → VP 提醒配置（仅群聊；只认 group_id，私聊 session_id 是 QQ 不能兜底）
            group_id = event.message_obj.group_id
            if not group_id:
                yield event.plain_result("❌ VP 提醒配置仅在群聊中可用。")
                event.stop_event()
                return
            vp_val = " ".join(x for x in (arg, arg2, arg3) if x)
            yield event.plain_result(
                await self._cmd_vp(event, vp_val, str(group_id)))
            event.stop_event()
            return

        if sub == "watch":
            value = f"{arg2} {arg3}".strip() if arg3 else arg2
            yield event.plain_result(
                await self._handle_watch(event, arg, value))
            event.stop_event()
            return

        if sub == "risk":
            if not arg:
                yield event.plain_result(RISK_HELP)
                event.stop_event()
                return
            value = f"{arg2} {arg3}".strip() if arg3 else arg2
            yield event.plain_result(
                await self._handle_risk(event, arg, value))
            event.stop_event()
            return

        if sub == "market":
            value = f"{arg2} {arg3}".strip() if arg3 else arg2
            yield event.plain_result(
                await self._handle_market(event, arg, value))
            event.stop_event()
            return

        if sub == "map":
            map_value = f"{arg} {arg2}".strip()
            yield event.plain_result(
                await self._handle_map(event, map_value))
            event.stop_event()
            return

        if sub in ("wp", "waypoint"):
            value = f"{arg2} {arg3}".strip() if arg3 else arg2
            yield event.plain_result(
                await self._handle_wp(event, arg, value))
            event.stop_event()
            return

        tool_cls = TOOL_MAP.get(sub)
        if tool_cls is None:
            yield event.plain_result(f"❌ 未知子命令: {sub}\n\n{HELP_TEXT}")
            event.stop_event()
            return

        try:
            if tool_cls is LocationTool:
                result = await _run_location(arg, arg2)
            else:
                result = await _run_tool(tool_cls, arg)
            yield event.plain_result(str(result))
        except Exception as e:
            logger.error(f"[EarthMC] 命令 /em {text} 执行失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {e}")
        finally:
            event.stop_event()

    # ── 顶层别名命令（/vp、/res、/t、/n） ──

    @filter.command("vp", priority=10)
    async def cmd_vp_alias(self, event: AstrMessageEvent):
        """VP 提醒（`/em vp` 的别名）：裸命令查询进度，带参配置。"""
        pre = self._cmd_prelude(event, ("vp",))
        if not pre:
            return
        uid, text = pre
        self._pending_confirm.pop(uid, None)
        if not text:                       # 裸 /vp → 查询进度
            yield event.plain_result(await VotePartyTool().call(None))
            event.stop_event()
            return
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("❌ VP 提醒配置仅在群聊中可用。")
            event.stop_event()
            return
        yield event.plain_result(await self._cmd_vp(event, text, str(group_id)))
        event.stop_event()

    @filter.command("res", priority=10)
    async def cmd_res_alias(self, event: AstrMessageEvent):
        """玩家查询（`/em player` 的别名）。"""
        pre = self._cmd_prelude(event, ("res",))
        if not pre:
            return
        uid, text = pre
        self._pending_confirm.pop(uid, None)
        yield event.plain_result(await _run_tool(PlayerTool, _first_token(text)))
        event.stop_event()

    @filter.command("t", priority=10)
    async def cmd_t_alias(self, event: AstrMessageEvent):
        """城镇查询（`/em town` 的别名）。"""
        pre = self._cmd_prelude(event, ("t",))
        if not pre:
            return
        uid, text = pre
        self._pending_confirm.pop(uid, None)
        yield event.plain_result(await _run_tool(TownTool, _first_token(text)))
        event.stop_event()

    @filter.command("n", priority=10)
    async def cmd_n_alias(self, event: AstrMessageEvent):
        """国家查询（`/em nation` 的别名）。"""
        pre = self._cmd_prelude(event, ("n",))
        if not pre:
            return
        uid, text = pre
        self._pending_confirm.pop(uid, None)
        yield event.plain_result(await _run_tool(NationTool, _first_token(text)))
        event.stop_event()

    @filter.command("mctop", priority=10)
    async def cmd_mctop_alias(self, event: AstrMessageEvent):
        """mcMMO 排行榜（`/em mmo` 的别名）：/mctop <技能>。"""
        pre = self._cmd_prelude(event, ("mctop",))
        if not pre:
            return
        uid, text = pre
        self._pending_confirm.pop(uid, None)
        yield event.plain_result(await _run_tool(McMMOTopTool, _first_token(text)))
        event.stop_event()

    # ── watch 子命令 ───────────────────

    # ── risk 子命令 ───────────────────

    # ── market 子命令 ───────────────────

    # ── map 子命令 ───────────────────

    # ── Watch 管理 API ──────────────────

    @staticmethod
    @staticmethod
    @classmethod
    # ── wp 子命令 ───────────────────

    # ── 生命周期 ──────────────────────

    @filter.on_astrbot_loaded()
    async def _start_background(self):
        self.watch.start()
        self.ruins_checker.start()

    async def terminate(self):
        await self.watch.stop()
        await self.ruins_checker.stop()
        await close_session()
        logger.info("[EarthMC] 插件已卸载")
