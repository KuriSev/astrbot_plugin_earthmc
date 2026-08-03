"""
EarthMC 插件 — 市场交易信息
持久化存储 · 模糊查询 · LLM 工具 · 重复检测
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from astrbot.api import logger
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext

MARKET_FILE = "earthmc_market.json"


# ════════════════════════════════════════
# 数据管理
# ════════════════════════════════════════

class MarketManager:
    """管理市场交易数据的增删查"""

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
        return os.path.join(self.data_dir, MARKET_FILE)

    def load(self) -> list[dict]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[EarthMC] 读取市场数据失败: {e}")
        return []

    def save(self, data: list[dict]):
        try:
            tmp = self.file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error(f"[EarthMC] 保存市场数据失败: {e}")

    def add(self, entry: dict) -> dict:
        """
        添加一条记录。返回 {"id": N, "dup_warn": str | None}。
        重复检测: 同 type+location+action 下，新旧 item 名互相包含。
        """
        data = self.load()

        # 分配 ID
        max_id = max((r.get("id", 0) for r in data), default=0)
        entry["id"] = max_id + 1
        entry.setdefault("added_at",
                         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        entry.setdefault("amount", 1)

        # 重复检测
        dup_warn = None
        item_lower = entry.get("item", "").lower()
        for r in data:
            if (r.get("type") == entry.get("type") and
                    r.get("location", "").lower() == entry.get("location", "").lower() and
                    r.get("action") == entry.get("action")):
                existing = r.get("item", "").lower()
                if item_lower in existing or existing in item_lower:
                    dup_warn = (f"⚠ 已有类似条目 #{r['id']}: "
                                f"{r['type']}/{r['location']} {r['action']} "
                                f"{r['price']} × {r['amount']} {r['item']}，"
                                f"如重复请 /em market del {r['id']}")
                    break

        data.append(entry)
        self.save(data)
        logger.info(f"[EarthMC] 市场添加 #{entry['id']}: {entry['type']}/{entry['location']} "
                    f"{entry['action']} {entry['price']} × {entry['amount']} {entry['item']}")
        return {"id": entry["id"], "dup_warn": dup_warn}

    def delete(self, entry_id: int) -> bool:
        data = self.load()
        before = len(data)
        data = [r for r in data if r.get("id") != entry_id]
        if len(data) < before:
            self.save(data)
            return True
        return False

    def search(self, keyword: str, action: str = "") -> list[dict]:
        """模糊匹配物品名。action 可选: 出售/收购 过滤。"""
        kw = keyword.lower()
        data = self.load()
        results = [r for r in data if kw in r.get("item", "").lower()]
        if action:
            results = [r for r in results if r.get("action") == action]
        return results

    def list_all(self) -> list[dict]:
        return self.load()


# ════════════════════════════════════════
# LLM 工具
# ════════════════════════════════════════

# 模块级引用，由 main.py 在实例化后设置
_market: MarketManager | None = None


def set_market_manager(mgr: MarketManager):
    global _market
    _market = mgr


@dataclass
class MarketAddTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_market_add"
    description: str = (
        "添加一条交易信息到市场表格。从用户的自然语言中提取传送点类型、名称、交易方式、物品、数量、价格。"
        "如果信息不足以确定必填字段（type/location/item），返回引导提示让用户补充，不要猜测。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "传送点类型: t(城镇传送点/t spawn) 或 n(国家传送点/n spawn)",
                "enum": ["t", "n"],
            },
            "location": {
                "type": "string",
                "description": "传送点名称。如 /t spawn mending 中的 mending",
            },
            "action": {
                "type": "string",
                "description": "交易方向。用户说'收'=收购，'卖/出/有/出售'=出售",
                "enum": ["出售", "收购"],
            },
            "item": {
                "type": "string",
                "description": "物品名称（必须明确，不要猜测）",
            },
            "amount": {
                "type": "integer",
                "description": "数量。用户可能说'一个/一本/1个/one'等，统一转为纯数字。默认 1",
                "default": 1,
            },
            "price": {
                "type": "string",
                "description": "单价，如 8g。只提取 g 为单位的数字部分，如'1g50'中 1g 是价格、50 是数量",
            },
        },
        "required": ["type", "location", "action", "item"],
    })

    async def call(self, context, **kwargs) -> str:
        if _market is None:
            return "❌ 市场功能未初始化。"

        entry = {
            "type": kwargs.get("type", "").lower(),
            "location": (kwargs.get("location", "") or "").strip(),
            "action": kwargs.get("action", "出售"),
            "item": (kwargs.get("item", "") or "").strip(),
            "amount": kwargs.get("amount", 1) or 1,
            "price": (kwargs.get("price", "") or "").strip(),
        }

        if not entry["location"]:
            return "❌ 请提供传送点名称。例如：/t spawn mending 有 8g 经验修补"
        if not entry["item"]:
            return "❌ 请提供物品名称。例如：mending 有 8g 一本经验修补"

        result = _market.add(entry)
        eid = result["id"]

        msg = (f"✅ 已添加 #{eid}  "
               f"{entry['type']}/{entry['location']}  "
               f"{entry['action']}  "
               f"{entry['price']} × {entry['amount']} {entry['item']}")
        if result.get("dup_warn"):
            msg += f"\n{result['dup_warn']}"
        return msg


@dataclass
class MarketSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "earthmc_market_search"
    description: str = (
        "查询市场表格中的交易信息，支持物品名模糊匹配。"
        "可用于回答'哪里卖XX''谁收XX''XX在哪买'等问题。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "物品关键词，支持模糊匹配。如'青金石'可匹配'青金石块''青金石矿'等",
            },
            "action": {
                "type": "string",
                "description": "可选，过滤交易方向: 出售 或 收购。如用户问'哪里卖'则传出售，'有人收吗'则传收购",
                "enum": ["出售", "收购"],
            },
        },
        "required": ["keyword"],
    })

    async def call(self, context, **kwargs) -> str:
        if _market is None:
            return "❌ 市场功能未初始化。"

        keyword = (kwargs.get("keyword", "") or "").strip()
        action = (kwargs.get("action", "") or "").strip()

        if not keyword:
            return "❌ 请提供物品关键词。"

        results = _market.search(keyword, action)

        if not results:
            act_str = f"（{action}）" if action else ""
            return f"📦 市场查询 \"{keyword}\"{act_str}\n暂无相关记录。"

        act_str = f"（{action}）" if action else ""
        lines = [f"📦 市场查询 \"{keyword}\"{act_str}"]
        for r in results:
            lines.append(
                f"  #{r['id']}  {r['type']}/{r['location']}  "
                f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                f"[{r.get('added_at', '?')}]"
            )
        return "\n".join(lines)
