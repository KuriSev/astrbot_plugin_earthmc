"""MapMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..tools import MapLocationTool
from ..tools import MapPlayerTool
from ..tools import MapTownTool

class MapMixin:
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
