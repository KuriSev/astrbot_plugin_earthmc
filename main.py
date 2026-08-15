"""
AstrBot 插件：EarthMC 服务器信息查询 v1.13.1
/em 命令 · LLM Agent 工具 · 自动监控 · 销城评估 · 全服扫描 · 地图截图
"""
import asyncio
import os

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
from .watch import WatchManager
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
  status vp town nation player online nearby location quarter mm
── 地图 ──
  /em map town <名>    城镇地图截图
  /em map player <名>  玩家位置截图
  /em map <x> <z>      坐标截图
── 路径点 ──
  /em wp              使用 /em wp help 查看子命令
── 分析 ──
  /em risk      使用 /em risk help 查看子命令
── 监控 ──
  /em watch     使用 /em watch help 查看子命令
── 市场 ──
  /em market    使用 /em market 查看子命令
━━━━━━━━━━━━━━━━
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
  /em watch vp <票数> ...     多级 VP 提醒
  /em watch player add <名>   添加玩家监控
  /em watch player del <名>   移除玩家监控
  /em watch player             查看监控玩家列表
  /em watch town add <名>     添加城镇监控
  /em watch town del <名>     移除城镇监控
  /em watch town               查看监控城镇列表
  /em watch off               关闭所有
  /em watch                   查看全部设置"""

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
}


class EarthMCPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # ── 读取配置（毫秒值在 main.py 转为秒） ──
        api_configure(
            cache_ttl=config.get("cache_ttl", 30000),
            http_timeout=config.get("http_timeout", 10000),
        )

        watch_interval_ms = config.get("watch_interval", 20000)
        self.watch_interval = watch_interval_ms // 1000  # 秒，用于帮助消息

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

        # ── WebUI Watch 管理 API ──
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/groups",
            self._api_watch_groups, ["GET"], "列出有 watch 的群")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/status",
            self._api_watch_status, ["GET"], "获取某群 watch 配置")
        context.register_web_api(
            "/astrbot_plugin_earthmc/watch/vp/save",
            self._api_watch_vp_save, ["POST"], "保存 VP 阈值")
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

    @filter.command("em", priority=10)
    async def cmd_em(self, event: AstrMessageEvent):
        """EarthMC 查询：/em status|vp|town|nation|player|online|nearby|location|quarter|mm|watch"""
        uid = str(event.message_obj.group_id or event.message_obj.session_id)
        self._record_conversation(uid, "group" if event.message_obj.group_id else "friend")
        cfg = self.load_feature_config(uid)
        if not self._feature_enabled(cfg, "commands"):
            return
        text = event.message_str.strip()
        for prefix in ("/em ", "em "):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            yield event.plain_result(HELP_TEXT)
            event.stop_event()
            return

        parts = text.split(maxsplit=3)
        sub = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""
        arg3 = parts[3] if len(parts) > 3 else ""

        if sub == "help":
            yield event.plain_result(HELP_TEXT)
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

    # ── watch 子命令 ───────────────────

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

        # 关闭
        if action in ("off", "stop", "关闭"):
            config = self.watch.load_config()
            if group_key in config:
                del config[group_key]
                self.watch.save_config(config)
                return "✅ 已关闭本群所有自动提醒。"
            return "⚠ 本群未开启自动提醒。"

        # VP
        if action in ("vp",):
            return await self._cmd_watch_vp(event, value, group_key)

        # 玩家
        if action in ("player", "players"):
            return await self._cmd_watch_player(event, value, group_key)

        # 城镇
        if action in ("town",):
            return await self._cmd_watch_town(event, value, group_key)

        # 查看全部
        return self._cmd_watch_status(group_key)

    async def _cmd_watch_vp(self, event: AstrMessageEvent,
                             value: str, group_key: str) -> str:
        if not value:
            return ("❌ 用法: /em watch vp <票数1> <票数2> ...\n"
                    "例如: /em watch vp 500 200 100 50")

        parts = value.replace(",", " ").split()
        thresholds = []
        for p in parts:
            try:
                t = int(p)
                if t > 0:
                    thresholds.append(t)
            except ValueError:
                return f"❌ 无效的票数: {p}"
        if not thresholds:
            return "❌ 请至少提供一个大于 0 的票数。"
        thresholds.sort(reverse=True)

        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        config[group_key]["vp_thresholds"] = thresholds
        config[group_key].setdefault("vp_last")
        self.watch.save_config(config)
        self.watch.ensure_running()

        lines = "\n".join(f"  • 降至 {t} 票时提醒" for t in thresholds)
        return (f"✅ VP 多级提醒已开启\n━━━━━━━━━━━━━━━━\n{lines}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🔄 检测间隔: {self.watch_interval} 秒\n"
                f"使用 /em watch off 关闭")

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
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in watched]
            if not new:
                return "⚠ 这些玩家已在监控列表中。"

            # 校验玩家是否存在
            from .api import post as api_post
            data = await api_post("/players", {"query": new})
            existing = set()
            if data and isinstance(data, list):
                existing = {p.get("name", "").lower() for p in data}

            valid, invalid = [], []
            for name in new:
                (valid if name.lower() in existing else invalid).append(name)

            for name in valid:
                watched[name] = {"online": False}
            if valid:
                self.watch.save_config(config)
                self.watch.ensure_running()

            msg_parts = []
            if valid:
                msg_parts.append(f"✅ 已添加: {', '.join(valid)}")
            if invalid:
                msg_parts.append(f"❌ 玩家不存在: {', '.join(invalid)}")
            return "\n".join(msg_parts) if msg_parts else "⚠ 未能添加任何玩家。"

        # 删除
        if sub_action in ("del", "delete", "remove", "删除", "移除"):
            if not names_str:
                return ("❌ 用法: /em watch player del <玩家名>\n"
                        "例如: /em watch player del Fixer")
            names = [n.strip() for n in names_str.replace(",", " ").split()]
            removed = [n for n in names if n in watched]
            for n in removed:
                del watched[n]
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
                f"🔄 检测间隔: {self.watch_interval} 秒\n"
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
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in watched]
            if not new:
                return "⚠ 这些城镇已在监控列表中。"

            from .tools import post as tpost
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
            removed = [n for n in names if n in watched]
            for n in removed:
                del watched[n]
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

    def _cmd_watch_status(self, group_key: str) -> str:
        config = self.watch.load_config()
        w = config.get(group_key)
        if not w:
            return ("📊 本群自动提醒: 未开启\n━━━━━━━━━━━━━━━━\n"
                    "开启 VP: /em watch vp <票数> ...\n"
                    "添加玩家: /em watch player add <名>\n"
                    "查看全部: /em watch")

        parts = []
        th = w.get("vp_thresholds")
        if th:
            parts.append("🎯 VP 提醒线: " +
                         " > ".join(str(t) for t in sorted(th, reverse=True)))
        else:
            parts.append("🎯 VP 提醒: 未设置")

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
                f"🔄 检测间隔: {self.watch_interval} 秒\n"
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

    async def _api_watch_status(self):
        from astrbot.api.web import json_response, error_response, request
        gid = request.query.get("group_id", "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w:
            return json_response({"group_id": gid, "empty": True})
        # 精简返回，去掉内部状态
        return json_response({
            "group_id": gid,
            "empty": False,
            "vp_thresholds": w.get("vp_thresholds", []),
            "players": {k: v.get("online", False)
                        for k, v in (w.get("players") or {}).items()},
            "towns": {k: {
                "resident_count": v.get("resident_count", "?"),
                "blocks": v.get("blocks", "?"),
                "maxBlocks": v.get("maxBlocks", "?"),
            } for k, v in (w.get("towns") or {}).items()},
        })

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

    async def _api_watch_vp_save(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        thresholds = payload.get("thresholds", [])
        if not gid:
            return error_response("missing group_id", status_code=400)
        th = [int(t) for t in thresholds if str(t).isdigit() and int(t) > 0]
        th.sort(reverse=True)
        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        config[gid]["vp_thresholds"] = th
        self.watch.save_config(config)
        self.watch.ensure_running()
        return json_response({"saved": True, "thresholds": th})

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
        if name.lower() not in players:
            players[name] = {"online": False}
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
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        if gid in config:
            del config[gid]
            self.watch.save_config(config)
            return json_response({"closed": True})
        return json_response({"closed": False})

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
