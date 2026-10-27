"""WpMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..core.texts import WAYPOINT_HELP

class WpMixin:
    async def _handle_wp(self, event: AstrMessageEvent,
                         action: str, value: str) -> str:
        action = (action or "").lower()
        value = (value or "").strip()
        from ..features.waypoints import WORLDS

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
