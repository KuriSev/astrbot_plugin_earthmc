"""
AstrBot 插件：EarthMC 服务器信息查询 v1.11.0
/em 命令 · LLM Agent 工具 · 自动监控 · 销城评估 · 全服扫描 · 地图截图
"""
import asyncio

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
    MarketManager, MarketAddTool, MarketSearchTool, set_market_manager,
)

HELP_TEXT = """🌍 EarthMC 查询
── 查询 ──
  status vp town nation player online nearby location quarter mm
── 地图 ──
  /em map town <名>    城镇地图截图
  /em map player <名>  玩家位置截图
  /em map <x> <z>      坐标截图
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
  /em market list              查看全部
  /em market search <关键词>   搜索物品
  /em market add <t/n> <点> <价> <量> <物品>
      如 /em market add t mending 8 1 经验修补
  /em market del <id>          删除条目
━━━━━━━━━━━━━━━━
也可直接告诉机器人: /t spawn mending有8g一本经验修补"""

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
            yield event.plain_result(
                await self._handle_map(event, arg, arg2))
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

        if action in ("list",):
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

        if action in ("search",):
            if not value:
                return "❌ 用法: /em market search <关键词>"
            results = self.market.search(value)
            if not results:
                return f"📦 市场查询 \"{value}\"\n暂无相关记录。"
            lines = [f"📦 市场查询 \"{value}\""]
            for r in results:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        if action in ("add",):
            # /em market add <t/n> <点> <价> <量> <物品>
            parts = value.split()
            if len(parts) < 5:
                return ("❌ 用法: /em market add <t/n> <传送点名> <价格> <数量> <物品名>\n"
                        "例如: /em market add t mending 8 1 经验修补")
            tp = parts[0].lower()
            if tp not in ("t", "n"):
                return "❌ 类型必须是 t（城镇传送点）或 n（国家传送点）"
            price_raw = parts[2].rstrip("gG")
            entry = {
                "type": tp,
                "location": parts[1],
                "price": f"{price_raw}g",
                "amount": int(parts[3]) if parts[3].isdigit() else 1,
                "item": " ".join(parts[4:]),
                "action": "出售",
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

        if action in ("del", "delete", "remove"):
            if not value or not value.isdigit():
                return "❌ 用法: /em market del <id>"
            eid = int(value)
            if self.market.delete(eid):
                return f"✅ 已删除 #{eid}。"
            return f"❌ 未找到 #{eid}。"

        return MARKET_HELP

    # ── map 子命令 ───────────────────

    async def _handle_map(self, event: AstrMessageEvent,
                          action: str, value: str) -> str:
        action = (action or "").lower()
        value = (value or "").strip()

        if action in ("town",):
            if not value:
                return "❌ 用法: /em map town <城镇名>"
            return await MapTownTool().call(None, name=value)

        if action in ("player",):
            if not value:
                return "❌ 用法: /em map player <玩家名>"
            return await MapPlayerTool().call(None, name=value)

        if action in ("", "location", "coord"):
            parts = value.split()
            if len(parts) >= 2 and parts[0].lstrip("-").isdigit():
                return await MapLocationTool().call(
                    None, x=int(parts[0]), z=int(parts[1]))
            if action:
                return "❌ 用法: /em map <x> <z>"

        return ("🌍 地图截图\n"
                "━━━━━━━━━━━━━━━━\n"
                "/em map town <城镇名>     城镇地图\n"
                "/em map player <玩家名>   玩家位置\n"
                "/em map <x> <z>           坐标截图\n"
                "━━━━━━━━━━━━━━━━\n"
                "也可用自然语言: '帮我截一张北京的地图'")

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
