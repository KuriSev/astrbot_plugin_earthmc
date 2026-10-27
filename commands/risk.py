"""RiskMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import MessageChain
import asyncio

from ..core.texts import RISK_HELP

class RiskMixin:
    async def _handle_risk(self, event: AstrMessageEvent,
                            action: str, value: str) -> str:
        action = action.lower()

        if action in ("help",):
            return RISK_HELP

        if action in ("nation",):
            nation = value.strip() if value.strip() else ""
            if not nation:
                return "❌ 用法: /em risk nation <国家名>"
            from ..tools import _nation_risk
            return await _nation_risk(nation)

        if action in ("scan",):
            umo = event.unified_msg_origin

            async def done(risk_count: int, total: int):
                try:
                    if risk_count < 0:
                        await self.context.send_message(
                            umo, MessageChain().message(
                                "❌ 全服扫描失败，无法获取城镇列表。"))
                    else:
                        await self.context.send_message(
                            umo, MessageChain().message(
                                f"✅ 全服扫描完成\n━━━━━━━━━━━━━━━━\n"
                                f"共检查 {total} 个城镇\n"
                                f"5天内可能销城 {risk_count} 个\n"
                                f"━━━━━━━━━━━━━━━━\n"
                                f"查看名单: /em risk list"))
                    logger.info("[EarthMC] 扫描通知已发送")
                except Exception as e:
                    logger.error(f"[EarthMC] 扫描通知发送失败: {e}")

            asyncio.create_task(self.scanner.scan(on_done=done))
            return "🔍 开始全服扫描，请稍候...完成后将自动通知。"

        if action in ("list",):
            # 解析: /em risk list [天数] [页码]
            # 天数=0 仅Ruins, 1~N 各自独立显示该天数段
            parts = value.split() if value.strip() else []
            days = 5
            page = 1
            if len(parts) >= 1 and parts[0].isdigit():
                days = int(parts[0])
            if len(parts) >= 2 and parts[1].isdigit():
                page = int(parts[1])
            PAGE_SIZE = 20

            # 按 days 决定筛选范围（独立，不累计）
            if days == 0:
                label = "Ruins"
                lo, hi = 0, 0
            elif days == 1:
                label = "1天"
                lo, hi = 0.01, 1
            else:
                label = f"{days}天"
                lo, hi = days, days + 0.99

            towns = self.scanner.get_risklist(days)
            updated = self.scanner.cache_age()
            # 按独立范围过滤
            towns = [t for t in towns if lo <= t["days_left"] <= hi]
            if not towns:
                return (f"📋 {label}销城风险: 无\n"
                        f"更新时间 {updated}\n"
                        f"手动扫描: /em risk scan")

            total_pages = max((len(towns) + PAGE_SIZE - 1) // PAGE_SIZE, 1)
            page = max(1, min(page, total_pages))
            start = (page - 1) * PAGE_SIZE
            end = page * PAGE_SIZE

            lines = [f"📋 {label}销城风险 ({len(towns)} 个)  更新 {updated}  第{page}/{total_pages}页"]
            shown = 0
            for t in towns:
                if shown >= end:
                    break
                if shown < start:
                    shown += 1
                    continue
                shown += 1
                d = t["days_left"]
                if d < 1:
                    day_str = "不足1天"
                elif d < 2:
                    day_str = f"约{int(d)}天"
                else:
                    day_str = f"{int(d)}天"
                lines.append(
                    f"  {t['name']}({t['nation']}) "
                    f"剩{day_str} 活跃{t['active_count']}人 ★{t['defense']}")
            if page < total_pages:
                lines.append(f"下一页: /em risk list {days} {page + 1}")
            return "\n".join(lines)

        if action in ("town",):
            from ..tools import _calc_risk
            return await _calc_risk(value) if value else "❌ 用法: /em risk town <城镇名>"

        return ("❌ 用法:\n"
                "  /em risk town <名>    评估单个城镇\n"
                "  /em risk nation <名>  国家销城排名\n"
                "  /em risk list [天] [页] 查看风险名单\n"
                "  /em risk scan          手动全服扫描")
