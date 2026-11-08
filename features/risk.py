"""销城风险评估：计算函数与对应的 LLM 工具。"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

from ..core.api import post, ts_str
from ..core.constants import INACTIVE_DAYS

# API 单次 query 有数量上限（实测 >100 会被截断），统一按 50 分批
_BATCH = 50


async def _post_chunked(path: str, names: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(names), _BATCH):
        data = await post(path, {"query": names[i:i + _BATCH]})
        if isinstance(data, list):
            out.extend(x for x in data if isinstance(x, dict))
    return out


_TZ_CN = timezone(timedelta(hours=8))
_DAY_MS = 86400000
_INACTIVE_MS = INACTIVE_DAYS * _DAY_MS


def fmt_cn(ms: int | None) -> str:
    """UTC+8、带年份的显示格式。"""
    if not ms:
        return "?"
    return datetime.fromtimestamp(ms / 1000, tz=_TZ_CN).strftime("%Y-%m-%d %H:%M")


# EarthMC 每日结算在 UTC 10:00 = UTC+8 18:00。
# 依据：/towns 的 timestamps.ruinedAt 统计，69 个已废墟城镇中 45 个恰好落在这个点，
# 其余为建国/删国等非自然结算造成的散点。
DAY_BOUNDARY_HOUR_UTC = 10


def next_day_boundary(ts_ms: int) -> int:
    """返回第一个 >= ts_ms 的每日结算时刻（UTC 10:00 = UTC+8 18:00）；正好整点时返回自身。"""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    boundary = dt.replace(hour=DAY_BOUNDARY_HOUR_UTC, minute=0, second=0, microsecond=0)
    if dt > boundary:
        boundary += timedelta(days=1)
    return int(boundary.timestamp() * 1000)


# 兼容旧名（历史调用/测试）
next_utc_midnight = next_day_boundary


@dataclass
class ResidentActivity:
    name: str
    last_online: int | None
    is_mayor: bool = False


@dataclass
class RuinsEstimate:
    town: str
    nation: str
    is_open: bool
    ruined: bool
    total: int
    visible: list[ResidentActivity]
    missing: int
    mayor_name: str
    mayor_is_last: bool
    mayor_expired: bool
    mayor_unknown: bool
    mayor_event_at: int | None
    ruins_at: int | None
    now_ms: int


def analyze_ruins(town: dict, p_map: dict[str, dict], now_ms: int) -> RuinsEstimate:
    """按每日结算点（UTC 10:00 = UTC+8 18:00）计算变废墟时间与城主分支。

    规则：`/players` 查不到的居民一律视为 inactive，不参与 max(lastOnline)。
    """
    status = town.get("status") or {}
    nation = (town.get("nation") or {}).get("name") or "无"
    mayor_name = (town.get("mayor") or {}).get("name") or "?"
    acts: list[ResidentActivity] = []
    for r in town.get("residents") or []:
        rname = r.get("name") or "?"
        p = p_map.get(rname.lower()) or {}
        lo = (p.get("timestamps") or {}).get("lastOnline")
        acts.append(ResidentActivity(
            name=rname,
            last_online=int(lo) if lo else None,
            is_mayor=rname.lower() == mayor_name.lower(),
        ))
    visible = [a for a in acts if a.last_online]

    est = RuinsEstimate(
        town=town.get("name") or "?", nation=nation,
        is_open=bool(status.get("isOpen")), ruined=bool(status.get("isRuined")),
        total=len(acts), visible=visible, missing=len(acts) - len(visible),
        mayor_name=mayor_name, mayor_is_last=False, mayor_expired=False,
        mayor_unknown=False, mayor_event_at=None, ruins_at=None, now_ms=now_ms,
    )
    if est.ruined or not visible:
        return est

    last_online = max(a.last_online for a in visible)
    t42 = last_online + _INACTIVE_MS
    est.ruins_at = next_day_boundary(max(t42, now_ms))

    mayor_act = next((a for a in acts if a.is_mayor), None)
    m_lo = mayor_act.last_online if mayor_act else None
    est.mayor_unknown = m_lo is None
    est.mayor_is_last = bool(m_lo and m_lo == last_online)
    est.mayor_expired = bool(m_lo) and (now_ms - m_lo >= _INACTIVE_MS)
    # 城主数据不可用时按“未知”处理：不预测转让
    if not est.mayor_unknown and not est.mayor_is_last:
        base = now_ms if est.mayor_expired else max(m_lo + _INACTIVE_MS, now_ms)
        est.mayor_event_at = next_day_boundary(base)
    return est


def render_town_risk(e: RuinsEstimate) -> str:
    head = (f"{'🏚' if e.ruined else '⚠'} {e.town}（{e.nation}）"
            f"· {'开放' if e.is_open else '封闭'}")
    if e.ruined:
        return f"{head}\n已是废墟 · 城主 {e.mayor_name}"
    if e.total == 0:
        return f"{head}\n无居民，随时可能变废墟 · 城主 {e.mayor_name}"
    if not e.visible:
        return f"{head}\n全员数据不可用，无法判断 · 城主 {e.mayor_name}（数据不可用）"
    days = max(0, e.ruins_at - e.now_ms) / _DAY_MS
    ruins_txt = f"{fmt_cn(e.ruins_at)} 变废墟"
    if e.mayor_event_at and e.mayor_event_at < e.ruins_at:
        line = f"{fmt_cn(e.mayor_event_at)} 转让城主 → {ruins_txt}"
    else:
        line = ruins_txt
    mayor_tag = "（数据不可用）" if e.mayor_unknown else ""
    line += f" · 剩 {int(days)} 天 · 城主 {e.mayor_name}{mayor_tag}"
    if e.missing:
        line += f" · {e.missing} 人无数据"
    return f"{head}\n{line}"


@dataclass
class TownRiskTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_town_risk"
    description: str = ("评估 EarthMC 城镇的销城风险：预计变废墟时间（UTC+8）、剩余天数、"
                        "城主、城镇是否开放；若城主会先被转让，也会给出转让时间。")
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "城镇名称"}},
        "required": ["name"],
    })

    async def call(self, context, name: str = "", **kwargs) -> str:
        return await _calc_risk(name)


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
    pdata = await _post_chunked("/players", pnames)
    p_map: dict[str, dict] = {}
    if pdata and isinstance(pdata, list):
        for p in pdata:
            p_map[p.get("name", "").lower()] = p

    return t, p_map, ""


async def _calc_risk(name: str) -> str:
    t, p_map, err = await _fetch_town_with_players(name)
    if err:
        return err
    if not t:
        return "❌ 未知错误。"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return render_town_risk(analyze_ruins(t, p_map, now_ms))


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

        parts = [p.get("name", rname)]      # 头衔在下方单独显示，避免 formattedName 重复

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
    tdata = await _post_chunked("/towns", tnames)
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
    nation_name = (nation_name or "").strip()
    if not nation_name:
        return "❌ 请提供国家名称。"

    data = await post("/nations", {"query": [nation_name]})
    if not data or not isinstance(data, list) or len(data) == 0:
        return f"❌ 未找到国家「{nation_name}」。"
    n = data[0]
    towns = n.get("towns", []) or []
    capital = (n.get("capital") or {}).get("name", "无")

    if not towns:
        return f"🏰 {n['name']} 首都 {capital}\n城镇 0 个"

    tnames = [t.get("name") for t in towns if t.get("name")]
    tdata = await _post_chunked("/towns", tnames)
    t_map = {t.get("name", "").lower(): t for t in (tdata or []) if isinstance(t, dict)}
    residents = sorted(
        {r.get("name") for td in t_map.values()
         for r in (td.get("residents") or []) if r.get("name")},
        key=str.lower)
    pdata = await _post_chunked("/players", residents) if residents else []
    p_map = {p.get("name", "").lower(): p for p in (pdata or []) if isinstance(p, dict)}

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    rows = []
    for tname in tnames:
        td = t_map.get(tname.lower())
        if not td:
            continue
        e = analyze_ruins(td, p_map, now)
        if e.ruined:
            status, key = "已废墟", -1
        elif not e.visible:
            status, key = "无数据", 10 ** 15
        else:
            if e.mayor_event_at and (not e.ruins_at or e.mayor_event_at <= e.ruins_at):
                ev, label = e.mayor_event_at, "转让"
            else:
                ev, label = e.ruins_at, "废墟"
            days = max(0, (ev - now) // _DAY_MS)
            status = f"{fmt_cn(ev)[:10]} {label}·剩{days}天"
            key = ev
        rows.append((key, f"  {td.get('name', tname)}  {status}"
                          f"  {len(td.get('residents') or [])}人"))

    rows.sort(key=lambda x: x[0])
    lines = [f"🏰 {n['name']} 首都 {capital}  城镇 {len(rows)} 个（按临近程度）"]
    lines += [r[1] for r in rows[:20]]
    if len(rows) > 20:
        lines.append(f"  …另有 {len(rows) - 20} 个")
    return "\n".join(lines)
