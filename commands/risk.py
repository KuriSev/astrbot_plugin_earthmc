"""RiskMixin：销城分析、国家/城镇废墟关注与状态查看。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..core.api import auth_error_active
from ..core.texts import RISK_HELP, API_KEY_INVALID

_ADD_OPS = {"add", "添加"}
_DEL_OPS = {"del", "delete", "remove", "删除", "移除"}


class RiskMixin:
    async def _handle_risk(self, event: AstrMessageEvent,
                           action: str, value: str) -> str:
        action = (action or "").lower()
        value = (value or "").strip()

        if action in ("help",):
            return RISK_HELP

        # 裸 /em risk → 关注状态卡（读快照，不联网）
        if action in ("", "status", "列表"):
            gid = event.message_obj.group_id
            if not gid:
                return RISK_HELP
            checker = getattr(self, "ruins_checker", None)
            if checker is None:
                return "❌ 废墟关注未初始化。"
            # 手动查询直接拉最新数据（只读，不改写快照）
            live = getattr(checker, "live_status", None)
            text = (await live(str(gid)) if live is not None
                    else checker.status_text(str(gid)))
            return API_KEY_INVALID if auth_error_active() else text

        if action in ("town", "nation"):
            op, _, name = value.partition(" ")
            op = op.lower()
            name = name.strip()
            if op in _ADD_OPS:
                return await self._risk_watch_add(event, action, name, value)
            if op in _DEL_OPS:
                return await self._risk_watch_del(event, action, name, value)
            # 否则整段当作名称做实时分析
            if not value:
                return (f"❌ 用法: /em risk {action} <名称>" if action == "town"
                        else "❌ 用法: /em risk nation <国家名>")
            if action == "town":
                from ..features.risk import _calc_risk
                text = await _calc_risk(value)
            else:
                from ..features.risk import _nation_risk
                text = await _nation_risk(value)
            return API_KEY_INVALID if auth_error_active() else text

        return ("❌ 用法:\n"
                "  /em risk                查看废墟关注状态\n"
                "  /em risk town <名>      评估单个城镇\n"
                "  /em risk nation <名>    国家销城情况\n"
                "  /em risk town add|del <名>    关注/取消关注城镇\n"
                "  /em risk nation add|del <名>  关注/取消关注国家")

    async def _risk_watch_add(self, event: AstrMessageEvent,
                              kind: str, name: str, raw: str) -> str:
        gid = event.message_obj.group_id
        if not gid:
            return "❌ 废墟关注仅在群聊中可用。"
        mgr = getattr(self, "ruins_watch", None)
        checker = getattr(self, "ruins_checker", None)
        if mgr is None or checker is None:
            return "❌ 废墟关注未初始化。"
        if not name:
            return (f"❌ 用法: /em risk {'town' if kind == 'town' else 'nation'} add <名称>")

        key, display = name, name
        if kind == "town":
            # 先解析 uuid：改名不影响关注，名字只用于显示
            from ..core.api import post as api_post
            data = await api_post("/towns", {"query": [name]})
            if auth_error_active():
                return API_KEY_INVALID
            if not data or not isinstance(data, list) or not data:
                return f"❌ 未找到城镇「{name}」，未加入关注。"
            t = data[0]
            key = t.get("uuid") or ""
            display = t.get("name") or name
            if not key:
                return f"❌ 未获取到城镇「{name}」的 uuid，未加入关注。"
            ok, res = mgr.add_town(str(gid), key, display, event.unified_msg_origin)
        else:
            from ..core.api import post as api_post
            data = await api_post("/nations", {"query": [name]})
            if auth_error_active():
                return API_KEY_INVALID
            if not data or not isinstance(data, list) or not data:
                return f"❌ 未找到国家「{name}」，未加入关注。"
            n = data[0]
            key = n.get("uuid") or ""
            display = n.get("name") or name
            if not key:
                return f"❌ 未获取到国家「{name}」的 uuid，未加入关注。"
            ok, res = mgr.add_nation(str(gid), key, display, event.unified_msg_origin)
        if not ok:
            return res

        # 立刻刷新并输出该对象的当前情况
        _, found = await checker.refresh()
        return checker.added_text(str(gid), kind, key, display, found)

    async def _risk_watch_del(self, event: AstrMessageEvent,
                              kind: str, name: str, raw: str) -> str:
        gid = event.message_obj.group_id
        if not gid:
            return "❌ 废墟关注仅在群聊中可用。"
        mgr = getattr(self, "ruins_watch", None)
        if mgr is None:
            return "❌ 废墟关注未初始化。"
        if not name:
            return (f"❌ 用法: /em risk {'town' if kind == 'town' else 'nation'} del <名称>")
        ok, res = (mgr.del_town(str(gid), name) if kind == "town"
                   else mgr.del_nation(str(gid), name))
        return f"✅ 已取消关注 {res}" if ok else res
