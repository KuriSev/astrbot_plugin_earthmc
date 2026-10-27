"""查询类命令：工具注册表与调用辅助。"""
from ..tools import (
    ServerStatusTool, VotePartyTool, TownTool, NationTool,
    PlayerTool, OnlinePlayersTool, NearbyTownsTool,
    LocationTool, QuarterTool, MysteryMasterTool,
    TownRiskTool, TownMembersTool, NationTownsTool, NationRiskTool,
    MapTownTool, MapPlayerTool, MapLocationTool,
)
from ..features.mcmmo import McMMOTopTool
from ..features.market import (
    MarketAddTool, MarketSearchTool, TrialAddTool, TrialListTool,
)
from ..features.waypoints import WaypointAddTool, WaypointSearchTool


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
