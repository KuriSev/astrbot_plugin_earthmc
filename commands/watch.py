"""WatchCommandMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
import time

from ..core.texts import WATCH_HELP

class WatchCommandMixin:
    async def _handle_watch(self, event: AstrMessageEvent,
                            action: str, value: str) -> str:
        group_id = event.message_obj.group_id or event.message_obj.session_id
        if not group_id:
            return "❌ watch 功能仅在群聊中可用。"

        action = action.lower()
        group_key = str(group_id)

        # 帮助
        if action in ("help",):
            return WATCH_HELP

        # 关闭（两步确认：先登记，回复 /em confirm 执行）
        if action in ("off", "stop", "关闭"):
            config = self.watch.load_config()
            if group_key not in config:
                return "⚠ 本群未开启自动提醒。"
            self._pending_confirm[group_key] = {
                "user": str(event.get_sender_id()),
                "ts": time.time(),
                "kind": "watch_off",
            }
            return ("⚠ 将关闭本群**所有**自动提醒（VP/玩家/城镇监控），不可撤销。\n"
                    "回复 /em confirm 确认 /em cancel 取消（30 秒内有效）。")

        # 玩家
        if action in ("player", "players"):
            return await self._cmd_watch_player(event, value, group_key)

        # 城镇
        if action in ("town",):
            return await self._cmd_watch_town(event, value, group_key)

        # 查看全部
        return self._cmd_watch_status(group_key)

    async def _cmd_watch_player(self, event: AstrMessageEvent,
                                 value: str, group_key: str) -> str:
        parts = value.split(maxsplit=1)
        sub_action = parts[0].lower() if parts else ""
        names_str = parts[1] if len(parts) > 1 else ""

        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]
        watched: dict = w.setdefault("players", {})

        # 添加
        if sub_action in ("add", "添加"):
            if not names_str:
                return ("❌ 用法: /em watch player add <玩家名> ...\n"
                        "例如: /em watch player add Fixer Warriorrr")
            existing_lower = {k.lower() for k in watched}
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in existing_lower]
            if not new:
                return "⚠ 这些玩家已在监控列表中。"

            # 校验玩家是否存在，并记录当前城镇作为基线
            from ..core.api import post as api_post
            data = await api_post("/players", {"query": new})
            existing = set()
            town_map = {}
            canon = {}
            if data and isinstance(data, list):
                existing = {p.get("name", "").lower() for p in data}
                town_map = {p.get("name", "").lower(): (p.get("town") or {}).get("name", "")
                            for p in data}
                canon = {p.get("name", "").lower(): p.get("name", "")
                         for p in data if p.get("name")}

            valid, invalid = [], []
            for name in new:
                (valid if name.lower() in existing else invalid).append(name)

            added = []
            for name in valid:
                cname = canon.get(name.lower(), name)   # 落服务端规范大小写
                watched[cname] = {"online": False,
                                  "town": town_map.get(name.lower(), "")}
                added.append(cname)
            if valid:
                self.watch.save_config(config)
                self.watch.ensure_running()

            msg_parts = []
            if added:
                msg_parts.append(f"✅ 已添加: {', '.join(added)}")
            if invalid:
                msg_parts.append(f"❌ 玩家不存在: {', '.join(invalid)}")
            return "\n".join(msg_parts) if msg_parts else "⚠ 未能添加任何玩家。"

        # 删除
        if sub_action in ("del", "delete", "remove", "删除", "移除"):
            if not names_str:
                return ("❌ 用法: /em watch player del <玩家名>\n"
                        "例如: /em watch player del Fixer")
            names = [n.strip() for n in names_str.replace(",", " ").split()]
            names_lower = {n.lower() for n in names}
            removed = [k for k in watched if k.lower() in names_lower]
            for k in removed:
                del watched[k]
            if not removed:
                return "⚠ 这些玩家不在监控列表中。"
            if not watched:
                del w["players"]
            self.watch.save_config(config)
            return (f"✅ 已移除玩家监控\n━━━━━━━━━━━━━━━━\n"
                    f"👤 {', '.join(removed)}")

        # 查看
        if not watched:
            return ("📊 玩家上线监控: 未添加\n━━━━━━━━━━━━━━━━\n"
                    "添加: /em watch player add <玩家名>\n"
                    "例如: /em watch player add Fixer")

        lines = []
        for name, state in sorted(watched.items()):
            s = "🟢 在线" if state.get("online") else "🔴 离线"
            lines.append(f"  {name}  {s}")
        return (f"📊 玩家上线监控 ({len(watched)} 人)\n"
                f"━━━━━━━━━━━━━━━━\n" + "\n".join(lines) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"添加: /em watch player add <名>\n"
                f"移除: /em watch player del <名>")

    async def _cmd_watch_town(self, event: AstrMessageEvent,
                               value: str, group_key: str) -> str:
        parts = value.split(maxsplit=1)
        sub_action = parts[0].lower() if parts else ""
        names_str = parts[1] if len(parts) > 1 else ""

        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]
        watched: dict = w.setdefault("towns", {})

        if sub_action in ("add", "添加"):
            if not names_str:
                return ("❌ 用法: /em watch town add <城镇名> ...\n"
                        "例如: /em watch town add Beijing Shanghai")
            existing_lower = {k.lower() for k in watched}
            new = [n.strip() for n in names_str.replace(",", " ").split()
                   if n.strip() and n.strip().lower() not in existing_lower]
            if not new:
                return "⚠ 这些城镇已在监控列表中。"

            from ..core.api import post as tpost
            tdata = await tpost("/towns", {"query": new})
            valid, invalid = [], []
            if tdata and isinstance(tdata, list):
                existing = {t.get("name", "").lower() for t in tdata}
                for n in new:
                    (valid if n.lower() in existing else invalid).append(n)
            else:
                invalid = new

            # 拉取城镇的当前状态作为初始值
            for t in tdata:
                if isinstance(t, dict):
                    tname = t.get("name", "")
                    if tname.lower() in [n.lower() for n in valid]:
                        stats = t.get("stats") or {}
                        cur_names = sorted(
                            r.get("name", "") for r in (t.get("residents") or []))
                        watched[tname] = {
                            "resident_count": stats.get("numResidents", 0),
                            "residents": cur_names,
                            "blocks": stats.get("numTownBlocks", 0),
                            "maxBlocks": stats.get("maxTownBlocks", 0),
                            "balance": stats.get("balance", 0),
                            "mayor": (t.get("mayor") or {}).get("name", ""),
                            "nation": (t.get("nation") or {}).get("name", ""),
                            "is_open": (t.get("status") or {}).get("isOpen", False),
                            "is_ruined": (t.get("status") or {}).get("isRuined", False),
                        }
            if valid:
                self.watch.save_config(config)
                self.watch.ensure_running()

            lines = []
            if valid:
                lines.append("✅ 已添加城镇监控:")
                for t in tdata:
                    if isinstance(t, dict) and t.get("name", "").lower() in [n.lower() for n in valid]:
                        s = t.get("stats") or {}
                        mayor = (t.get("mayor") or {}).get("name", "?")
                        nation = (t.get("nation") or {}).get("name", "无")
                        lines.append(
                            f"  {t['name']}({nation})  {s.get('numResidents',0)}人  "
                            f"{s.get('numTownBlocks',0)}方块  {s.get('balance',0)}G  市长{mayor}")
            if invalid:
                lines.append("❌ 城镇不存在: " + ", ".join(invalid))
            return "\n".join(lines) if lines else "⚠ 未能添加任何城镇。"

        if sub_action in ("del", "delete", "remove", "删除", "移除"):
            if not names_str:
                return ("❌ 用法: /em watch town del <城镇名>\n"
                        "例如: /em watch town del Beijing")
            names = [n.strip() for n in names_str.replace(",", " ").split()]
            names_lower = {n.lower() for n in names}
            removed = [k for k in watched if k.lower() in names_lower]
            for k in removed:
                del watched[k]
            if not removed:
                return "⚠ 这些城镇不在监控列表中。"
            if not watched:
                del w["towns"]
            self.watch.save_config(config)
            return f"✅ 已移除城镇监控: {', '.join(removed)}"

        if not watched:
            return ("📊 城镇变动监控: 未添加\n━━━━━━━━━━━━━━━━\n"
                    "添加: /em watch town add <城镇名>\n"
                    "例如: /em watch town add Beijing")

        lines = [f"📊 城镇变动监控 ({len(watched)} 个)"]
        for name in sorted(watched):
            old = watched[name]
            r = old.get("resident_count", "?")
            b = old.get("blocks", "?")
            bal = old.get("balance", "?")
            lines.append(f"  {name}  {r}人  {b}方块  {bal}G")
        return "\n".join(lines)

    def _cmd_watch_status(self, group_key: str) -> str:
        config = self.watch.load_config()
        w = config.get(group_key)
        if not w:
            return ("📊 本群自动提醒: 未开启\n━━━━━━━━━━━━━━━━\n"
                    "开启 VP: /em vp <票数> ...\n"
                    "添加玩家: /em watch player add <名>\n"
                    "查看全部: /em watch")

        parts = []
        th = w.get("vp_thresholds")
        if th:
            parts.append("🎯 VP 提醒线: " +
                         " > ".join(str(t) for t in sorted(th, reverse=True)))
        else:
            parts.append("🎯 VP 提醒: 未设置")

        at = w.get("vp_at")
        if at:
            parts.append("📣 @ 名单: " + " ".join(str(q) for q in at))
        else:
            parts.append("📣 @ 名单: 未设置")

        at_lines = w.get("vp_at_lines")
        if at_lines:
            parts.append("🎯 @ 触发线: " +
                         " > ".join(str(t) for t in sorted(at_lines, reverse=True)))
        else:
            parts.append("🎯 @ 触发线: 未设置（默认不 @）")

        ds, de = w.get("vp_dnd_start"), w.get("vp_dnd_end")
        if ds and de:
            parts.append(f"🌙 免打扰: {ds} - {de} (UTC+8)")
        else:
            parts.append("🌙 免打扰: 未设置")

        pl = w.get("players")
        if pl:
            parts.append(f"👤 玩家监控({len(pl)}): " + ", ".join(sorted(pl)))
        else:
            parts.append("👤 玩家监控: 未设置")

        tl = w.get("towns")
        if tl:
            parts.append(f"🏘 城镇监控({len(tl)}): " + ", ".join(sorted(tl)))
        else:
            parts.append("🏘 城镇监控: 未设置")

        return (f"📊 本群自动提醒设置\n━━━━━━━━━━━━━━━━\n" +
                "\n".join(parts) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"状态: 运行中 ✅\n"
                f"关闭: /em watch off")

    def _handle_confirm(self, event: AstrMessageEvent) -> str:
        """/em confirm：确认执行本群待确认的破坏性操作（30 秒内，限发起人）。"""
        group_id = event.message_obj.group_id
        if not group_id:
            return "❌ /em confirm 仅在群聊中可用。"
        group_key = str(group_id)
        pc = self._pending_confirm.get(group_key)
        if not pc:
            return "❌ 当前没有待确认的操作。"
        if time.time() - pc["ts"] > 30:
            self._pending_confirm.pop(group_key, None)
            return "❌ 确认已超时（30 秒），请重新发起。"
        if pc["user"] != str(event.get_sender_id()):
            return "❌ 该操作由他人发起，仅发起人可确认。"
        kind = pc.get("kind", "")
        self._pending_confirm.pop(group_key, None)
        if kind == "watch_off":
            config = self.watch.load_config()
            if group_key in config:
                del config[group_key]
                self.watch.save_config(config)
            return "✅ 已确认，本群所有自动提醒已关闭。"
        return "✅ 已确认。"

    def _handle_cancel(self, event: AstrMessageEvent) -> str:
        """/em cancel：取消本群待确认的破坏性操作。取消是保护性操作，任何群成员可取消。"""
        group_id = event.message_obj.group_id
        if not group_id:
            return "❌ /em cancel 仅在群聊中可用。"
        group_key = str(group_id)
        if group_key in self._pending_confirm:
            self._pending_confirm.pop(group_key)
            return "✅ 已取消该操作。"
        return "❌ 当前没有待取消的操作。"
