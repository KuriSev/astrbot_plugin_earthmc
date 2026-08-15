"""EarthMC 插件 — 路径点记录
记录玩家自建坐标地标（主世界/地狱），支持搜索
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from astrbot.api import logger
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

WAYPOINT_FILE = "earthmc_waypoints.json"
WORLDS = {"overworld": "主世界", "nether": "地狱"}


class WaypointManager:
    """管理路径点数据的增删查"""

    def __init__(self, plugin_name: str):
        self._plugin_name = plugin_name
        self._data_dir: str = ""

    @property
    def data_dir(self) -> str:
        if not self._data_dir:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            self._data_dir = os.path.join(
                str(get_astrbot_data_path()), "plugin_data", self._plugin_name)
            os.makedirs(self._data_dir, exist_ok=True)
        return self._data_dir

    @property
    def file_path(self) -> str:
        return os.path.join(self.data_dir, WAYPOINT_FILE)

    def load(self) -> list[dict]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[EarthMC] 读取路径点数据失败: {e}")
        return []

    def save(self, data: list[dict]):
        try:
            tmp = self.file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error(f"[EarthMC] 保存路径点数据失败: {e}")

    def add(self, name: str, world: str, x: int, y: int, z: int) -> dict:
        """添加路径点，返回 {"id": N, "dup_warn": str|None}"""
        data = self.load()
        world = world.lower()

        dup_warn = None
        for r in data:
            if (r.get("name", "").lower() == name.lower() and
                    r.get("world") == world):
                dup_warn = (f"⚠ 已有同名路径点 #{r['id']}: "
                            f"{r['name']} ({WORLDS.get(r['world'], r['world'])}) "
                            f"{r['x']}, {r['y']}, {r['z']}")
                break

        max_id = max((r.get("id", 0) for r in data), default=0)
        entry = {
            "id": max_id + 1,
            "name": name.strip(),
            "world": world,
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        data.append(entry)
        self.save(data)
        logger.info(f"[EarthMC] 路径点添加 #{entry['id']}: "
                    f"{entry['name']} ({world}) {x}, {y}, {z}")
        return {"id": entry["id"], "dup_warn": dup_warn}

    def delete(self, wp_id: int) -> bool:
        data = self.load()
        before = len(data)
        data = [r for r in data if r.get("id") != wp_id]
        if len(data) < before:
            self.save(data)
            return True
        return False

    def search(self, keyword: str, world: str = "") -> list[dict]:
        """按名称模糊搜索，可选按世界过滤。"""
        kw = keyword.lower()
        results = [r for r in self.load()
                   if kw in r.get("name", "").lower()
                   or kw in str(r.get("x", ""))
                   or kw in str(r.get("z", ""))]
        if world:
            results = [r for r in results if r.get("world") == world]
        return results

    def list_all(self, world: str = "") -> list[dict]:
        data = self.load()
        if world:
            data = [r for r in data if r.get("world") == world]
        return data


# 模块级引用，由 main.py 设置
_wp: WaypointManager | None = None


def set_waypoint_manager(mgr: WaypointManager):
    global _wp
    _wp = mgr


def _fmt(w: dict) -> str:
    return (f"  #{w['id']}  {w['name']}  "
            f"({WORLDS.get(w['world'], w['world'])})  "
            f"{w['x']}, {w['y']}, {w['z']}  [{w.get('added_at', '?')}]")


@dataclass
class WaypointAddTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_waypoint_add"
    description: str = (
        "记录一个自定义路径点/地标。玩家给出坐标和名称。"
        "世界参数: overworld(主世界) 或 nether(地狱/下界)。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "路径点名称"},
            "world": {
                "type": "string",
                "description": "所在世界: overworld(主世界) 或 nether(地狱/下界)。"
                "用户说'地狱''下界''nether'都表示 nether，说'主世界''overworld'表示 overworld",
                "enum": ["overworld", "nether"],
            },
            "x": {"type": "integer", "description": "X 坐标"},
            "y": {"type": "integer", "description": "Y 坐标（高度）"},
            "z": {"type": "integer", "description": "Z 坐标"},
        },
        "required": ["name", "world", "x", "y", "z"],
    })

    async def call(self, context, **kwargs) -> str:
        if _wp is None:
            return "❌ 路径点功能未初始化。"

        name = (kwargs.get("name", "") or "").strip()
        world = (kwargs.get("world", "") or "").strip().lower()
        if not name:
            return "❌ 请提供路径点名称。"
        if world not in WORLDS:
            return "❌ 世界必须是 overworld(主世界) 或 nether(地狱)。"

        result = _wp.add(name, world,
                         kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("z", 0))
        msg = (f"✅ 已记录 #{result['id']}  {name}  "
               f"({WORLDS[world]})  {kwargs.get('x')}, {kwargs.get('y')}, {kwargs.get('z')}")
        if result.get("dup_warn"):
            msg += f"\n{result['dup_warn']}"
        return msg


@dataclass
class WaypointSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_waypoint_search"
    description: str = (
        "搜索已记录的自定义路径点/地标。按名称模糊匹配。"
        "可用于回答'XX在哪''XX的坐标'等问题。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "路径点名称关键词"},
            "world": {
                "type": "string",
                "description": "可选，按世界过滤: overworld(主世界) 或 nether(地狱/下界)",
                "enum": ["overworld", "nether"],
            },
        },
        "required": ["keyword"],
    })

    async def call(self, context, **kwargs) -> str:
        if _wp is None:
            return "❌ 路径点功能未初始化。"

        keyword = (kwargs.get("keyword", "") or "").strip()
        world = (kwargs.get("world", "") or "").strip().lower()
        if not keyword:
            return "❌ 请提供搜索关键词。"

        results = _wp.search(keyword, world)
        if not results:
            return f"📍 路径点查询 \"{keyword}\"\n暂无相关记录。"
        lines = [f"📍 路径点查询 \"{keyword}\" ({len(results)} 个)"]
        for w in results:
            lines.append(_fmt(w))
        return "\n".join(lines)
