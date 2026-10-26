"""
EarthMC 插件 — LLM 工具
FunctionTool 集合，供 Agent 自然语言调用
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

from .api import get, post, ts_str, mc_time, moon, weather, bool_emoji

INACTIVE_DAYS = 42  # 42 天不上线即 inactive → 被销城


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
    description: str = "查询 EarthMC 上指定城镇的详细信息：市长、所属国家、居民数、方块数、余额、坐标、开放状态等。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"name": {"type": "string", "description": "城镇名称"}}, "required": ["name"]})

    async def call(self, context, name: str = "", **kwargs) -> str:
        name = (name or "").strip()
        if not name: return "❌ 请提供城镇名称。"
        data = await post("/towns", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到城镇「{name}」。"
        t = data[0]; mayor = t.get("mayor",{}) or {}; nation = t.get("nation",{}) or {}
        stats = t.get("stats",{}) or {}; status = t.get("status",{}) or {}
        coord = (t.get("coordinates",{}) or {}).get("spawn", {})
        coord_str = f"({coord.get('x','?')}, {coord.get('z','?')})" if coord else "?"
        warps = [w.get("name","?") if isinstance(w, dict) else w
                 for w in (t.get("warps",[]) or [])]
        discord_str = _extract_discord(t.get("discord"))
        return (
            f"🏘 {t.get('name','?')}  {coord_str}\n━━━━━━━━━━━━━━━━\n"
            f"👤 市长: {mayor.get('name','?')}\n🏰 国家: {nation.get('name','无')}\n"
            f"📝 公告: {t.get('board','无') or '无'}\n━━━━━━━━━━━━━━━━\n"
            f"👥 居民: {stats.get('numResidents','?')}  🔒 罪犯: {stats.get('numOutlaws','?')}\n"
            f"🧱 方块: {stats.get('numTownBlocks','?')}/{stats.get('maxTownBlocks','?')}  "
            f"💰 {stats.get('balance','?')} G\n"
            f"📍 传送点: {', '.join(warps[:8]) if warps else '无'}\n"
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
    description: str = "查询 EarthMC 上指定国家的详细信息：国王、首都、城镇列表、居民数、盟友、敌对国、国家加成(nation bonus)、禁运、条约、余额等。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {"name": {"type": "string", "description": "国家名称"}}, "required": ["name"]})

    async def call(self, context, name: str = "", **kwargs) -> str:
        name = (name or "").strip()
        if not name: return "❌ 请提供国家名称。"
        data = await post("/nations", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0: return f"❌ 未找到国家「{name}」。"
        n = data[0]; king = n.get("king",{}) or {}; capital = n.get("capital",{}) or {}
        stats = n.get("stats",{}) or {}; status = n.get("status",{}) or {}
        coord = (n.get("coordinates",{}) or {}).get("spawn", {})
        coord_str = f"({coord.get('x','?')}, {coord.get('z','?')})" if coord else "?"
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
        return (
            f"🏰 {n.get('name','?')}  {coord_str}\n━━━━━━━━━━━━━━━━\n"
            f"👑 国王: {king.get('name','?')}\n🏛 首都: {capital.get('name','无')}\n"
            f"📝 公告: {n.get('board','无') or '无'}\n━━━━━━━━━━━━━━━━\n"
            f"🏘 城镇({stats.get('numTowns','?')}): {', '.join(towns[:12])}{'...' if len(towns) > 12 else ''}\n"
            f"👥 居民: {stats.get('numResidents','?')}  💰 {stats.get('balance','?')} G\n"
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
            f"👤 {p.get('formattedName') or p.get('name','?')}\n━━━━━━━━━━━━━━━━\n"
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


@dataclass
class TownRiskTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_town_risk"
    description: str = "评估 EarthMC 城镇的销城风险：居民活跃度、预计被删除时间、最后防线玩家。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "城镇名称"}},
        "required": ["name"],
    })

    async def call(self, context, name: str = "", **kwargs) -> str:
        return await _calc_risk(name)


# ── 公共：查城镇 + 批量取所有成员玩家数据 ──

async def _fetch_town_with_players(name: str) -> tuple[dict | None, dict[str, dict], str]:
    """
    输入城镇名，返回 (town_dict, player_map_lowercase, error_msg)。
    一次 POST /towns + 一次 POST /players 批量取全。
    """
    name = (name or "").strip()
    if not name:
        return None, {}, "❌ 请提供城镇名称。"

    data = await post("/towns", {"query": [name]})
    if not data or not isinstance(data, list) or len(data) == 0:
        return None, {}, f"❌ 未找到城镇「{name}」。"

    t = data[0]
    residents = t.get("residents", []) or []
    if not residents:
        return t, {}, ""

    pnames = [r.get("name", "") for r in residents if r.get("name")]
    pdata = await post("/players", {"query": pnames})
    p_map: dict[str, dict] = {}
    if pdata and isinstance(pdata, list):
        for p in pdata:
            p_map[p.get("name", "").lower()] = p

    return t, p_map, ""


# ── 销城风险 ────────────────────────

async def _calc_risk(name: str) -> str:
    t, p_map, err = await _fetch_town_with_players(name)
    if err:
        return err
    if not t:
        return "❌ 未知错误。"

    residents = t.get("residents", []) or []
    town_name = t.get("name", name)
    nation = (t.get("nation") or {}).get("name", "无")

    if not residents:
        return f"⚠ {town_name} ({nation}) 销城风险\n活跃 0 人\n🔴 已无人活跃，随时可能被删除"

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    rlist = []
    for r in residents:
        rname = r.get("name", "?")
        p = p_map.get(rname.lower(), {})
        lo = (p.get("timestamps") or {}).get("lastOnline")
        if not lo:
            continue
        days_offline = (now_ms - lo) / 86400000
        days_left = INACTIVE_DAYS - days_offline
        if days_left <= 0:
            continue
        ua = p.get("formattedName") or rname
        rlist.append({"name": ua, "days_offline": days_offline,
                       "days_left": days_left})

    if not rlist:
        return (f"⚠ {town_name} ({nation}) 销城风险\n"
                f"活跃 0 人（{len(residents)}人在册但均已离线超42天）\n"
                f"🔴 随时可能被删除")

    rlist.sort(key=lambda x: x["days_left"])
    last_defense = rlist[-1]
    days_until_deletion = last_defense["days_left"]
    del_date = datetime.now(timezone.utc) + timedelta(days=days_until_deletion)

    if days_until_deletion < 3: risk = "🔴 高危"
    elif days_until_deletion < 7: risk = "🟠 警告"
    elif days_until_deletion < 14: risk = "🟡 关注"
    else: risk = "🟢 安全"

    lines = [
        f"⚠ {town_name} ({nation}) 销城风险",
        f"活跃 {len(rlist)} 人  预计销城 {del_date.strftime('%m-%d')}(约{int(days_until_deletion)}天后)",
        f"最后防线 {last_defense['name']}({int(last_defense['days_offline'])}天前上线)",
    ]
    for r in rlist:
        dl = r["days_left"]
        if dl < 1: day_str = "不足1天"
        elif dl < 2: day_str = f"约{int(dl)}天"
        else: day_str = f"{int(dl)}天"
        mark = " ★" if r is last_defense else ""
        lines.append(f"  {r['name']} {day_str} ({int(r['days_offline'])}天前){mark}")
    lines.append(risk)
    return "\n".join(lines)


# ── 城镇成员遍历 ────────────────────

@dataclass
class TownMembersTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_town_members"
    description: str = (
        "查询 EarthMC 城镇的活跃成员完整信息。一次返回所有人，LLM 直接分析，无需逐个调 PlayerTool。"
        "包含字段: 姓名、在线状态、最后上线、注册时间、加入城镇时间、余额(G)、好友数、头衔(title)、"
        "个人简介(about)、是否市长/国王、城镇头衔(townRanks)、国家头衔(nationRanks)。"
        "按最后上线降序排列，长列表截断至 30 人。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"town_name": {"type": "string", "description": "城镇名称"}},
        "required": ["town_name"],
    })

    async def call(self, context, town_name: str = "", **kwargs) -> str:
        return await _list_members(town_name)


async def _list_members(town_name: str) -> str:
    t, p_map, err = await _fetch_town_with_players(town_name)
    if err:
        return err
    if not t:
        return "❌ 未知错误。"

    residents = t.get("residents", []) or []
    nation = (t.get("nation") or {}).get("name", "无")

    if not residents:
        return f"🏘 {t['name']} ({nation})\n活跃成员 0 人"

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    members = []

    for r in residents:
        rname = r.get("name", "?")
        p = p_map.get(rname.lower(), {})
        if not p:
            continue
        ts = p.get("timestamps") or {}
        st = p.get("stats") or {}
        status = p.get("status") or {}
        ranks = p.get("ranks") or {}

        lo = ts.get("lastOnline")
        reg = ts.get("registered")
        joined = ts.get("joinedTownAt")

        parts = [p.get("formattedName") or p.get("name", rname)]

        tags = []
        if status.get("isOnline"): tags.append("在线")
        if status.get("isMayor"): tags.append("市长")
        if status.get("isKing"): tags.append("国王")
        parts.append(",".join(tags) if tags else "离线")

        if lo:
            days = (now_ms - lo) / 86400000
            parts.append(f"{int(days)}天前上线" if days >= 1 else "今天上线")
        else:
            parts.append("上线:?")

        parts.append(f"{st.get('balance', 0)}G")

        nf = st.get("numFriends", 0)
        if nf:
            parts.append(f"{nf}好友")

        title = p.get("title")
        if title:
            parts.append(f"「{title}」")

        about = p.get("about")
        if about:
            about = about[:30] + ("..." if len(about) > 30 else "")
            parts.append(f"简介:{about}")

        tr = ranks.get("townRanks") or []
        nr = ranks.get("nationRanks") or []
        if tr: parts.append(f"镇衔:{','.join(tr[:3])}")
        if nr: parts.append(f"国衔:{','.join(nr[:3])}")

        parts.append(f"注册:{ts_str(reg)}" if reg else "注册:?")
        parts.append(f"加入:{ts_str(joined)}" if joined else "加入:?")

        members.append(("  ".join(parts), lo or 0))

    members.sort(key=lambda x: x[1], reverse=True)
    total = len(members)
    members = members[:30]

    lines = [f"🏘 {t['name']} ({nation}) 成员 ({total} 人)"]
    if total > 30:
        lines.append(f"（仅显示前 30 人）")
    lines.extend(m[0] for m in members)
    return "\n".join(lines)


# ── 国家城镇遍历 ────────────────────

@dataclass
class NationTownsTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_nation_towns"
    description: str = (
        "查询 EarthMC 国家下所有城镇的详细信息。一次返回全部城镇，LLM 直接分析，无需逐个调 TownTool。"
        "每城镇一行含: 城镇名、市长、居民数、余额(G)、方块数、是否首都/开放、注册时间。"
        "按居民数降序排列，长列表截断至 30 个。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"nation_name": {"type": "string", "description": "国家名称"}},
        "required": ["nation_name"],
    })

    async def call(self, context, nation_name: str = "", **kwargs) -> str:
        return await _list_nation_towns(nation_name)


async def _list_nation_towns(nation_name: str) -> str:
    nation_name = (nation_name or "").strip()
    if not nation_name:
        return "❌ 请提供国家名称。"

    data = await post("/nations", {"query": [nation_name]})
    if not data or not isinstance(data, list) or len(data) == 0:
        return f"❌ 未找到国家「{nation_name}」。"
    n = data[0]
    towns = n.get("towns", []) or []
    king = (n.get("king") or {}).get("name", "?")
    capital = (n.get("capital") or {}).get("name", "无")

    if not towns:
        return f"🏰 {n['name']} 国王 {king} 首都 {capital}\n城镇 0 个"

    # 批量取所有城镇详情
    tnames = [t.get("name", "") for t in towns if t.get("name")]
    tdata = await post("/towns", {"query": tnames})
    t_map: dict[str, dict] = {}
    if tdata and isinstance(tdata, list):
        for t in tdata:
            t_map[t.get("name", "").lower()] = t

    town_list = []
    for t in towns:
        tname = t.get("name", "?")
        td = t_map.get(tname.lower(), {})
        if not td:
            continue
        stats = td.get("stats") or {}
        status = td.get("status") or {}
        mayor = (td.get("mayor") or {}).get("name", "?")
        residents = stats.get("numResidents", 0)
        balance = stats.get("balance", 0)
        blocks = f"{stats.get('numTownBlocks',0)}/{stats.get('maxTownBlocks',0)}"

        flags = []
        if status.get("isCapital"): flags.append("首都")
        if status.get("isOpen"): flags.append("开放")
        if status.get("isRuined"): flags.append("废墟")
        flag_str = ",".join(flags) if flags else ""

        town_list.append((
            f"  {td.get('name', tname)}  市长{mayor}  "
            f"{residents}人  {balance}G  {blocks}块  "
            f"{flag_str}  "
            f"注册{ts_str(td.get('timestamps', {}).get('registered'))}",
            residents
        ))

    town_list.sort(key=lambda x: x[1], reverse=True)
    total = len(town_list)
    town_list = town_list[:30]

    lines = [f"🏰 {n['name']} 国王 {king} 首都 {capital} 城镇 ({total} 个)"]
    if total > 30:
        lines.append(f"（仅显示前 30 个）")
    lines.extend(m[0] for m in town_list)
    return "\n".join(lines)


# ── 国家销城风险 ────────────────────

@dataclass
class NationRiskTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_nation_risk"
    description: str = (
        "查询 EarthMC 国家内所有城镇的销城风险排名。基于最近全服扫描缓存，无需额外 API。"
        "按剩余天数升序（最危险在前），返回城镇名、剩余天数、活跃人数、最后防线。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"nation_name": {"type": "string", "description": "国家名称"}},
        "required": ["nation_name"],
    })

    async def call(self, context, nation_name: str = "", **kwargs) -> str:
        return await _nation_risk(nation_name)


async def _nation_risk(nation_name: str) -> str:
    import json, os

    nation_name = (nation_name or "").strip()
    if not nation_name:
        return "❌ 请提供国家名称。"

    data = await post("/nations", {"query": [nation_name]})
    if not data or not isinstance(data, list) or len(data) == 0:
        return f"❌ 未找到国家「{nation_name}」。"
    n = data[0]
    towns = n.get("towns", []) or []
    king = (n.get("king") or {}).get("name", "?")
    capital = (n.get("capital") or {}).get("name", "无")

    if not towns:
        return f"🏰 {n['name']} 国王 {king} 首都 {capital}\n城镇 0 个"

    town_names_lower = {t.get("name", "").lower() for t in towns}

    cache_updated = "从未扫描"
    risk_map: dict[str, dict] = {}
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        cache_path = os.path.join(
            str(get_astrbot_data_path()), "plugin_data",
            "astrbot_plugin_earthmc", "earthmc_risk_scan.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cache_updated = cache.get("updated_at", "?")
            for t in cache.get("towns", []):
                if t["name"].lower() in town_names_lower:
                    risk_map[t["name"].lower()] = t
    except Exception as e:
        from astrbot.api import logger
        logger.error(f"[EarthMC] 加载扫描缓存失败: {e}")

    if not risk_map:
        return (f"🏰 {n['name']} 销城风险: 无缓存数据\n"
                f"请先执行 /em risk scan 生成扫描数据")

    ranked = sorted(risk_map.values(), key=lambda x: x["days_left"])
    lines = [
        f"🏰 {n['name']} 国王 {king} 首都 {capital}  销城风险排名"
        f"  缓存 {cache_updated}"
    ]
    for t in ranked[:20]:
        d = t["days_left"]
        if d < 1: day_str = "不足1天"
        elif d < 2: day_str = f"约{int(d)}天"
        else: day_str = f"{int(d)}天"
        lines.append(
            f"  {t['name']}  剩{day_str}  活跃{t['active_count']}人  ★{t['defense']}")

    return "\n".join(lines)


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
        from .map import fetch_markers, screenshot_area, screenshot_path

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
        from .map import (fetch_players, fetch_markers,
                          screenshot_area, screenshot_center,
                          screenshot_path, ZOOM_DEFAULT)
        from .api import post as api_post

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
                return f"🗺 {pdata['name']} 在线，位于 ({pdata['x']}, {pdata['z']})"
            except Exception:
                return (f"🗺 {pdata['name']} 在线 ({pdata['x']}, {pdata['z']})\n"
                        f"⚠ 截图失败，点击查看: "
                        f"https://map.earthmc.net/?world=minecraft_overworld"
                        f"&x={pdata['x']}&z={pdata['z']}&zoom=3")

        data = await api_post("/players", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return f"❌ 未找到玩家「{name}」。"
        town = (data[0].get("town") or {}).get("name", "")
        disp = data[0].get("formattedName") or data[0].get("name") or name   # 服务端规范名
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
        from .map import (screenshot_center, screenshot_path, ZOOM_DEFAULT)
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
