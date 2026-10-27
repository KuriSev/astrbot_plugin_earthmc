"""
EarthMC 插件 — mcMMO 排行榜查询
McMMOTopTool（前 25 名榜单）· 共享缓存
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

from ..core.api import get_api_key, post

_mcmmo_cache: dict[str, tuple[float, list]] = {}  # 技能 → (时间戳, 条目)，避免频繁命中限流

# EarthMC 服务器可用的 mcMMO 技能（英文 + 中文别名）
MCMMO_SKILLS_EN = [
    "excavation", "fishing", "herbalism", "mining", "woodcutting",
    "archery", "axes", "crossbows", "maces", "swords", "spears",
    "taming", "tridents", "unarmed", "alchemy", "repair", "salvage",
    "smelting", "power",
]
MCMMO_SKILL_ALIASES = {
    "excavation": "EXCAVATION", "挖掘": "EXCAVATION", "挖掘术": "EXCAVATION",
    "fishing": "FISHING", "钓鱼": "FISHING", "垂钓": "FISHING",
    "herbalism": "HERBALISM", "草药学": "HERBALISM", "草药": "HERBALISM", "采药": "HERBALISM",
    "mining": "MINING", "挖矿": "MINING", "采矿": "MINING", "挖矿术": "MINING",
    "woodcutting": "WOODCUTTING", "伐木": "WOODCUTTING", "木工": "WOODCUTTING",
    "archery": "ARCHERY", "箭术": "ARCHERY", "弓箭": "ARCHERY", "射箭": "ARCHERY",
    "axes": "AXES", "斧": "AXES", "斧头": "AXES", "斧术": "AXES",
    "crossbows": "CROSSBOWS", "弩": "CROSSBOWS", "弩术": "CROSSBOWS",
    "maces": "MACES", "锤": "MACES", "锤术": "MACES", "战锤": "MACES",
    "swords": "SWORDS", "剑": "SWORDS", "剑术": "SWORDS",
    "spears": "SPEARS", "矛": "SPEARS", "矛术": "SPEARS",
    "taming": "TAMING", "驯服": "TAMING", "驯兽": "TAMING", "驯养": "TAMING",
    "tridents": "TRIDENTS", "三叉戟": "TRIDENTS",
    "unarmed": "UNARMED", "徒手": "UNARMED", "空手": "UNARMED", "拳击": "UNARMED", "格斗": "UNARMED",
    "alchemy": "ALCHEMY", "炼金": "ALCHEMY", "炼金术": "ALCHEMY", "炼药": "ALCHEMY", "药水": "ALCHEMY", "药剂": "ALCHEMY",
    "repair": "REPAIR", "修理": "REPAIR", "修复": "REPAIR",
    "salvage": "SALVAGE", "回收": "SALVAGE", "拆解": "SALVAGE", "拆解术": "SALVAGE",
    "smelting": "SMELTING", "冶炼": "SMELTING", "熔炼": "SMELTING", "熔炼术": "SMELTING",
    "power": "POWER", "总等级": "POWER", "总": "POWER", "total": "POWER",
}

# API 官方接受的技能名白名单（query 只能是其中之一，或 POWER 总等级）
MCMMO_API_SKILLS = frozenset({
    "EXCAVATION", "FISHING", "HERBALISM", "MINING", "WOODCUTTING",
    "ARCHERY", "AXES", "CROSSBOWS", "MACES", "SWORDS", "SPEARS",
    "TAMING", "TRIDENTS", "UNARMED", "ALCHEMY", "REPAIR", "SALVAGE",
    "SMELTING", "POWER",
})


def normalize_mcmmo_skill(skill: str) -> str | None:
    """把英文/中文技能名归一化为 API 用的大写技能名（如 fishing/钓鱼→FISHING）。"""
    key = (skill or "").strip().lower()
    return MCMMO_SKILL_ALIASES.get(key)


async def _get_mcmmo_entries(skill: str) -> tuple[list, str]:
    """获取某技能排行榜的完整条目（按排名排序）；返回 (entries, 错误信息)。带 3 分钟缓存。"""
    canonical = normalize_mcmmo_skill(skill)
    if canonical not in MCMMO_API_SKILLS:
        return [], (f"❌ 未知 mcMMO 技能「{skill or '?'}」。\n"
                    "可用技能: " + "/".join(MCMMO_SKILLS_EN) +
                    "\n支持中文名，如 钓鱼/挖矿/剑/炼金/总等级。")
    key = get_api_key()
    if not key:
        return [], ("❌ 无法获取排行榜：EarthMC API 密钥未配置。\n"
                    "游戏内 /api key create 获取后，填入插件配置的 api_key 并重载。")
    now = datetime.now(timezone.utc).timestamp()
    cached = _mcmmo_cache.get(canonical)
    if cached and now - cached[0] < 180:
        return cached[1], ""
    # 文档：POST /mcmmo-top，body {"query": [技能大写], "key": "API_KEY"}
    data = await post("/mcmmo-top", {"query": [canonical], "key": key})
    if data is None:
        return [], ("⚠ 无法获取排行榜：接口限流或请求失败。\n"
                    "mcMMO-top 每个 key 每 2 分钟限 1 次，请稍等 2 分钟再试。")
    if isinstance(data, dict) and data.get("error"):
        return [], f"❌ {data.get('error')}"
    # 真实形状：[{"skill":"...", "1":{player,level}, "2":{...}, ...}]
    entries: list = []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        ranked = []
        for k, v in data[0].items():
            if k == "skill" or not isinstance(v, dict):
                continue
            try:
                rank = int(k)
            except (ValueError, TypeError):
                continue
            if v.get("player"):
                ranked.append((rank, v))
        ranked.sort(key=lambda x: x[0])
        entries = [v for _, v in ranked]
    elif isinstance(data, dict):
        entries = (data.get("players") or data.get("leaderboard")
                   or data.get("data") or [])
    else:
        entries = data or []
    _mcmmo_cache[canonical] = (now, entries)
    return entries, ""


@dataclass
class McMMOTopTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_mcmmo_top"
    description: str = ("查询 EarthMC 某 mcMMO 技能排行榜的前 25 名完整列表（含名次）。"
                        "本工具返回的是**已排版好的榜单文本，每行一个名次**；回复时请**整段原样输出**，"
                        "保留换行，**不要合并成一行、不要在名字之间加顿号或逗号、不要改写或精简**。"
                        "仅当用户问'第 N 名是谁'之类具体问题时，才从列表中读出对应条目作答。"
                        "把用户原话的技能名（中文或英文均可）原样传入 skill，如用户说'炼药'就传'炼药'、"
                        "说'驯兽'就传'驯兽'，保持用户措辞，不要翻译。可用技能: excavation挖掘、fishing钓鱼、"
                        "herbalism草药学、mining挖矿、woodcutting伐木、archery箭术、axes斧、crossbows弩、"
                        "maces锤、swords剑、spears矛、taming驯服、tridents三叉戟、unarmed徒手、alchemy炼金、"
                        "repair修理、salvage回收、smelting冶炼，总等级用 power。"
                        "不用于查询某玩家在榜单中的名次（不支持）。接口每 2 分钟限 1 次，结果已缓存，直接返回。")
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "mcMMO 技能名（英文或中文），如 fishing/钓鱼、mining/挖矿、power/总等级"},
        },
        "required": ["skill"],
    })

    async def call(self, context, skill: str = "", **kwargs) -> str:
        skill = (skill or "").strip().lower()
        if not skill:
            return "❌ 请提供 mcMMO 技能名（如 fishing/钓鱼、mining/挖矿、power/总等级）。"
        entries, err = await _get_mcmmo_entries(skill)
        if err:
            return err
        if not entries:
            return f"❌ 技能「{skill}」暂无数据。"
        lines = []
        for i, p in enumerate(entries, 1):
            name = p.get("player") or p.get("name") or "?"
            level = p.get("level", "?")
            lines.append(f"{i:2d}. {name}  Lv{level}")
        return (f"📊 mcMMO {skill} 排行榜（前 {len(entries)} 名）\n"
                f"━━━━━━━━━━━━━━━━\n" + "\n".join(lines))
