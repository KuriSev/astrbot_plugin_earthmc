"""
EarthMC 插件 — LLM 工具
FunctionTool 集合，供 Agent 自然语言调用
"""
from dataclasses import dataclass, field

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

from .core.api import get, post, ts_str, mc_time, moon, weather, bool_emoji
from .core.utils import fmt_coord, fmt_coord_pair



def _extract_discord(v) -> str:
    """从 town/nation 的 discord 字段提取可显示的 Discord 链接/代码。"""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("invite", "code", "link", "url"):
            val = v.get(k)
            if val:
                return str(val)
    return ""


def _fmt_rank_lines(ranks, max_names: int = 12) -> list[str]:
    """把 ranks（职位名 → [{name, uuid}]）渲染成「职位: 名字、名字」；空职位跳过。"""
    lines = []
    if not isinstance(ranks, dict):
        return lines
    for rank, members in ranks.items():
        names = [m.get("name") for m in (members or [])
                 if isinstance(m, dict) and m.get("name")]
        if not names:
            continue
        shown = "、".join(names[:max_names])
        if len(names) > max_names:
            shown += "…"
        lines.append(f"  {rank}: {shown}")
    return lines


def _names_list(v) -> list[str]:
    """把 API 返回的列表（元素可能是 {name} dict 或 str）统一成名字列表。"""
    out = []
    for x in v or []:
        if isinstance(x, dict):
            nm = x.get("name")
            if nm:
                out.append(str(nm))
        elif isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


@dataclass
class ServerStatusTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_server_status"
    description: str = "查询 EarthMC Minecraft 服务器的实时状态：在线人数、天气、月相、游戏时间、城镇/国家总数。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    async def call(self, context, **kwargs) -> str:
        data = await get("/")
        if not data: return "❌ 无法获取 EarthMC 服务器状态，API 暂不可用。"
        s = data.get("stats", {}); ts = data.get("timestamps", {}); st = data.get("status", {})
        return (
            f"🌍 EarthMC 服务器状态\n━━━━━━━━━━━━━━━━\n"
            f"👥 在线: {s.get('numOnlinePlayers','?')}/{s.get('maxPlayers','?')}  "
            f"游民: {s.get('numOnlineNomads','?')}\n"
            f"{moon(data.get('moonPhase'))}  {weather(st.get('hasStorm',False), st.get('isThundering',False))}  "
            f"🕐 {mc_time(ts.get('serverTimeOfDay'))}\n━━━━━━━━━━━━━━━━\n"
            f"🏘 城镇: {s.get('numTowns','?')}  🏰 国家: {s.get('numNations','?')}  "
            f"🧱 方块: {s.get('numTownBlocks','?')}\n"
            f"👤 居民: {s.get('numResidents','?')}  🚶 游民: {s.get('numNomads','?')}  "
            f"🏠 领地: {s.get('numQuarters','?')}"
        )


@dataclass
class VotePartyTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_vote_party"
    description: str = "查询 EarthMC 投票派对的当前进度（已投票数/所需总数）。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    async def call(self, context, **kwargs) -> str:
        data = await get("/")
        if not data: return "❌ 无法获取 VoteParty 状态。"
        vp = data.get("voteParty", {}); target = vp.get("target", 0) or 1
        current = target - vp.get("numRemaining", 0)
        pct = min(current / target * 100, 100)
        return (f"🗳 VoteParty: {current}/{target}（{pct:.0f}%）"
                f"  还需 {vp.get('numRemaining','?')} 票")


@dataclass
class TownTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_town"
    description: str = "查询 EarthMC 上指定城镇的详细信息：市长、所属国家、居民数、方块数、余额、坐标、职位（rank）及成员、开放状态等。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"name": {"type": "string", "description": "城镇名称"}}, "required": ["name"]})

    async def call(self, context, name: str = "", **kwargs) -> str:
        name = (name or "").strip()
        if not name: return "❌ 请提供城镇名称。"
        data = await post("/towns", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到城镇「{name}」。"
        t = data[0]; mayor = t.get("mayor",{}) or {}; nation = t.get("nation",{}) or {}
        stats = t.get("stats",{}) or {}; status = t.get("status",{}) or {}
        coord = (t.get("coordinates",{}) or {}).get("spawn", {})
        coord_str = fmt_coord_pair(coord.get("x"), coord.get("z")) if coord else "?"
        warps = [w.get("name","?") if isinstance(w, dict) else w
                 for w in (t.get("warps",[]) or [])]
        discord_str = _extract_discord(t.get("discord"))
        rank_lines = _fmt_rank_lines(t.get("ranks"))
        rank_block = ("🏛 职位:\n" + "\n".join(rank_lines) + "\n") if rank_lines else ""
        return (
            f"🏘 {t.get('name','?')}  {coord_str}\n━━━━━━━━━━━━━━━━\n"
            f"👤 市长: {mayor.get('name','?')}\n🏰 国家: {nation.get('name','无')}\n"
            f"📝 公告: {t.get('board','无') or '无'}\n━━━━━━━━━━━━━━━━\n"
            f"👥 居民: {stats.get('numResidents','?')}  🔒 罪犯: {stats.get('numOutlaws','?')}\n"
            f"🧱 方块: {stats.get('numTownBlocks','?')}/{stats.get('maxTownBlocks','?')}  "
            f"💰 {stats.get('balance','?')} G\n"
            f"📍 传送点: {', '.join(warps[:8]) if warps else '无'}\n"
            f"{rank_block}"
            f"{'🔗 Discord: ' + discord_str + '\n' if discord_str else ''}"
            f"━━━━━━━━━━━━━━━━\n"
            f"开放: {bool_emoji(status.get('isOpen'))}  公共: {bool_emoji(status.get('isPublic'))}  "
            f"首都: {bool_emoji(status.get('isCapital'))}\n"
            f"中立: {bool_emoji(status.get('isNeutral'))}  废墟: {bool_emoji(status.get('isRuined'))}  "
            f"出售: {bool_emoji(status.get('isForSale'))}\n"
            f"🕐 注册: {ts_str(t.get('timestamps',{}).get('registered'))}"
        )


@dataclass
class NationTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_nation"
    description: str = "查询 EarthMC 上指定国家的详细信息：国王、首都、城镇列表、居民数、国家职位（rank）及成员、盟友、敌对国、国家加成(nation bonus)、禁运、条约、余额等。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"name": {"type": "string", "description": "国家名称"}}, "required": ["name"]})

    async def call(self, context, name: str = "", **kwargs) -> str:
        name = (name or "").strip()
        if not name: return "❌ 请提供国家名称。"
        data = await post("/nations", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到国家「{name}」。"
        n = data[0]; king = n.get("king",{}) or {}; capital = n.get("capital",{}) or {}
        stats = n.get("stats",{}) or {}; status = n.get("status",{}) or {}
        coord = (n.get("coordinates",{}) or {}).get("spawn", {})
        coord_str = fmt_coord_pair(coord.get("x"), coord.get("z")) if coord else "?"
        towns = [t.get("name","?") for t in (n.get("towns",[]) or [])]
        allies = [a.get("name","?") for a in (n.get("allies",[]) or [])]
        enemies = [e.get("name","?") for e in (n.get("enemies",[]) or [])]
        nb = stats.get('nationBonus')
        bonus_str = f"📦 国家加成: +{nb} 块" if nb is not None else "📦 国家加成: ?"
        emb = n.get("embargoes") or {}
        own_emb = _names_list(emb.get("own"))
        against_emb = _names_list(emb.get("against"))
        emb_parts = []
        if own_emb:
            emb_parts.append("我方:" + "、".join(own_emb[:6]))
        if against_emb:
            emb_parts.append("被:" + "、".join(against_emb[:6]))
        emb_line = "；".join(emb_parts) if emb_parts else "无"
        pact_names = []
        for p in (n.get("pacts") or {}).get("active") or []:
            if isinstance(p, dict):
                pact_names.append(f"{p.get('sender','?')}↔{p.get('receiver','?')}")
        discord_str = _extract_discord(n.get("discord"))
        rank_lines = _fmt_rank_lines(n.get("ranks"))
        rank_block = ("🏛 职位:\n" + "\n".join(rank_lines) + "\n") if rank_lines else ""
        return (
            f"🏰 {n.get('name','?')}  {coord_str}\n━━━━━━━━━━━━━━━━\n"
            f"👑 国王: {king.get('name','?')}\n🏛 首都: {capital.get('name','无')}\n"
            f"📝 公告: {n.get('board','无') or '无'}\n━━━━━━━━━━━━━━━━\n"
            f"🏘 城镇({stats.get('numTowns','?')}): {', '.join(towns[:12])}{'...' if len(towns) > 12 else ''}\n"
            f"👥 居民: {stats.get('numResidents','?')}  💰 {stats.get('balance','?')} G\n"
            f"{rank_block}"
            f"{bonus_str}\n"
            f"🤝 盟友: {', '.join(allies[:6]) if allies else '无'}\n"
            f"⚔ 敌对: {', '.join(enemies[:6]) if enemies else '无'}\n"
            f"🚫 禁运: {emb_line}\n"
            f"📜 条约: {', '.join(pact_names[:6]) if pact_names else '无'}\n"
            f"{'🔗 Discord: ' + discord_str + '\n' if discord_str else ''}"
            f"━━━━━━━━━━━━━━━━\n"
            f"开放: {bool_emoji(status.get('isOpen'))}  公共: {bool_emoji(status.get('isPublic'))}  "
            f"中立: {bool_emoji(status.get('isNeutral'))}\n"
            f"🕐 注册: {ts_str(n.get('timestamps',{}).get('registered'))}"
        )


@dataclass
class PlayerTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_player"
    description: str = "查询 EarthMC 上指定玩家的详细信息：所在城镇/国家、在线状态、最后上线时间、余额、头衔等。支持游戏 ID、UUID 或 Discord ID。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"name": {"type": "string", "description": "玩家名、UUID 或 Discord ID"}}, "required": ["name"]})

    async def call(self, context, name: str = "", **kwargs) -> str:
        name = (name or "").strip()
        if not name: return "❌ 请提供玩家名。"
        data = await post("/players", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到玩家「{name}」。"
        p = data[0]; town = p.get("town",{}) or {}; nation = p.get("nation",{}) or {}
        stats = p.get("stats",{}) or {}; status = p.get("status",{}) or {}; _ts = p.get("timestamps",{}) or {}
        return (
            f"👤 {p.get('name','?')}\n━━━━━━━━━━━━━━━━\n"
            f"🏷 头衔: {p.get('title','无')}\n📝 简介: {p.get('about','无') or '无'}\n━━━━━━━━━━━━━━━━\n"
            f"🏘 城镇: {town.get('name','无')}\n🏰 国家: {nation.get('name','无')}\n━━━━━━━━━━━━━━━━\n"
            f"在线: {bool_emoji(status.get('isOnline'))}  市长: {bool_emoji(status.get('isMayor'))}  "
            f"国王: {bool_emoji(status.get('isKing'))}\n"
            f"💰 {stats.get('balance','?')} G  👫 好友: {stats.get('numFriends','?')}\n"
            f"🕐 最后在线: {ts_str(_ts.get('lastOnline'))}\n📅 注册: {ts_str(_ts.get('registered'))}"
        )


@dataclass
class OnlinePlayersTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_online_players"
    description: str = "查询 EarthMC 当前在线的玩家列表和数量。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    async def call(self, context, **kwargs) -> str:
        data = await get("/online")
        if not data: return "❌ 无法获取在线列表。"
        count = data.get("count", 0); players = data.get("players", [])
        names = [p.get("name","?") for p in players[:30]]
        more = f"...共 {count} 人在线" if count > 30 else ""
        return f"🌍 EarthMC 在线玩家\n━━━━━━━━━━━━━━━━\n👥 共 {count} 人在线\n━━━━━━━━━━━━━━━━\n{', '.join(names)}{more}"


@dataclass
class NearbyTownsTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_nearby_towns"
    description: str = "查询 EarthMC 上指定城镇周围 100 格范围内的其他城镇。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"town": {"type": "string", "description": "目标城镇名称"}}, "required": ["town"]})

    async def call(self, context, town: str = "", **kwargs) -> str:
        town = (town or "").strip()
        if not town: return "❌ 请提供目标城镇名称。"
        # 取服务端规范名用于显示（查询本身大小写不敏感）；取不到则退回用户输入
        disp = town
        tq = await post("/towns", {"query": [town]})
        if isinstance(tq, list) and tq and isinstance(tq[0], dict) and tq[0].get("name"):
            disp = tq[0]["name"]
        data = await post("/nearby", {"query": [{"target_type": "TOWN", "target": town, "search_type": "TOWN", "radius": 100}]})
        if not data or not isinstance(data, list): return f"❌ 未找到「{disp}」附近的城镇。"
        nearby = data[0] if data else []
        if not nearby: return f"🏘 「{disp}」周围 100 格内没有其他城镇。"
        names = [t.get("name","?") for t in nearby[:30]]
        return f"🏘 {disp} 附近城镇 ({len(nearby)} 个)\n━━━━━━━━━━━━━━━━\n{', '.join(names)}{'...' if len(nearby) > 30 else ''}"


@dataclass
class LocationTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_location"
    description: str = "查询 EarthMC 地图上指定坐标 (x, z) 属于哪个城镇和国家。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"x": {"type": "number", "description": "X 坐标"}, "z": {"type": "number", "description": "Z 坐标"}}, "required": ["x", "z"]})

    async def call(self, context, x: float = 0, z: float = 0, **kwargs) -> str:
        data = await post("/location", {"query": [[int(x), int(z)]]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 无法查询坐标 ({int(x)}, {int(z)})。"
        loc = data[0]
        if loc.get("isWilderness"): return f"🗺 坐标 ({int(x)}, {int(z)}) → 🏕 荒野（无归属）"
        town = loc.get("town",{}) or {}; nation = loc.get("nation",{}) or {}
        return f"🗺 坐标 ({int(x)}, {int(z)})\n━━━━━━━━━━━━━━━━\n🏘 城镇: {town.get('name','?')}\n🏰 国家: {nation.get('name','无')}"


@dataclass
class QuarterTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_quarter"
    description: str = "查询 EarthMC 上指定领地（Quarter）的详细信息：类型、所有者、所属城镇、价格、体积等。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"query": {"type": "string", "description": "领地名称或 UUID"}}, "required": ["query"]})

    async def call(self, context, query: str = "", **kwargs) -> str:
        query = (query or "").strip()
        if not query: return "❌ 请提供领地名称。"
        data = await post("/quarters", {"query": [query]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到领地「{query}」。"
        q = data[0]; owner = q.get("owner",{}) or {}; town = q.get("town",{}) or {}; stats = q.get("stats",{}) or {}
        return (
            f"🏠 领地: {q.get('uuid','?')[:8]}...\n━━━━━━━━━━━━━━━━\n"
            f"📦 类型: {q.get('type','?')}\n👤 所有者: {owner.get('name','无')}\n🏘 所属城镇: {town.get('name','?')}\n━━━━━━━━━━━━━━━━\n"
            f"💰 价格: {stats.get('price','?')} G  📐 体积: {stats.get('volume','?')}\n"
            f"🧱 块数: {stats.get('numCuboids','?')}  🏳 大使馆: {bool_emoji(q.get('status',{}).get('isEmbassy'))}"
        )


@dataclass
class MysteryMasterTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_mystery_master"
    description: str = "查询 EarthMC Mystery Master 小游戏排行榜前 50 名。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    async def call(self, context, **kwargs) -> str:
        data = await get("/mm")
        if not data or not isinstance(data, list): return "❌ 无法获取 Mystery Master 排行榜。"
        lines = [f"{i:2d}. {p.get('name','?')} {'↑' if p.get('change')=='UP' else '↓'}" for i, p in enumerate(data[:15], 1)]
        return f"🎮 Mystery Master Top 15\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + f"\n━━━━━━━━━━━━━━━━\n共 {len(data)} 人上榜"


# ── 地图截图工具 ──────────────────────────────────────

async def _send_map_image(context, path: str):
    """通过工具 context 直接发图。"""
    try:
        event = context.context.event
        ctx = context.context.context
        from astrbot.api.event import MessageChain
        await ctx.send_message(
            event.unified_msg_origin,
            MessageChain().file_image(path))
    except Exception:
        pass


@dataclass
class MapTownTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_map_town"
    description: str = (
        "生成 EarthMC 网页地图上指定城镇的截图。自动定位城镇坐标和领地范围，"
        "无需先调用 earthmc_town。用户要求截图/地图/卫星图时直接使用此工具。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "城镇名称"}
        },
        "required": ["name"],
    })

    async def call(self, context, name: str = "", **kwargs) -> str:
        from .features.map import fetch_markers, screenshot_area, screenshot_path

        name = (name or "").strip()
        if not name:
            return "❌ 请提供城镇名称。"

        markers = await fetch_markers()
        marker = markers.get(name.lower())
        if not marker:
            return f"❌ 未在地图上找到城镇「{name}」。请确认名称拼写正确。"

        try:
            buf = await screenshot_area(
                marker["min_x"], marker["min_z"],
                marker["max_x"], marker["max_z"])
            path = screenshot_path()
            with open(path, "wb") as f:
                f.write(buf.read())
            await _send_map_image(context, path)
            info = f"{marker['name']}"
            if marker["nation"]:
                info += f" ({marker['nation']})"
            return f"🗺 {info} 地图截图已生成"
        except Exception:
            cx = (marker["min_x"] + marker["max_x"]) // 2
            cz = (marker["min_z"] + marker["max_z"]) // 2
            return f"🗺 {marker['name']} 地图: https://map.earthmc.net/?world=minecraft:overworld&x={cx}&z={cz}&zoom=3\n⚠ 截图生成失败，请点击链接查看"


@dataclass
class MapPlayerTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_map_player"
    description: str = (
        "生成 EarthMC 网页地图上指定玩家的位置截图。自动定位玩家，"
        "无需先调用 earthmc_player。用户要求看玩家在哪/玩家地图位置时直接使用。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "玩家名"}
        },
        "required": ["name"],
    })

    async def call(self, context, name: str = "", **kwargs) -> str:
        from .features.map import (fetch_players, fetch_markers,
                          screenshot_area, screenshot_center,
                          screenshot_path, ZOOM_DEFAULT)
        from .core.api import post as api_post

        name = (name or "").strip()
        if not name:
            return "❌ 请提供玩家名。"

        online = await fetch_players()
        pdata = online.get(name.lower())
        if pdata:
            try:
                buf = await screenshot_center(
                    pdata["x"], pdata["z"], ZOOM_DEFAULT)
                path = screenshot_path()
                with open(path, "wb") as f:
                    f.write(buf.read())
                await _send_map_image(context, path)
                return (f"🗺 {pdata['name']} 在线，位于 "
                        f"{fmt_coord_pair(pdata['x'], pdata['z'])}")
            except Exception:
                return (f"🗺 {pdata['name']} 在线 "
                        f"{fmt_coord_pair(pdata['x'], pdata['z'])}\n"
                        f"⚠ 截图失败，点击查看: "
                        f"https://map.earthmc.net/?world=minecraft_overworld"
                        f"&x={fmt_coord(pdata['x'])}&z={fmt_coord(pdata['z'])}&zoom=3")

        data = await api_post("/players", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return f"❌ 未找到玩家「{name}」。"
        town = (data[0].get("town") or {}).get("name", "")
        disp = data[0].get("name") or name   # 只用名字，避免带出姓氏/头衔
        if not town:
            return (f"👤 {disp} 为游民，"
                    f"且未在地图上暴露位置。")

        markers = await fetch_markers()
        marker = markers.get(town.lower())
        if not marker:
            return f"👤 {disp} 在城镇「{town}」中，但该城镇未在地图上标记。"

        try:
            buf = await screenshot_area(
                marker["min_x"], marker["min_z"],
                marker["max_x"], marker["max_z"])
            path = screenshot_path()
            with open(path, "wb") as f:
                f.write(buf.read())
            await _send_map_image(context, path)
        except Exception:
            pass  # 截图失败不阻塞，下面返回链接

        cx = (marker["min_x"] + marker["max_x"]) // 2
        cz = (marker["min_z"] + marker["max_z"]) // 2
        info = f"{disp} 离线，展示所属城镇 {marker['name']}"
        if marker["nation"]:
            info += f" ({marker['nation']})"
        return (f"🗺 {info}\n"
                f"https://map.earthmc.net/?world=minecraft:overworld&x={cx}&z={cz}&zoom=3")


@dataclass
class MapLocationTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_map_location"
    description: str = (
        "生成 EarthMC 地图上指定坐标的截图。给定 X、Z 坐标和可选的缩放级别。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X 坐标（Minecraft 坐标）"},
            "z": {"type": "integer", "description": "Z 坐标（Minecraft 坐标）"},
        },
        "required": ["x", "z"],
    })

    async def call(self, context, x: int = 0, z: int = 0, **kwargs) -> str:
        from .features.map import (screenshot_center, screenshot_path, ZOOM_DEFAULT)
        try:
            buf = await screenshot_center(x, z, ZOOM_DEFAULT)
            path = screenshot_path()
            with open(path, "wb") as f:
                f.write(buf.read())
            await _send_map_image(context, path)
            return f"🗺 坐标 ({x}, {z}) 地图截图已生成"
        except Exception:
            return (f"🗺 坐标 ({x}, {z})\n⚠ 截图失败，点击查看: "
                    f"https://map.earthmc.net/?world=minecraft:overworld&x={x}&z={z}&zoom=3")
