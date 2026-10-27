"""VPMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..core.texts import VP_USAGE
from ..core.texts import _OP_ALIASES
from ..features.watch import current_cn_minutes
from ..features.watch import in_dnd
from ..features.watch import parse_cn_time

class VPMixin:
    async def _cmd_vp(self, event: AstrMessageEvent,
                       value: str, group_key: str) -> str:
        if not value or value.strip().lower() in ("help", "帮助", "?"):
            return ("📊 VP 提醒用法\n━━━━━━━━━━━━━━━━\n"
                    "/em vp <票数> ...              多级提醒\n"
                    "/em vp at add|del|reset|off <QQ号>   @ 名单\n"
                    "/em vp atline add|del|reset|off <票数>  标记哪些线触发 @\n"
                    "/em vp dnd <开始> <结束>        免打扰(UTC+8)\n"
                    "/em vp off                     清除 VP 阈值\n"
                    "/em vp status                  查看本群配置\n"
                    "（留空 at/atline 显示当前配置）")

        tokens = value.replace(",", " ").split()
        mode = None                 # None=阈值上下文 | "at" | "atline" | "dnd"
        thresholds: list[int] = []
        at_list: list[int] = []
        atline_list: list[int] = []
        dnd_tokens: list[str] = []
        do_status = False
        at_op = atline_op = None    # None=留空(不操作) | "add" | "del" | "reset"
        clear_th = clear_at = clear_atlines = clear_dnd = False

        for tok in tokens:
            low = tok.lower()
            if low in ("at", "@"):
                mode = "at"
            elif low == "atline":
                mode = "atline"
            elif low == "dnd":
                mode = "dnd"
            elif low in ("off", "clear", "none"):
                if mode == "at":
                    clear_at = True
                elif mode == "atline":
                    clear_atlines = True
                elif mode == "dnd":
                    clear_dnd = True
                else:
                    clear_th = True
            elif low == "status":
                do_status = True
            elif mode == "at":
                op = _OP_ALIASES.get(low)
                if op:
                    if at_op:
                        return f"❌ 冲突：at 只能指定一个操作（add/del/reset）\n\n{VP_USAGE}"
                    at_op = op
                elif tok.isdigit():
                    if at_op is None:
                        return ("❌ /em vp at 需要关键字：add|del|reset|off <QQ号>\n"
                                "   例如 /em vp at add 123456\n\n" + VP_USAGE)
                    at_list.append(int(tok))
                else:
                    break          # 格式不符 → 静默截断，忽略其后全部
            elif mode == "atline":
                op = _OP_ALIASES.get(low)
                if op:
                    if atline_op:
                        return f"❌ 冲突：atline 只能指定一个操作（add/del/reset）\n\n{VP_USAGE}"
                    atline_op = op
                elif tok.isdigit():
                    if atline_op is None:
                        return ("❌ /em vp atline 需要关键字：add|del|reset|off <票数>\n"
                                "   例如 /em vp atline add 200\n\n" + VP_USAGE)
                    atline_list.append(int(tok))
                else:
                    break          # 格式不符 → 静默截断，忽略其后全部
            elif mode == "dnd":
                if len(dnd_tokens) >= 2:
                    break          # 已够起止两个时间 → 静默截断
                dnd_tokens.append(tok)
            else:
                try:
                    t = int(tok)
                except ValueError:
                    break          # 非数字 → 静默截断，忽略其后全部
                if t <= 0:
                    return f"❌ 票数必须大于 0: {tok}\n\n{VP_USAGE}"
                thresholds.append(t)

        if do_status:
            return self._vp_status_text(group_key)

        # at / atline 留空（无操作、无 clear）→ 不修改配置，显示当前配置
        if mode == "at" and at_op is None and not at_list and not clear_at:
            return self._vp_status_text(group_key)
        if mode == "atline" and atline_op is None and not atline_list and not clear_atlines:
            return self._vp_status_text(group_key)

        # 缺参边界
        if mode == "at" and at_op and not at_list:
            return f"❌ at {at_op} 后面至少需要一个 QQ 号\n\n{VP_USAGE}"
        if mode == "atline" and atline_op and not atline_list:
            return f"❌ atline {atline_op} 后面至少需要一个票数\n\n{VP_USAGE}"
        if mode == "dnd" and not dnd_tokens and not clear_dnd:
            return f"❌ /em vp dnd 需要起止两个时间\n\n{VP_USAGE}"
        # 既操作又清除
        if clear_at and (at_list or at_op):
            return f"❌ 冲突：at 与 at off 不能同时使用\n\n{VP_USAGE}"
        if clear_atlines and (atline_list or atline_op):
            return f"❌ 冲突：atline 与 atline off 不能同时使用\n\n{VP_USAGE}"
        if clear_dnd and dnd_tokens:
            return f"❌ 冲突：dnd 与 dnd off 不能同时使用\n\n{VP_USAGE}"

        # 免打扰时间解析校验
        dnd_start = dnd_end = None
        if dnd_tokens:
            if len(dnd_tokens) == 1:
                return f"❌ 免打扰需要起止两个时间\n\n{VP_USAGE}"
            if (parse_cn_time(dnd_tokens[0]) is None
                    or parse_cn_time(dnd_tokens[1]) is None):
                return (f"❌ 免打扰时间格式无效: {dnd_tokens[0]} {dnd_tokens[1]}"
                        f"（支持 HH:MM 或裸小时）\n\n{VP_USAGE}")
            dnd_start, dnd_end = dnd_tokens[0], dnd_tokens[1]

        # 落盘
        config = self.watch.load_config()
        if group_key not in config:
            config[group_key] = {"umo": event.unified_msg_origin}
        w = config[group_key]

        # atline 校验：标记的票数必须在提醒线中，否则拒绝存储（del 不校验，否则删非提醒线值会被误拦）
        if atline_list and atline_op != "del":
            valid = set(thresholds) | set(w.get("vp_thresholds") or [])
            bad = sorted({t for t in atline_list if t not in valid})
            if bad:
                cur = (" > ".join(str(t) for t in sorted(valid, reverse=True))
                       if valid else "未设置")
                return (f"❌ {'、'.join(str(t) for t in bad)} 不在提醒线中（当前 {cur}）\n"
                        f"   请先用 /em vp 添加该线，或 /em vp atline off 清除\n\n"
                        f"{VP_USAGE}")

        msgs = []
        if clear_th:
            w.pop("vp_thresholds", None)
            w.pop("vp_at_lines", None)   # 阈值没了，@ 标记随之失效
            w["vp_last"] = None          # 重置基线，避免下次加回阈值时误报
            thresholds = []
            msgs.append("✅ 已清除 VP 阈值")
        if clear_at:
            w.pop("vp_at", None)
            at_list = []
            at_op = None
            msgs.append("✅ 已清空 @ 名单")
        if clear_atlines:
            w.pop("vp_at_lines", None)
            atline_list = []
            atline_op = None
            msgs.append("✅ 已清除 @ 触发线（默认不 @）")
        if clear_dnd:
            w.pop("vp_dnd_start", None)
            w.pop("vp_dnd_end", None)
            dnd_start = dnd_end = None
            msgs.append("✅ 已关闭免打扰")

        if thresholds:
            uniq = []
            for t in sorted(thresholds, reverse=True):
                if t not in uniq:
                    uniq.append(t)
            w["vp_thresholds"] = uniq
            w.setdefault("vp_last")
            msgs.append("✅ VP 多级提醒已开启")
            msgs.extend(f"  • 降至 {t} 票时提醒" for t in uniq)

        # @ 名单：add / del / reset
        if at_op:
            cur = list(w.get("vp_at") or [])
            if at_op == "add":
                added = [q for q in at_list if q not in cur]
                cur += added
                w["vp_at"] = cur
                msgs.append(f"✅ 已添加 @ 名单: {' '.join(map(str, added))}" if added
                            else "⚠ 这些 QQ 已在 @ 名单中。")
            elif at_op == "del":
                removed = [q for q in at_list if q in cur]
                cur = [q for q in cur if q not in at_list]
                if cur:
                    w["vp_at"] = cur
                else:
                    w.pop("vp_at", None)
                msgs.append(f"✅ 已移除 @ 名单: {' '.join(map(str, removed))}" if removed
                            else "⚠ 这些 QQ 不在 @ 名单中。")
            else:  # reset
                uniq = []
                for q in at_list:
                    if q not in uniq:
                        uniq.append(q)
                w["vp_at"] = uniq
                msgs.append("✅ @ 名单: " + " ".join(str(q) for q in uniq))

        # @ 触发线：add / del / reset
        if atline_op:
            cur = list(w.get("vp_at_lines") or [])
            if atline_op == "add":
                added = [t for t in atline_list if t not in cur]
                cur += added
                cur.sort(reverse=True)
                w["vp_at_lines"] = cur
                msgs.append(f"✅ 已添加 @ 触发线: {' > '.join(map(str, sorted(added, reverse=True)))}" if added
                            else "⚠ 这些提醒线已在 @ 触发线中。")
            elif atline_op == "del":
                removed = [t for t in atline_list if t in cur]
                cur = [t for t in cur if t not in atline_list]
                if cur:
                    w["vp_at_lines"] = cur
                else:
                    w.pop("vp_at_lines", None)
                msgs.append(f"✅ 已移除 @ 触发线: {' > '.join(map(str, sorted(removed, reverse=True)))}" if removed
                            else "⚠ 这些提醒线不在 @ 触发线中。")
            else:  # reset
                uniq = []
                for t in sorted(atline_list, reverse=True):
                    if t not in uniq:
                        uniq.append(t)
                w["vp_at_lines"] = uniq
                msgs.append("✅ @ 触发线: " + " > ".join(str(t) for t in uniq))

        if dnd_start is not None:
            w["vp_dnd_start"] = dnd_start
            w["vp_dnd_end"] = dnd_end
            msgs.append(f"✅ 免打扰: {dnd_start} - {dnd_end} (UTC+8)")

        self.watch.save_config(config)
        self.watch.ensure_running()

        if not msgs:
            return self._vp_status_text(group_key)

        return ("\n".join(msgs) +
                f"\n━━━━━━━━━━━━━━━━\n"
                f"查看: /em vp status")

    def _vp_status_text(self, group_key: str) -> str:
        config = self.watch.load_config()
        w = config.get(group_key)
        if not w:
            return ("📊 VP 提醒: 未开启\n━━━━━━━━━━━━━━━━\n"
                    "开启: /em vp <票数> ...\n"
                    "例如: /em vp 500 200 100")

        lines = []
        th = w.get("vp_thresholds")
        if th:
            lines.append("🎯 VP 提醒线: " +
                         " > ".join(str(t) for t in sorted(th, reverse=True)))
        else:
            lines.append("🎯 VP 提醒: 未设置")

        at = w.get("vp_at")
        if at:
            lines.append("📣 @ 名单: " + " ".join(str(q) for q in at))
        else:
            lines.append("📣 @ 名单: 未设置（仅纯文本）")

        at_lines = w.get("vp_at_lines")
        if at_lines:
            lines.append("🎯 @ 触发线: " +
                         " > ".join(str(t) for t in sorted(at_lines, reverse=True)))
        else:
            lines.append("🎯 @ 触发线: 未设置（默认不 @）")

        ds, de = w.get("vp_dnd_start"), w.get("vp_dnd_end")
        if ds and de:
            lines.append(f"🌙 免打扰: {ds} - {de} (UTC+8)")
        else:
            lines.append("🌙 免打扰: 未设置")

        now = current_cn_minutes()
        cur = f"{now // 60:02d}:{now % 60:02d}"
        lines.append(f"🕐 当前(UTC+8): {cur}  →  "
                     + ("免打扰中（不 @）" if in_dnd(w) else "正常提醒"))

        return ("📊 VP 提醒设置\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
                + "\n━━━━━━━━━━━━━━━━")
