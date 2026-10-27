"""MarketMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..core.texts import MARKET_HELP

class MarketMixin:
    async def _handle_market(self, event: AstrMessageEvent,
                              action: str, value: str) -> str:
        action = action.lower()

        if action in ("help",):
            return MARKET_HELP

        if action in ("list", "all"):
            data = self.market.list_all()
            if not data:
                return "📦 市场暂无记录。"
            lines = [f"📦 市场记录 ({len(data)} 条)"]
            for r in data:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 分类型子命令: trial/sell/buy
        action_map = {"sell": "出售", "buy": "收购", "trial": "试炼"}
        if action in action_map:
            act = action_map[action]
            return self._handle_market_action(act, value)

        return MARKET_HELP

    def _handle_market_action(self, act: str, value: str) -> str:
        """处理 /em market <trial|sell|buy> <sub> [args]"""
        parts = value.split(maxsplit=1) if value.strip() else []
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        # 列表
        if not sub or sub in ("list", "all"):
            data = self.market.list_by_action(act)
            if not data:
                return f"📦 {act}记录: 暂无"
            lines = [f"📦 {act}记录 ({len(data)} 条)"]
            for r in data:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 搜索（试炼不搜索，只列出）
        if sub in ("search", "查") and act != "试炼":
            if not rest:
                return f"❌ 用法: /em market {act.lower()} search <关键词>"
            results = self.market.search(rest, act)
            if not results:
                return f"📦 {act}查询 \"{rest}\"\n暂无相关记录。"
            lines = [f"📦 {act}查询 \"{rest}\""]
            for r in results:
                lines.append(
                    f"  #{r['id']}  {r['type']}/{r['location']}  "
                    f"{r['action']}  {r['price']} × {r['amount']} {r['item']}  "
                    f"[{r.get('added_at', '?')}]"
                )
            return "\n".join(lines)

        # 添加
        if sub in ("add", "添加"):
            rp = rest.split() if rest else []
            if not rp:
                return (f"❌ 用法: /em market {act.lower()} add "
                        f"<t/n> <传送点名> [价格 数量 物品名]")

            tp = rp[0].lower()
            if tp not in ("t", "n"):
                return "❌ 类型必须是 t（城镇传送点）或 n（国家传送点）"
            if len(rp) < 2:
                return "❌ 缺少传送点名称。"

            if act == "试炼":
                entry = {
                    "type": tp,
                    "location": rp[1],
                    "action": act,
                    "item": "试炼密室",
                    "amount": 1,
                    "price": "",
                }
            else:
                if len(rp) < 5:
                    return (f"❌ 用法: /em market {act.lower()} add "
                            f"<t/n> <传送点名> <价格> <数量> <物品名>\n"
                            f"例如: /em market {act.lower()} add t mending 8 1 经验修补")
                price_raw = rp[2].rstrip("gG")
                entry = {
                    "type": tp,
                    "location": rp[1],
                    "price": f"{price_raw}g",
                    "amount": int(rp[3]) if rp[3].isdigit() else 1,
                    "item": " ".join(rp[4:]),
                    "action": act,
                }

            result = self.market.add(entry)
            eid = result["id"]
            msg = (f"✅ 已添加 #{eid}  "
                   f"{entry['type']}/{entry['location']}  "
                   f"{entry['action']}  "
                   f"{entry['price']} × {entry['amount']} {entry['item']}")
            if result.get("dup_warn"):
                msg += f"\n{result['dup_warn']}"
            return msg

        # 删除
        if sub in ("del", "delete", "remove", "删"):
            if not rest or not rest.isdigit():
                return "❌ 用法: /em market del <id>"
            eid = int(rest)
            if self.market.delete(eid):
                return f"✅ 已删除 #{eid}。"
            return f"❌ 未找到 #{eid}。"

        search_line = (f"/em market {act.lower()} search <关键词>     搜索\n"
                       if act != "试炼" else "")
        return (f"📦 {act}管理\n"
                f"/em market {act.lower()} add <t/n> <点> ...  添加\n"
                f"/em market {act.lower()} del <id>            删除\n"
                f"{search_line}"
                f"/em market {act.lower()}                     查看全部")
