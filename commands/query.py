"""查询类命令：工具注册表与调用辅助。"""
from ..core.api import auth_error_active
from ..core.texts import API_KEY_INVALID, API_KEY_REQUIRED
from ..tools import (
    ServerStatusTool, VotePartyTool, TownTool, NationTool,
    PlayerTool, OnlinePlayersTool, NearbyTownsTool,
    LocationTool, QuarterTool, MysteryMasterTool,
    MapTownTool, MapPlayerTool, MapLocationTool,
)
from ..features.risk import (
    TownRiskTool, TownMembersTool, NationTownsTool, NationRiskTool,
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
        result = await tool_cls().call(None)
    elif tool_cls is TownTool:
        result = await tool_cls().call(None, name=arg)
    elif tool_cls is NationTool:
        result = await tool_cls().call(None, name=arg)
    elif tool_cls is PlayerTool:
        result = await tool_cls().call(None, name=arg)
    elif tool_cls is NearbyTownsTool:
        result = await tool_cls().call(None, town=arg)
    elif tool_cls is McMMOTopTool:
        result = await tool_cls().call(None, skill=arg)
    elif tool_cls is QuarterTool:
        result = await tool_cls().call(None, query=arg)
    else:
        return "❌ 未知工具类型"
    # 本次请求若因 key 无效被拒，直接给 key 提示，而不是「未找到 XX」
    return API_KEY_INVALID if auth_error_active() else result


async def _run_location(x_str: str, z_str: str) -> str:
    try:
        x = int(x_str)
        z = int(z_str)
    except (ValueError, TypeError):
        return "❌ 用法: /em location <x> <z>  例如 /em location 2000 10000"
    result = await LocationTool().call(None, x=x, z=z)
    return API_KEY_INVALID if auth_error_active() else result


async def _check_api_key_text() -> str:
    """`/em test`：验证当前 api_key 是否有效（用 /mcmmo-top，按 key 限流）。"""
    from ..core.api import check_api_key, has_api_key

    if not has_api_key():
        return API_KEY_REQUIRED

    state, detail = await check_api_key()
    head = "🔑 API Key 检查" + chr(10) + "━━━━━━━━━━━━━━━━" + chr(10)
    if state == "ok":
        return head + "✅ 有效" + chr(10) + chr(10) + "（该测试调用 /mcmmo-top，会占用 2 分钟一次的 mcMMO 查询配额）"
    if state == "rate_limited":
        return head + "✅ 有效" + chr(10) + chr(10) + "服务器返回限流（限流按 key 计），说明 key 已被认可；2 分钟后 /em mmo 会自动恢复。"
    if state == "invalid":
        return API_KEY_INVALID + (chr(10) + chr(10) + "服务器返回: " + detail if detail else "")
    return head + "⚠️ 无法确认" + chr(10) + "服务器返回: " + detail
