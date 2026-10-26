"""
AstrBot 插件：EarthMC 服务器信息查询 v1.13.1
/em 命令 · LLM Agent 工具 · 自动监控 · 销城评估 · 全服扫描 · 地图截图
"""
import asyncio
import os
import time

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .api import close_session, configure as api_configure
from .tools import (
    ServerStatusTool, VotePartyTool, TownTool, NationTool,
    PlayerTool, OnlinePlayersTool, NearbyTownsTool,
    LocationTool, QuarterTool, MysteryMasterTool, TownRiskTool,
    TownMembersTool,
    NationTownsTool,
    NationRiskTool,
    MapTownTool,
    MapPlayerTool,
    MapLocationTool,
)
from .mcmmo import McMMOTopTool
from .watch import WatchManager, current_cn_minutes, in_dnd, parse_cn_time
from .scanner import TownRiskScanner
from .market import (
    MarketManager, MarketAddTool, MarketSearchTool,
    TrialAddTool, TrialListTool, set_market_manager,
)
from .waypoints import (
    WaypointManager, WaypointAddTool, WaypointSearchTool,
    set_waypoint_manager,
)

HELP_TEXT = """🌍 EarthMC 查询
── 查询 ──
  status vp town nation player online nearby location quarter mm mmo
── 地图 ──
  /em map town <名>    城镇地图截图
  /em map player <名>  玩家位置截图
  /em map <x> <z>      坐标截图
── 路径点 ──
  /em wp              使用 /em wp help 查看子命令
── 分析 ──
  /em risk      使用 /em risk help 查看子命令
── 监控 ──
  /em vp        使用 /em vp help 查看子命令
  /em watch     使用 /em watch help 查看子命令
── 市场 ──
  /em market    使用 /em market 查看子命令
━━━━━━━━━━━━━━━━
别名: /t 城镇 · /n 国家 · /res 玩家 · /vp VP 提醒 · /mctop mcMMO 榜
也可直接 @bot 用自然语言询问"""

RISK_HELP = """销城分析:
  /em risk town <名>      单镇评估
  /em risk nation <名>    国家排名
  /em risk list [天] [页]  全服名单
  /em risk scan           手动全服扫描"""

MARKET_HELP = """市场交易:
  /em market list                   查看全部
  /em market sell add <t/n> <点> <价> <量> <物品>
      如 /em market sell add t mending 8 1 经验修补
  /em market buy add <t/n> <点> <价> <量> <物品>
  /em market trial add <t/n> <点>   记录试炼密室
  /em market <sell|buy> search <关键词>
  /em market <sell|buy|trial> del <id>
  /em market <sell|buy|trial>       查看对应类型
━━━━━━━━━━━━━━━━
也可直接告诉机器人: /t spawn mending有8g一本经验修补 / mending有试炼密室"""

WAYPOINT_HELP = """路径点:
  /em wp add <世界> <名称> <x> <y> <z>   记录（overworld主世界/nether地狱）
      如 /em wp add overworld 刷铁机 100 64 -200
  /em wp search <关键词> [世界]           搜索
  /em wp del <id>                        删除
  /em wp list [世界]                     查看全部"""

WATCH_HELP = """自动监控:
  /em watch player add <名>          添加玩家监控
  /em watch player del <名>          移除玩家监控
  /em watch player                   查看监控玩家列表
  /em watch town add <名>            添加城镇监控
  /em watch town del <名>            移除城镇监控
  /em watch town                     查看监控城镇列表
  /em watch off                      关闭所有（/em confirm 确认，/em cancel 取消）
  /em watch                          查看全部设置"""

VP_USAGE = ("❌ 用法: /em vp <票数> ... | at <add|del|reset|off> <QQ号> ... | "
            "atline <add|del|reset|off> <票数>... | dnd <开始> <结束> | status\n"
            "例如:\n"
            "  /em vp 500 200 100\n"
            "  /em vp at add 123456\n"
            "  /em vp at del 123456\n"
            "  /em vp at reset 123456 654321\n"
            "  /em vp at off\n"
            "  /em vp atline add 200\n"
            "  /em vp atline del 200\n"
            "  /em vp atline reset 200 100\n"
            "  /em vp dnd 23:00 07:30\n"
            "  /em vp dnd off\n"
            "  /em vp status")

# at / atline 的操作关键字别名
_OP_ALIASES = {
    "add": "add", "添加": "add",
    "del": "del", "delete": "del", "remove": "del", "删除": "del", "移除": "del",
    "reset": "reset", "重设": "reset",
}


def _first_token(text: str) -> str:
    """取首个空白分隔的 token（多余文本静默截断）；无内容返回空串。"""
    parts = text.split(maxsplit=1)
    return parts[0] if parts else ""

ALL_TOOLS = [
    ServerStatusTool(), VotePartyTool(), TownTool(), NationTool(),
    PlayerTool(), OnlinePlayersTool(), NearbyTownsTool(),
    LocationTool(), QuarterTool(), MysteryMasterTool(), TownRiskTool(),
    TownMembersTool(),
    NationTownsTool(),
    NationRiskTool(),
    MapTownTool(),
    MapPlayerTool(),
    MapLocationTool(),
    McMMOTopTool(),
    MarketAddTool(),
    MarketSearchTool(),
    TrialAddTool(),
    TrialListTool(),
    WaypointAddTool(),
    WaypointSearchTool(),
]

TOOL_MAP = {
    "status":   ServerStatusTool,
    "vp":       VotePartyTool,
    "town":     TownTool,
    "nation":   NationTool,
    "player":   PlayerTool,
    "online":   OnlinePlayersTool,
    "nearby":   NearbyTownsTool,
    "location": LocationTool,
    "quarter":  QuarterTool,
    "mm":       MysteryMasterTool,
    "mmo":      McMMOTopTool,
}


class EarthMCPlugin(Star):
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
        self.scanner = TownRiskScanner(
            self.name or "astrbot_plugin_earthmc",
            self.context.send_message,
            batch_size=config.get("scan_batch_size", 100),
            concurrency=config.get("scan_concurrency", 5),
            deep_scan_max_residents=config.get("deep_scan_max_residents", 10),
            scan_hour=config.get("scan_hour", 18),
            scan_minute=config.get("scan_minute", 30),
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
        self._record_conversation(uid, "group" if event.message_obj.group_id else "friend")
        if not self._feature_enabled(self.load_feature_config(uid), "commands"):
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

    def _handle_confirm(self, event: AstrMessageEvent) -> str:
        """/em confirm：确认执行本群待确认的破坏性操作（30 秒内，限发起人）。"""
        group_id = event.message_obj.group_id
        if not group_id:
            return "❌ /em confirm 仅在群聊中可用。"
        group_key = str(group_id)
        pc = self._pending_confirm.get(group_key)
        if not pc:
            return "❌ 当前没有待确认的操作。"
        if time.time() - pc["ts"] > 30:
            self._pending_confirm.pop(group_key, None)
            return "❌ 确认已超时（30 秒），请重新发起。"
        if pc["user"] != str(event.get_sender_id()):
            return "❌ 该操作由他人发起，仅发起人可确认。"
        kind = pc.get("kind", "")
        self._pending_confirm.pop(group_key, None)
        if kind == "watch_off":
            config = self.watch.load_config()
            if group_key in config:
                del config[group_key]
                self.watch.save_config(config)
            return "✅ 已确认，本群所有自动提醒已关闭。"
        return "✅ 已确认。"

    def _handle_cancel(self, event: AstrMessageEvent) -> str:
        """/em cancel：取消本群待确认的破坏性操作。取消是保护性操作，任何群成员可取消。"""
        group_id = event.message_obj.group_id
        if not group_id:
            return "❌ /em cancel 仅在群聊中可用。"
        group_key = str(group_id)
        if group_key in self._pending_confirm:
            self._pending_confirm.pop(group_key)
            return "✅ 已取消该操作。"
        return "❌ 当前没有待取消的操作。"

    async def _handle_watch(self, event: AstrMessageEvent,
                            action: str, value: str) -> str:
        group_id = event.message_obj.group_id or event.message_obj.session_id
        if not group_id:
            return "❌ watch 功能仅在群聊中可用。"

        action = action.lower()
        group_key = str(group_id)

        # 帮助
        if action in ("help",):
            return WATCH_HELP

        # 关闭（两步确认：先登记，回复 /em confirm 执行）
        if action in ("off", "stop", "关闭"):
            config = self.watch.load_config()
            if group_key not in config:
                return "⚠ 本群未开启自动提醒。"
            self._pending_confirm[group_key] = {
                "user": str(event.get_sender_id()),
                "ts": time.time(),
                "kind": "watch_off",
            }
            return ("⚠ 将关闭本群**所有**自动提醒（VP/玩家/城镇监控），不可撤销。\n"
                    "回复 /em confirm 确认 /em cancel 取消（30 秒内有效）。")

        # 玩家
        if action in ("player", "players"):
            return await self._cmd_watch_player(event, value, group_key)

        # 城镇
        if action in ("town",):
            return await self._cmd_watch_town(event, value, group_key)

        # 查看全部
        return self._cmd_watch_status(group_key)

    async def _cmd_vp(self, event: AstrMessageEvent,
                       value: str, group_key: str) -> str:
        if not value or value.strip().lower() in ("help", "帮助", "?"):
            return ("📊 VP 提醒用法\n━━━━━━━━━━━━━━━━\n"
                    "/em vp <票数> ...              多级提醒\n"
                    "/em vp at add|del|reset|off <QQ号>   @ 名单\n"
                    "/em vp atline add|del|reset|off <票数>  标记哪些线触发 @\n"
                    "/em vp dnd <开始> <结束>        免打扰(UTC+8)\n"
                    "/em vp off                     清除 VP 阈值\n"
                    "/em vp status                  查看本群配置\n"
                    "（留空 at/atline 显示当前配置）")

        tokens = value.replace(",", " ").split()
        mode = None                 # None=阈值上下文 | "at" | "atline" | "dnd"
        thresholds: list[int] = []
        at_list: list[int] = []
        atline_list: list[int] = []
        dnd_tokens: list[str] = []
        do_status = False
        at_op = atline_op = None    # None=留空(不操作) | "add" | "del" | "reset"
        clear_th = clear_at = clear_atlines = clear_dnd = False

        for tok in tokens:
            low = tok.lower()
            if low in ("at", "@"):
                mode = "at"
            elif low == "atline":
                mode = "atline"
            elif low == "dnd":
                mode = "dnd"
            elif low in ("off", "clear", "none"):
                if mode == "at":
                    clear_at = True
                elif mode == "atline":
                    clear_atlines = True
                elif mode == "dnd":
                    clear_dnd = True
                else:
                    clear_th = True
            elif low == "status":
                do_status = True
            elif mode == "at":
                op = _OP_ALIASES.get(low)
                if op:
                    if at_op:
                        return f"❌ 冲突：at 只能指定一个操作（add/del/reset）\n\n{VP_USAGE}"
                    at_op = op
                elif tok.isdigit():
                    if at_op is None:
                        return ("❌ /em vp at 需要关键字：add|del|reset|off <QQ号>\n"
                                "   例如 /em vp at add 123456\n\n" + VP_USAGE)
                    at_list.append(int(tok))
                else:
                    break          # 格式不符 → 静默截断，忽略其后全部
            elif mode == "atline":
                op = _OP_ALIASES.get(low)
                if op:
                    if atline_op:
                        return f"❌ 冲突：atline 只能指定一个操作（add/del/reset）\n\n{VP_USAGE}"
                    atline_op = op
                elif tok.isdigit():
                    if atline_op is None:
                        return ("❌ /em vp atline 需要关键字：add|del|reset|off <票数>\n"
                                "   例如 /em vp atline add 200\n\n" + VP_USAGE)
                    atline_list.append(int(tok))
                else:
                    break          # 格式不符 → 静默截断，忽略其后全部
            elif mode == "dnd":
                if len(dnd_tokens) >= 2:
                    break          # 已够起止两个时间 → 静默截断
                dnd_tokens.append(tok)
            else:
                try:
                    t = int(tok)
                except ValueError:
                    break          # 非数字 → 静默截断，忽略其后全部
                if t <= 0:
                    return f"❌ 票数必须大于 0: {tok}\n\n{VP_USAGE}"
                thresholds.append(t)

        if do_status:
            return self._vp_status_text(group_key)

        # at / atline 留空（无操作、无 clear）→ 不修改配置，显示当前配置
        if mode == "at" and at_op is None and not at_list and not clear_at:
            return self._vp_status_text(group_key)
        if mode == "atline" and atline_op is None and not atline_list and not clear_atlines:
            return self._vp_status_text(group_key)

        # 缺参边界
        if mode == "at" and at_op and not at_list:
            return f"❌ at {at_op} 后面至少需要一个 QQ 号\n\n{VP_USAGE}"
        if mode == "atline" and atline_op and not atline_list:
            return f"❌ atline {atline_op} 后面至少需要一个票数\n\n{VP_USAGE}"
        if mode == "dnd" and not dnd_tokens and not clear_dnd:
            return f"❌ /em vp dnd 需要起止两个时间\n\n{VP_USAGE}"
        # 既操作又清除
        if clear_at and (at_list or at_op):
            return f"❌ 冲突：at 与 at off 不能同时使用\n\n{VP_USAGE}"
        if clear_atlines and (atline_list or atline_op):
            return f"❌ 冲突：atline 与 atline off 不能同时使用\n\n{VP_USAGE}"
        if clear_dnd and dnd_tokens:
            return f"❌ 冲突：dnd 与 dnd off 不能同时使用\n\n{VP_USAGE}"

        # 免打扰时间解析校验
        dnd_start = dnd_end = None
        if dnd_tokens:
            if len(dnd_tokens) == 1:
                return f"❌ 免打扰需要起止两个时间\n\n{VP_USAGE}"
            if (parse_cn_time(dnd_tokens[0]) is None
                    or parse_cn_time(dnd_tokens[1]) is None):
                return (f"❌ 免打扰时间格式无效: {dnd_tokens[0]} {dnd_tokens[1]}"
                        f"（支持 HH:MM 或裸小时）\n\n{VP_USAGE}")
            dnd_start, dnd_end = dnd_tokens[0], dnd_tokens[1]

        # 落盘
        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]

        # atline 校验：标记的票数必须在提醒线中，否则拒绝存储（del 不校验，否则删非提醒线值会被误拦）
        if atline_list and atline_op != "del":
            valid = set(thresholds) | set(w.get("vp_thresholds") or [])
            bad = sorted({t for t in atline_list if t not in valid})
            if bad:
                cur = (" > ".join(str(t) for t in sorted(valid, reverse=True))
                       if valid else "未设置")
                return (f"❌ {'、'.join(str(t) for t in bad)} 不在提醒线中（当前 {cur}）\n"
                        f"   请先用 /em vp 添加该线，或 /em vp atline off 清除\n\n"
                        f"{VP_USAGE}")

        msgs = []
        if clear_th:
            w.pop("vp_thresholds", None)
            w.pop("vp_at_lines", None)   # 阈值没了，@ 标记随之失效
            w["vp_last"] = None          # 重置基线，避免下次加回阈值时误报
            thresholds = []
            msgs.append("✅ 已清除 VP 阈值")
        if clear_at:
            w.pop("vp_at", None)
            at_list = []
            at_op = None
            msgs.append("✅ 已清空 @ 名单")
        if clear_atlines:
            w.pop("vp_at_lines", None)
            atline_list = []
            atline_op = None
            msgs.append("✅ 已清除 @ 触发线（默认不 @）")
        if clear_dnd:
            w.pop("vp_dnd_start", None)
            w.pop("vp_dnd_end", None)
            dnd_start = dnd_end = None
            msgs.append("✅ 已关闭免打扰")

        if thresholds:
            uniq = []
            for t in sorted(thresholds, reverse=True):
                if t not in uniq:
                    uniq.append(t)
            w["vp_thresholds"] = uniq
            w.setdefault("vp_last")
            msgs.append("✅ VP 多级提醒已开启")
            msgs.extend(f"  • 降至 {t} 票时提醒" for t in uniq)

        # @ 名单：add / del / reset
        if at_op:
            cur = list(w.get("vp_at") or [])
            if at_op == "add":
                added = [q for q in at_list if q not in cur]
                cur += added
                w["vp_at"] = cur
                msgs.append(f"✅ 已添加 @ 名单: {' '.join(map(str, added))}" if added
                            else "⚠ 这些 QQ 已在 @ 名单中。")
            elif at_op == "del":
                removed = [q for q in at_list if q in cur]
                cur = [q for q in cur if q not in at_list]
                if cur:
                    w["vp_at"] = cur
                else:
                    w.pop("vp_at", None)
                msgs.append(f"✅ 已移除 @ 名单: {' '.join(map(str, removed))}" if removed
                            else "⚠ 这些 QQ 不在 @ 名单中。")
            else:  # reset
                uniq = []
                for q in at_list:
                    if q not in uniq:
                        uniq.append(q)
                w["vp_at"] = uniq
                msgs.append("✅ @ 名单: " + " ".join(str(q) for q in uniq))

        # @ 触发线：add / del / reset
        if atline_op:
            cur = list(w.get("vp_at_lines") or [])
            if atline_op == "add":
                added = [t for t in atline_list if t not in cur]
                cur += added
                cur.sort(reverse=True)
                w["vp_at_lines"] = cur
                msgs.append(f"✅ 已添加 @ 触发线: {' > '.join(map(str, sorted(added, reverse=True)))}" if added
                            else "⚠ 这些提醒线已在 @ 触发线中。")
            elif atline_op == "del":
                removed = [t for t in atline_list if t in cur]
                cur = [t for t in cur if t not in atline_list]
                if cur:
                    w["vp_at_lines"] = cur
                else:
                    w.pop("vp_at_lines", None)
                msgs.append(f"✅ 已移除 @ 触发线: {' > '.join(map(str, sorted(removed, reverse=True)))}" if removed
                            else "⚠ 这些提醒线不在 @ 触发线中。")
            else:  # reset
                uniq = []
                for t in sorted(atline_list, reverse=True):
                    if t not in uniq:
                        uniq.append(t)
                w["vp_at_lines"] = uniq
                msgs.append("✅ @ 触发线: " + " > ".join(str(t) for t in uniq))

        if dnd_start is not None:
            w["vp_dnd_start"] = dnd_start
            w["vp_dnd_end"] = dnd_end
            msgs.append(f"✅ 免打扰: {dnd_start} - {dnd_end} (UTC+8)")

        self.watch.save_config(config)
        self.watch.ensure_running()

        if not msgs:
            return self._vp_status_text(group_key)

        return ("\n".join(msgs) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"查看: /em vp status")

    async def _cmd_watch_player(self, event: AstrMessageEvent,
                                 value: str, group_key: str) -> str:
        parts = value.split(maxsplit=1)
        sub_action = parts[0].lower() if parts else ""
        names_str = parts[1] if len(parts) > 1 else ""

        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]
        watched: dict = w.setdefault("players", {})

        # 添加
        if sub_action in ("add", "添加"):
            if not names_str:
                return ("❌ 用法: /em watch player add <玩家名> ...\n"
                        "例如: /em watch player add Fixer Warriorrr")
            existing_lower = {k.lower() for k in watched}
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in existing_lower]
            if not new:
                return "⚠ 这些玩家已在监控列表中。"

            # 校验玩家是否存在，并记录当前城镇作为基线
            from .api import post as api_post
            data = await api_post("/players", {"query": new})
            existing = set()
            town_map = {}
            canon = {}
            if data and isinstance(data, list):
                existing = {p.get("name", "").lower() for p in data}
                town_map = {p.get("name", "").lower(): (p.get("town") or {}).get("name", "")
                            for p in data}
                canon = {p.get("name", "").lower(): p.get("name", "")
                         for p in data if p.get("name")}

            valid, invalid = [], []
            for name in new:
                (valid if name.lower() in existing else invalid).append(name)

            added = []
            for name in valid:
                cname = canon.get(name.lower(), name)   # 落服务端规范大小写
                watched[cname] = {"online": False,
                                  "town": town_map.get(name.lower(), "")}
                added.append(cname)
            if valid:
                self.watch.save_config(config)
                self.watch.ensure_running()

            msg_parts = []
            if added:
                msg_parts.append(f"✅ 已添加: {', '.join(added)}")
            if invalid:
                msg_parts.append(f"❌ 玩家不存在: {', '.join(invalid)}")
            return "\n".join(msg_parts) if msg_parts else "⚠ 未能添加任何玩家。"

        # 删除
        if sub_action in ("del", "delete", "remove", "删除", "移除"):
            if not names_str:
                return ("❌ 用法: /em watch player del <玩家名>\n"
                        "例如: /em watch player del Fixer")
            names = [n.strip() for n in names_str.replace(",", " ").split()]
            names_lower = {n.lower() for n in names}
            removed = [k for k in watched if k.lower() in names_lower]
            for k in removed:
                del watched[k]
            if not removed:
                return "⚠ 这些玩家不在监控列表中。"
            if not watched:
                del w["players"]
            self.watch.save_config(config)
            return (f"✅ 已移除玩家监控\n━━━━━━━━━━━━━━━━\n"
                    f"👤 {', '.join(removed)}")

        # 查看
        if not watched:
            return ("📊 玩家上线监控: 未添加\n━━━━━━━━━━━━━━━━\n"
                    "添加: /em watch player add <玩家名>\n"
                    "例如: /em watch player add Fixer")

        lines = []
        for name, state in sorted(watched.items()):
            s = "🟢 在线" if state.get("online") else "🔴 离线"
            lines.append(f"  {name}  {s}")
        return (f"📊 玩家上线监控 ({len(watched)} 人)\n"
                f"━━━━━━━━━━━━━━━━\n" + "\n".join(lines) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"添加: /em watch player add <名>\n"
                f"移除: /em watch player del <名>")

    async def _cmd_watch_town(self, event: AstrMessageEvent,
                               value: str, group_key: str) -> str:
        parts = value.split(maxsplit=1)
        sub_action = parts[0].lower() if parts else ""
        names_str = parts[1] if len(parts) > 1 else ""

        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]
        watched: dict = w.setdefault("towns", {})

        if sub_action in ("add", "添加"):
            if not names_str:
                return ("❌ 用法: /em watch town add <城镇名> ...\n"
                        "例如: /em watch town add Beijing Shanghai")
            existing_lower = {k.lower() for k in watched}
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in existing_lower]
            if not new:
                return "⚠ 这些城镇已在监控列表中。"

            from .api import post as tpost
            tdata = await tpost("/towns", {"query": new})
            valid, invalid = [], []
            if tdata and isinstance(tdata, list):
                existing = {t.get("name", "").lower() for t in tdata}
                for n in new:
                    (valid if n.lower() in existing else invalid).append(n)
            else:
                invalid = new

            # 拉取城镇的当前状态作为初始值
            for t in tdata:
                if isinstance(t, dict):
                    tname = t.get("name", "")
                    if tname.lower() in [n.lower() for n in valid]:
                        stats = t.get("stats") or {}
                        cur_names = sorted(
                            r.get("name", "") for r in (t.get("residents") or []))
                        watched[tname] = {
                            "resident_count": stats.get("numResidents", 0),
                            "residents": cur_names,
                            "blocks": stats.get("numTownBlocks", 0),
                            "maxBlocks": stats.get("maxTownBlocks", 0),
                            "balance": stats.get("balance", 0),
                            "mayor": (t.get("mayor") or {}).get("name", ""),
                            "nation": (t.get("nation") or {}).get("name", ""),
                            "is_open": (t.get("status") or {}).get("isOpen", False),
                            "is_ruined": (t.get("status") or {}).get("isRuined", False),
                        }
            if valid:
                self.watch.save_config(config)
                self.watch.ensure_running()

            lines = []
            if valid:
                lines.append("✅ 已添加城镇监控:")
                for t in tdata:
                    if isinstance(t, dict) and t.get("name", "").lower() in [n.lower() for n in valid]:
                        s = t.get("stats") or {}
                        mayor = (t.get("mayor") or {}).get("name", "?")
                        nation = (t.get("nation") or {}).get("name", "无")
                        lines.append(
                            f"  {t['name']}({nation})  {s.get('numResidents',0)}人  "
                            f"{s.get('numTownBlocks',0)}方块  {s.get('balance',0)}G  市长{mayor}")
            if invalid:
                lines.append("❌ 城镇不存在: " + ", ".join(invalid))
            return "\n".join(lines) if lines else "⚠ 未能添加任何城镇。"

        if sub_action in ("del", "delete", "remove", "删除", "移除"):
            if not names_str:
                return ("❌ 用法: /em watch town del <城镇名>\n"
                        "例如: /em watch town del Beijing")
            names = [n.strip() for n in names_str.replace(",", " ").split()]
            names_lower = {n.lower() for n in names}
            removed = [k for k in watched if k.lower() in names_lower]
            for k in removed:
                del watched[k]
            if not removed:
                return "⚠ 这些城镇不在监控列表中。"
            if not watched:
                del w["towns"]
            self.watch.save_config(config)
            return f"✅ 已移除城镇监控: {', '.join(removed)}"

        if not watched:
            return ("📊 城镇变动监控: 未添加\n━━━━━━━━━━━━━━━━\n"
                    "添加: /em watch town add <城镇名>\n"
                    "例如: /em watch town add Beijing")

        lines = [f"📊 城镇变动监控 ({len(watched)} 个)"]
        for name in sorted(watched):
            old = watched[name]
            r = old.get("resident_count", "?")
            b = old.get("blocks", "?")
            bal = old.get("balance", "?")
            lines.append(f"  {name}  {r}人  {b}方块  {bal}G")
        return "\n".join(lines)

    def _vp_status_text(self, group_key: str) -> str:
        config = self.watch.load_config()
        w = config.get(group_key)
        if not w:
            return ("📊 VP 提醒: 未开启\n━━━━━━━━━━━━━━━━\n"
                    "开启: /em vp <票数> ...\n"
                    "例如: /em vp 500 200 100")

        lines = []
        th = w.get("vp_thresholds")
        if th:
            lines.append("🎯 VP 提醒线: " +
                         " > ".join(str(t) for t in sorted(th, reverse=True)))
        else:
            lines.append("🎯 VP 提醒: 未设置")

        at = w.get("vp_at")
        if at:
            lines.append("📣 @ 名单: " + " ".join(str(q) for q in at))
        else:
            lines.append("📣 @ 名单: 未设置（仅纯文本）")

        at_lines = w.get("vp_at_lines")
        if at_lines:
            lines.append("🎯 @ 触发线: " +
                         " > ".join(str(t) for t in sorted(at_lines, reverse=True)))
        else:
            lines.append("🎯 @ 触发线: 未设置（默认不 @）")

        ds, de = w.get("vp_dnd_start"), w.get("vp_dnd_end")
        if ds and de:
            lines.append(f"🌙 免打扰: {ds} - {de} (UTC+8)")
        else:
            lines.append("🌙 免打扰: 未设置")

        now = current_cn_minutes()
        cur = f"{now // 60:02d}:{now % 60:02d}"
        lines.append(f"🕐 当前(UTC+8): {cur}  →  "
                     + ("免打扰中（不 @）" if in_dnd(w) else "正常提醒"))

        return ("📊 VP 提醒设置\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
                + "\n━━━━━━━━━━━━━━━━")

    def _cmd_watch_status(self, group_key: str) -> str:
        config = self.watch.load_config()
        w = config.get(group_key)
        if not w:
            return ("📊 本群自动提醒: 未开启\n━━━━━━━━━━━━━━━━\n"
                    "开启 VP: /em vp <票数> ...\n"
                    "添加玩家: /em watch player add <名>\n"
                    "查看全部: /em watch")

        parts = []
        th = w.get("vp_thresholds")
        if th:
            parts.append("🎯 VP 提醒线: " +
                         " > ".join(str(t) for t in sorted(th, reverse=True)))
        else:
            parts.append("🎯 VP 提醒: 未设置")

        at = w.get("vp_at")
        if at:
            parts.append("📣 @ 名单: " + " ".join(str(q) for q in at))
        else:
            parts.append("📣 @ 名单: 未设置")

        at_lines = w.get("vp_at_lines")
        if at_lines:
            parts.append("🎯 @ 触发线: " +
                         " > ".join(str(t) for t in sorted(at_lines, reverse=True)))
        else:
            parts.append("🎯 @ 触发线: 未设置（默认不 @）")

        ds, de = w.get("vp_dnd_start"), w.get("vp_dnd_end")
        if ds and de:
            parts.append(f"🌙 免打扰: {ds} - {de} (UTC+8)")
        else:
            parts.append("🌙 免打扰: 未设置")

        pl = w.get("players")
        if pl:
            parts.append(f"👤 玩家监控({len(pl)}): " + ", ".join(sorted(pl)))
        else:
            parts.append("👤 玩家监控: 未设置")

        tl = w.get("towns")
        if tl:
            parts.append(f"🏘 城镇监控({len(tl)}): " + ", ".join(sorted(tl)))
        else:
            parts.append("🏘 城镇监控: 未设置")

        return (f"📊 本群自动提醒设置\n━━━━━━━━━━━━━━━━\n" +
                "\n".join(parts) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"状态: 运行中 ✅\n"
                f"关闭: /em watch off")

    # ── risk 子命令 ───────────────────

    async def _handle_risk(self, event: AstrMessageEvent,
                            action: str, value: str) -> str:
        action = action.lower()

        if action in ("help",):
            return RISK_HELP

        if action in ("nation",):
            nation = value.strip() if value.strip() else ""
            if not nation:
                return "❌ 用法: /em risk nation <国家名>"
            from .tools import _nation_risk
            return await _nation_risk(nation)

        if action in ("scan",):
            umo = event.unified_msg_origin

            async def done(risk_count: int, total: int):
                try:
                    if risk_count < 0:
                        await self.context.send_message(
                            umo, MessageChain().message(
                                "❌ 全服扫描失败，无法获取城镇列表。"))
                    else:
                        await self.context.send_message(
                            umo, MessageChain().message(
                                f"✅ 全服扫描完成\n━━━━━━━━━━━━━━━━\n"
                                f"共检查 {total} 个城镇\n"
                                f"5天内可能销城 {risk_count} 个\n"
                                f"━━━━━━━━━━━━━━━━\n"
                                f"查看名单: /em risk list"))
                    logger.info("[EarthMC] 扫描通知已发送")
                except Exception as e:
                    logger.error(f"[EarthMC] 扫描通知发送失败: {e}")

            asyncio.create_task(self.scanner.scan(on_done=done))
            return "🔍 开始全服扫描，请稍候...完成后将自动通知。"

        if action in ("list",):
            # 解析: /em risk list [天数] [页码]
            # 天数=0 仅Ruins, 1~N 各自独立显示该天数段
            parts = value.split() if value.strip() else []
            days = 5
            page = 1
            if len(parts) >= 1 and parts[0].isdigit():
                days = int(parts[0])
            if len(parts) >= 2 and parts[1].isdigit():
                page = int(parts[1])
            PAGE_SIZE = 20

            # 按 days 决定筛选范围（独立，不累计）
            if days == 0:
                label = "Ruins"
                lo, hi = 0, 0
            elif days == 1:
                label = "1天"
                lo, hi = 0.01, 1
            else:
                label = f"{days}天"
                lo, hi = days, days + 0.99

            towns = self.scanner.get_risklist(days)
            updated = self.scanner.cache_age()
            # 按独立范围过滤
            towns = [t for t in towns if lo <= t["days_left"] <= hi]
            if not towns:
                return (f"📋 {label}销城风险: 无\n"
                        f"更新时间 {updated}\n"
                        f"手动扫描: /em risk scan")

            total_pages = max((len(towns) + PAGE_SIZE - 1) // PAGE_SIZE, 1)
            page = max(1, min(page, total_pages))
            start = (page - 1) * PAGE_SIZE
            end = page * PAGE_SIZE

            lines = [f"📋 {label}销城风险 ({len(towns)} 个)  更新 {updated}  第{page}/{total_pages}页"]
            shown = 0
            for t in towns:
                if shown >= end:
                    break
                if shown < start:
                    shown += 1
                    continue
                shown += 1
                d = t["days_left"]
                if d < 1:
                    day_str = "不足1天"
                elif d < 2:
                    day_str = f"约{int(d)}天"
                else:
                    day_str = f"{int(d)}天"
                lines.append(
                    f"  {t['name']}({t['nation']}) "
                    f"剩{day_str} 活跃{t['active_count']}人 ★{t['defense']}")
            if page < total_pages:
                lines.append(f"下一页: /em risk list {days} {page + 1}")
            return "\n".join(lines)

        if action in ("town",):
            from .tools import _calc_risk
            return await _calc_risk(value) if value else "❌ 用法: /em risk town <城镇名>"

        return ("❌ 用法:\n"
                "  /em risk town <名>    评估单个城镇\n"
                "  /em risk nation <名>  国家销城排名\n"
                "  /em risk list [天] [页] 查看风险名单\n"
                "  /em risk scan          手动全服扫描")

    # ── market 子命令 ───────────────────

    async def _handle_market(self, event: AstrMessageEvent,
                              action: str, value: str) -> str:
        action = action.lower()

        if action in ("help",):
            return MARKET_HELP

        if action in ("list", "all"):
            data = self.market.list_all()
            if not data:
                return "📦 市场暂无记录。"
            lines = [f"📦 市场记录 ({len(data)} 条)"]
            for r in data:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 分类型子命令: trial/sell/buy
        action_map = {"sell": "出售", "buy": "收购", "trial": "试炼"}
        if action in action_map:
            act = action_map[action]
            return self._handle_market_action(act, value)

        return MARKET_HELP

    def _handle_market_action(self, act: str, value: str) -> str:
        """处理 /em market <trial|sell|buy> <sub> [args]"""
        parts = value.split(maxsplit=1) if value.strip() else []
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        # 列表
        if not sub or sub in ("list", "all"):
            data = self.market.list_by_action(act)
            if not data:
                return f"📦 {act}记录: 暂无"
            lines = [f"📦 {act}记录 ({len(data)} 条)"]
            for r in data:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 搜索（试炼不搜索，只列出）
        if sub in ("search", "查") and act != "试炼":
            if not rest:
                return f"❌ 用法: /em market {act.lower()} search <关键词>"
            results = self.market.search(rest, act)
            if not results:
                return f"📦 {act}查询 \"{rest}\"\n暂无相关记录。"
            lines = [f"📦 {act}查询 \"{rest}\""]
            for r in results:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 添加
        if sub in ("add", "添加"):
            rp = rest.split() if rest else []
            if not rp:
                return (f"❌ 用法: /em market {act.lower()} add "
                        f"<t/n> <传送点名> [价格 数量 物品名]")

            tp = rp[0].lower()
            if tp not in ("t", "n"):
                return "❌ 类型必须是 t（城镇传送点）或 n（国家传送点）"
            if len(rp) < 2:
                return "❌ 缺少传送点名称。"

            if act == "试炼":
                entry = {
                    "type": tp,
                    "location": rp[1],
                    "action": act,
                    "item": "试炼密室",
                    "amount": 1,
                    "price": "",
                }
            else:
                if len(rp) < 5:
                    return (f"❌ 用法: /em market {act.lower()} add "
                            f"<t/n> <传送点名> <价格> <数量> <物品名>\n"
                            f"例如: /em market {act.lower()} add t mending 8 1 经验修补")
                price_raw = rp[2].rstrip("gG")
                entry = {
                    "type": tp,
                    "location": rp[1],
                    "price": f"{price_raw}g",
                    "amount": int(rp[3]) if rp[3].isdigit() else 1,
                    "item": " ".join(rp[4:]),
                    "action": act,
                }

            result = self.market.add(entry)
            eid = result["id"]
            msg = (f"✅ 已添加 #{eid}  "
                   f"{entry['type']}/{entry['location']}  "
                   f"{entry['action']}  "
                   f"{entry['price']} × {entry['amount']} {entry['item']}")
            if result.get("dup_warn"):
                msg += f"\n{result['dup_warn']}"
            return msg

        # 删除
        if sub in ("del", "delete", "remove", "删"):
            if not rest or not rest.isdigit():
                return "❌ 用法: /em market del <id>"
            eid = int(rest)
            if self.market.delete(eid):
                return f"✅ 已删除 #{eid}。"
            return f"❌ 未找到 #{eid}。"

        search_line = (f"/em market {act.lower()} search <关键词>     搜索\n"
                       if act != "试炼" else "")
        return (f"📦 {act}管理\n"
                f"/em market {act.lower()} add <t/n> <点> ...  添加\n"
                f"/em market {act.lower()} del <id>            删除\n"
                f"{search_line}"
                f"/em market {act.lower()}                     查看全部")

    # ── map 子命令 ───────────────────

    async def _handle_map(self, event: AstrMessageEvent, value: str) -> str:
        value = (value or "").strip()
        parts = value.split(maxsplit=1)
        action = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if action in ("town",):
            if not rest:
                return "❌ 用法: /em map town <城镇名>"
            return await MapTownTool().call(None, name=rest)

        if action in ("player",):
            if not rest:
                return "❌ 用法: /em map player <玩家名>"
            return await MapPlayerTool().call(None, name=rest)

        # 坐标: /em map <x> <z>
        if action.lstrip("-").isdigit() or action == "":
            coords = value.split()
            if len(coords) >= 2 and coords[0].lstrip("-").isdigit() \
                    and coords[1].lstrip("-").isdigit():
                return await MapLocationTool().call(
                    None, x=int(coords[0]), z=int(coords[1]))
            if action:
                return "❌ 用法: /em map <x> <z>"

        return ("🌍 地图截图\n"
                "━━━━━━━━━━━━━━━━\n"
                "/em map town <城镇名>     城镇地图\n"
                "/em map player <玩家名>   玩家位置\n"
                "/em map <x> <z>           坐标截图\n"
                "━━━━━━━━━━━━━━━━\n"
                "也可用自然语言: '帮我截一张北京的地图'")

    # ── 配置管理 ──────────────────────

    _conversations_path: str = ""

    @classmethod
    def _configs_dir(cls) -> str:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        d = os.path.join(str(get_astrbot_data_path()), "plugin_data",
                         "astrbot_plugin_earthmc", "configs")
        os.makedirs(d, exist_ok=True)
        return d

    @classmethod
    def _seen_path(cls) -> str:
        if not cls._conversations_path:
            cls._conversations_path = os.path.join(
                cls._configs_dir(), "../seen_conversations.json")
        return cls._conversations_path

    @classmethod
    def _record_conversation(cls, uid: str, ctype: str):
        """自动记录所有对话过的 ID。"""
        import json
        path = cls._seen_path()
        seen = {}
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    seen = json.load(f)
        except Exception:
            pass
        if uid not in seen:
            seen[uid] = ctype
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(seen, f)
            os.replace(tmp, path)

    @classmethod
    def load_feature_config(cls, uid: str) -> dict:
        """读取某 ID 的功能开关配置。"""
        import json
        uid = str(uid)
        path = os.path.join(cls._configs_dir(), f"group_{uid}.json")
        if not os.path.exists(path):
            path = os.path.join(cls._configs_dir(), f"friend_{uid}.json")
        if not os.path.exists(path):
            return {"features": {}}  # 默认全部开启
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"features": {}}

    @staticmethod
    def _feature_enabled(cfg: dict, key: str) -> bool:
        return cfg.get("features", {}).get(key, True)  # 默认开启

    async def _api_configs_list(self):
        from astrbot.api.web import json_response
        import json
        seen = set()
        result = []
        d = self._configs_dir()
        # 1. 已有显式配置文件
        if os.path.exists(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        result.append(cfg)
                        seen.add(cfg["id"])
                    except Exception:
                        pass
        # 2. 自动发现：所有对话过的群/私聊
        spath = self._seen_path()
        if os.path.exists(spath):
            try:
                with open(spath, "r", encoding="utf-8") as f:
                    seen_ids = json.load(f)
                for uid, ctype in seen_ids.items():
                    if uid not in seen:
                        result.append({
                            "id": uid, "type": ctype,
                            "features": {"watch": True, "market": True,
                                         "map": True, "scanner": True, "commands": True}
                        })
                        seen.add(uid)
            except Exception:
                pass
        # 3. 从 watch 配置兜底
        watch = self.watch.load_config()
        for gid in watch:
            if gid not in seen:
                result.append({
                    "id": gid, "type": "group",
                    "features": {"watch": True, "market": True,
                                 "map": True, "scanner": True, "commands": True}
                })
                seen.add(gid)
        return json_response(result)

    async def _api_configs_get(self):
        from astrbot.api.web import json_response, error_response, request
        uid = request.query.get("id", "").strip()
        if not uid:
            return error_response("missing id", status_code=400)
        return json_response(self.load_feature_config(uid))

    async def _api_configs_save(self):
        from astrbot.api.web import json_response, error_response, request
        import json
        payload = await request.json(default={})
        uid = str(payload.get("id", "")).strip()
        ctype = payload.get("type", "group").strip()
        features = payload.get("features", {})
        if not uid:
            return error_response("missing id", status_code=400)
        if not uid.isdigit():
            return error_response("ID 必须为数字（QQ群号或QQ号）", status_code=400)
        prefix = "friend" if ctype == "friend" else "group"
        path = os.path.join(self._configs_dir(), f"{prefix}_{uid}.json")
        data = {"id": uid, "type": ctype, "features": features}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return json_response({"saved": True})

    async def _api_configs_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        uid = str(payload.get("id", "")).strip()
        if not uid:
            return error_response("missing id", status_code=400)
        for prefix in ("group", "friend"):
            path = os.path.join(self._configs_dir(), f"{prefix}_{uid}.json")
            if os.path.exists(path):
                os.remove(path)
        return json_response({"deleted": True})

    # ── Watch 管理 API ──────────────────

    async def _api_watch_groups(self):
        from astrbot.api.web import json_response
        return json_response(list(self.watch.load_config().keys()))

    @staticmethod
    def _vp_payload(gid: str, w: dict | None) -> dict:
        """VP 配置的对外返回体。"""
        if not w:
            return {"group_id": gid, "empty": True,
                    "vp_thresholds": [], "vp_at": [], "vp_at_lines": [],
                    "vp_dnd_start": "", "vp_dnd_end": ""}
        return {
            "group_id": gid,
            "empty": False,
            "vp_thresholds": w.get("vp_thresholds", []),
            "vp_at": w.get("vp_at", []),
            "vp_at_lines": w.get("vp_at_lines", []),
            "vp_dnd_start": w.get("vp_dnd_start", ""),
            "vp_dnd_end": w.get("vp_dnd_end", ""),
        }

    async def _api_vp_status(self):
        from astrbot.api.web import json_response, error_response, request
        gid = request.query.get("group_id", "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        return json_response(self._vp_payload(gid, self.watch.load_config().get(gid)))

    async def _api_watch_status(self):
        from astrbot.api.web import json_response, error_response, request
        gid = request.query.get("group_id", "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w:
            return json_response({"group_id": gid, "empty": True})
        resp = self._vp_payload(gid, w)      # 兼容：保留 vp 字段供旧缓存前端使用
        resp.update({
            "empty": False,
            "players": {k: v.get("online", False)
                        for k, v in (w.get("players") or {}).items()},
            "towns": {k: {
                "resident_count": v.get("resident_count", "?"),
                "blocks": v.get("blocks", "?"),
                "maxBlocks": v.get("maxBlocks", "?"),
            } for k, v in (w.get("towns") or {}).items()},
        })
        return json_response(resp)

    @staticmethod
    def _build_umo(gid: str, ctype: str = "group") -> str:
        """按固定格式拼接 umo：qq-bot:GroupMessage:{群号} / qq-bot:FriendMessage:{QQ号}"""
        kind = "FriendMessage" if ctype == "friend" else "GroupMessage"
        return f"qq-bot:{kind}:{gid}"

    @classmethod
    def _ensure_watch_umo(cls, config: dict, gid: str, ctype: str = "group"):
        """群配置缺 umo 时按格式补全。"""
        w = config.setdefault(gid, {})
        if not w.get("umo"):
            w["umo"] = cls._build_umo(gid, ctype)

    async def _api_vp_save(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        thresholds = payload.get("thresholds", [])
        at = payload.get("at")                    # list | None（不传则不改动）
        at_lines = payload.get("at_lines")        # list | None（不传则不改动）
        dnd_start = (payload.get("dnd_start") or "").strip()
        dnd_end = (payload.get("dnd_end") or "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)

        th = [int(t) for t in thresholds if str(t).isdigit() and int(t) > 0]
        th.sort(reverse=True)

        if dnd_start and dnd_end:
            if parse_cn_time(dnd_start) is None or parse_cn_time(dnd_end) is None:
                return error_response("免打扰时间格式无效（需 HH:MM）", status_code=400)

        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        w = config[gid]
        w["vp_thresholds"] = th
        if not th:
            w["vp_last"] = None                    # 与命令行为一致，防误报

        if at is not None:
            uniq, seen = [], set()
            for a in at:
                if str(a).isdigit() and int(a) not in seen:
                    seen.add(int(a))
                    uniq.append(int(a))
            if uniq:
                w["vp_at"] = uniq
            else:
                w.pop("vp_at", None)

        if at_lines is not None:
            uniq, seen = [], set()
            for a in at_lines:
                v = int(a) if str(a).isdigit() else None
                if v is not None and v in th and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            if uniq:
                w["vp_at_lines"] = uniq
            else:
                w.pop("vp_at_lines", None)

        if dnd_start and dnd_end:
            w["vp_dnd_start"], w["vp_dnd_end"] = dnd_start, dnd_end
        else:
            w.pop("vp_dnd_start", None)
            w.pop("vp_dnd_end", None)

        self.watch.save_config(config)
        self.watch.ensure_running()
        return json_response({
            "saved": True,
            "thresholds": th,
            "at": w.get("vp_at", []),
            "at_lines": w.get("vp_at_lines", []),
            "dnd_start": w.get("vp_dnd_start", ""),
            "dnd_end": w.get("vp_dnd_end", ""),
        })

    async def _api_watch_player_add(self):
        from astrbot.api.web import json_response, error_response, request
        from .api import post as api_post
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        # 校验玩家存在
        data = await api_post("/players", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return error_response("玩家不存在", status_code=400)
        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        players = config[gid].setdefault("players", {})
        if name.lower() not in {k.lower() for k in players}:
            cname = data[0].get("name") or name      # 落服务端规范大小写
            players[cname] = {"online": False,
                              "town": (data[0].get("town") or {}).get("name", "")}
            self.watch.save_config(config)
            self.watch.ensure_running()
            return json_response({"added": True, "name": name})
        return json_response({"added": False, "name": name})

    async def _api_watch_player_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        config = self.watch.load_config()
        players = (config.get(gid) or {}).get("players", {})
        removed = [k for k in players if k.lower() == name.lower()]
        for k in removed:
            del players[k]
        if removed:
            self.watch.save_config(config)
        return json_response({"deleted": len(removed) > 0})

    async def _api_watch_town_add(self):
        from astrbot.api.web import json_response, error_response, request
        from .api import post as api_post
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        # 校验城镇存在并拉取初始状态
        data = await api_post("/towns", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return error_response("城镇不存在", status_code=400)
        t = data[0]
        stats = t.get("stats") or {}
        cur_names = sorted(r.get("name", "") for r in (t.get("residents") or []))
        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        towns = config[gid].setdefault("towns", {})
        if name.lower() not in {k.lower() for k in towns}:
            towns[t.get("name", name)] = {
                "resident_count": stats.get("numResidents", 0),
                "residents": cur_names,
                "blocks": stats.get("numTownBlocks", 0),
                "maxBlocks": stats.get("maxTownBlocks", 0),
                "balance": stats.get("balance", 0),
                "mayor": (t.get("mayor") or {}).get("name", ""),
                "nation": (t.get("nation") or {}).get("name", ""),
                "is_open": (t.get("status") or {}).get("isOpen", False),
                "is_ruined": (t.get("status") or {}).get("isRuined", False),
            }
            self.watch.save_config(config)
            self.watch.ensure_running()
            return json_response({"added": True, "name": t.get("name", name)})
        return json_response({"added": False, "name": name})

    async def _api_watch_town_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        config = self.watch.load_config()
        towns = (config.get(gid) or {}).get("towns", {})
        removed = [k for k in towns if k.lower() == name.lower()]
        for k in removed:
            del towns[k]
        if removed:
            self.watch.save_config(config)
        return json_response({"deleted": len(removed) > 0})

    async def _api_watch_off(self):
        """关闭该群的玩家/城镇监控（不动 VP 提醒设置）。"""
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w:
            return json_response({"closed": False})
        changed = False
        for key in ("players", "towns"):
            if key in w:
                del w[key]
                changed = True
        if changed:
            self.watch.save_config(config)
        return json_response({"closed": changed})

    async def _api_vp_off(self):
        """清除 VP 提醒线（与 /em vp off 一致）：清阈值+@触发线，保留 @名单与免打扰。"""
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w or ("vp_thresholds" not in w and "vp_at_lines" not in w):
            return json_response({"closed": False})
        w.pop("vp_thresholds", None)
        w.pop("vp_at_lines", None)
        w["vp_last"] = None          # 重置基线，避免下次加回阈值时误报
        self.watch.save_config(config)
        return json_response({"closed": True})

    # ── wp 子命令 ───────────────────

    async def _handle_wp(self, event: AstrMessageEvent,
                         action: str, value: str) -> str:
        action = (action or "").lower()
        value = (value or "").strip()
        from .waypoints import WORLDS

        if action in ("help",):
            return WAYPOINT_HELP

        if action in ("list", ""):
            world = value.strip().lower() if value else ""
            if world and world not in WORLDS:
                return "❌ 世界必须是 overworld(主世界) 或 nether(地狱)。"
            data = self.waypoints.list_all(world)
            if not data:
                return "📍 路径点: 暂无记录"
            wl = "主世界" if world == "overworld" else ("地狱" if world == "nether" else "全部")
            lines = [f"📍 路径点 ({wl}, {len(data)} 个)"]
            for w in data:
                lines.append(
                    f"  #{w['id']}  {w['name']}  "
                    f"({WORLDS.get(w['world'], w['world'])})  "
                    f"{w['x']}, {w['y']}, {w['z']}  [{w.get('added_at', '?')}]")
            return "\n".join(lines)

        if action in ("search",):
            if not value:
                return "❌ 用法: /em wp search <关键词> [overworld/nether]"
            parts = value.split()
            kw = parts[0]
            world = parts[1].lower() if len(parts) > 1 else ""
            results = self.waypoints.search(kw, world)
            if not results:
                return f"📍 路径点查询 \"{kw}\"\n暂无相关记录。"
            lines = [f"📍 路径点查询 \"{kw}\" ({len(results)} 个)"]
            for w in results:
                lines.append(
                    f"  #{w['id']}  {w['name']}  "
                    f"({WORLDS.get(w['world'], w['world'])})  "
                    f"{w['x']}, {w['y']}, {w['z']}  [{w.get('added_at', '?')}]")
            return "\n".join(lines)

        if action in ("add",):
            # /em wp add <world> <名称> <x> <y> <z>
            parts = value.split()
            if len(parts) < 5:
                return ("❌ 用法: /em wp add <overworld/nether> <名称> <x> <y> <z>\n"
                        "例如: /em wp add overworld 刷铁机 100 64 -200")
            world = parts[0].lower()
            if world not in WORLDS:
                return "❌ 世界必须是 overworld(主世界) 或 nether(地狱)。"
            try:
                x, y, z = int(parts[2]), int(parts[3]), int(parts[4])
            except ValueError:
                return "❌ 坐标必须是数字。"
            name = parts[1]
            result = self.waypoints.add(name, world, x, y, z)
            msg = (f"✅ 已记录 #{result['id']}  {name}  "
                   f"({WORLDS[world]})  {x}, {y}, {z}")
            if result.get("dup_warn"):
                msg += f"\n{result['dup_warn']}"
            return msg

        if action in ("del", "delete", "remove"):
            if not value or not value.isdigit():
                return "❌ 用法: /em wp del <id>"
            wid = int(value)
            if self.waypoints.delete(wid):
                return f"✅ 已删除 #{wid}。"
            return f"❌ 未找到 #{wid}。"

        return WAYPOINT_HELP

    # ── 生命周期 ──────────────────────

    @filter.on_astrbot_loaded()
    async def _start_background(self):
        self.watch.start()
        await self.scanner.start_scheduler()

    async def terminate(self):
        await self.watch.stop()
        await self.scanner.stop()
        await close_session()
        logger.info("[EarthMC] 插件已卸载")


# ── 工具调用辅助 ──────────────────────

async def _run_tool(tool_cls, arg: str) -> str:
    if tool_cls in (ServerStatusTool, VotePartyTool,
                    OnlinePlayersTool, MysteryMasterTool):
        return await tool_cls().call(None)
    if tool_cls is TownTool:
        return await tool_cls().call(None, name=arg)
    if tool_cls is NationTool:
        return await tool_cls().call(None, name=arg)
    if tool_cls is PlayerTool:
        return await tool_cls().call(None, name=arg)
    if tool_cls is NearbyTownsTool:
        return await tool_cls().call(None, town=arg)
    if tool_cls is McMMOTopTool:
        return await tool_cls().call(None, skill=arg)
    if tool_cls is QuarterTool:
        return await tool_cls().call(None, query=arg)
    return "❌ 未知工具类型"


async def _run_location(x_str: str, z_str: str) -> str:
    try:
        x = int(x_str)
        z = int(z_str)
    except (ValueError, TypeError):
        return "❌ 用法: /em location <x> <z>  例如 /em location 2000 10000"
    return await LocationTool().call(None, x=x, z=z)
