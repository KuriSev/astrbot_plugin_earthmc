"""废墟关注列表：国家/城镇关注（uuid 为键）、每小时刷新快照、每天定时推送。"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

from astrbot.api import logger
from astrbot.api.event import MessageChain

from ..core.api import post, post_chunked
from ..core.utils import is_uuid
from .risk import analyze_ruins, fmt_cn

RUINS_WATCH_FILE = "earthmc_ruins_watch.json"
_DAY_MS = 86400000
_TZ_CN = timezone(timedelta(hours=8))
# 允许的推送窗口（秒）：覆盖 tick 抖动，但不构成"补发"
_PUSH_GRACE_SECONDS = 120


def parse_alert_window(raw, default: int = 7) -> int:
    """把 7 / "7" / "7,3,1,0" 统一解析为单个天数。"""
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return max(0, raw)
    for part in str(raw or "").replace("，", ",").split(","):
        try:
            return max(0, int(part.strip()))
        except (TypeError, ValueError):
            continue
    return default


class RuinsWatchManager:
    """读写 plugin_data/<plugin>/earthmc_ruins_watch.json。"""

    def __init__(self, plugin_name: str):
        self._plugin_name = plugin_name
        self._data_dir = ""

    @property
    def data_dir(self) -> str:
        if not self._data_dir:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            self._data_dir = os.path.join(
                str(get_astrbot_data_path()), "plugin_data", self._plugin_name)
            os.makedirs(self._data_dir, exist_ok=True)
        return self._data_dir

    @property
    def config_path(self) -> str:
        return os.path.join(self.data_dir, RUINS_WATCH_FILE)

    def load(self) -> dict:
        path = self.config_path
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EarthMC] 读取废墟关注列表失败: {e}")
            return {}

    def save(self, cfg: dict) -> None:
        path = self.config_path
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EarthMC] 保存废墟关注列表失败: {e}")

    # ── 分组 ──────────────────────────

    @staticmethod
    def group(cfg: dict, gid: str) -> dict:
        g = cfg.setdefault(str(gid), {})
        g.setdefault("nations", {})      # uuid → 显示名
        g.setdefault("towns", {})        # uuid → 显示名
        g.setdefault("state", {})        # uuid → 快照
        return g

    @staticmethod
    def prune(g: dict) -> None:
        """删掉不再被任何关注条目覆盖的 state。"""
        raw_nations = g.get("nations") or {}
        nations = ({str(v).lower() for v in raw_nations.values()}
                   if isinstance(raw_nations, dict)
                   else {str(n).lower() for n in raw_nations})
        towns = g.get("towns") or {}
        if isinstance(towns, dict):
            uuids = set(towns)
            names = {str(v).lower() for v in towns.values()}
        else:  # 迁移期旧格式
            uuids = set()
            names = {str(t).lower() for t in towns}
        for key in list(g.get("state") or {}):
            st = g["state"][key]
            if (key in uuids or (st.get("name") or "").lower() in names
                    or (st.get("nation") or "").lower() in nations):
                continue
            g["state"].pop(key, None)

    # ── 关注操作 ──────────────────────

    def add_nation(self, gid: str, uid: str, name: str, umo: str = "") -> tuple[bool, str]:
        if not uid or not name:
            return False, "❌ 用法: /em risk nation add <国家名>"
        cfg = self.load()
        g = self.group(cfg, gid)
        if umo:
            g["umo"] = umo
        nations = g.get("nations")
        if isinstance(nations, list):        # 迁移期：list[str] → dict
            nations = {n: n for n in nations}
            g["nations"] = nations
        nations = g.setdefault("nations", {})
        if uid in nations or any(str(v).lower() == name.lower() for v in nations.values()):
            return False, f"⚠ {name} 已在关注列表中。"
        nations[uid] = name
        self.save(cfg)
        return True, name

    def add_town(self, gid: str, uid: str, name: str, umo: str = "") -> tuple[bool, str]:
        if not uid or not name:
            return False, "❌ 用法: /em risk town add <城镇名>"
        cfg = self.load()
        g = self.group(cfg, gid)
        if umo:
            g["umo"] = umo
        towns = g.get("towns")
        if isinstance(towns, list):          # 迁移期：list[str] → dict
            towns = {t: t for t in towns}
            g["towns"] = towns
        towns = g.setdefault("towns", {})
        if uid in towns or any(str(v).lower() == name.lower() for v in towns.values()):
            return False, f"⚠ {name} 已在关注列表中。"
        towns[uid] = name
        self.save(cfg)
        return True, name

    def del_nation(self, gid: str, target: str) -> tuple[bool, str]:
        target = (target or "").strip()
        if not target:
            return False, "❌ 用法: /em risk nation del <国家名>"
        cfg = self.load()
        g = self.group(cfg, gid)
        nations = g.get("nations") or {}
        tl = target.lower()
        if isinstance(nations, list):        # 迁移期旧格式
            remain = [n for n in nations if str(n).lower() != tl]
            if len(remain) == len(nations):
                return False, f"⚠ {target} 不在关注列表中。"
            g["nations"] = remain
            removed = target
        else:
            hit = None
            for uid, name in nations.items():
                if uid.lower() == tl or str(name).lower() == tl:
                    hit = uid
                    break
            if not hit:
                return False, f"⚠ {target} 不在关注列表中。"
            removed = nations.pop(hit)
        self.prune(g)
        self.save(cfg)
        return True, removed

    def del_town(self, gid: str, target: str) -> tuple[bool, str]:
        target = (target or "").strip()
        if not target:
            return False, "❌ 用法: /em risk town del <城镇名>"
        cfg = self.load()
        g = self.group(cfg, gid)
        towns = g.get("towns") or {}
        tl = target.lower()

        if isinstance(towns, list):          # 迁移期旧格式
            remain = [t for t in towns if str(t).lower() != tl]
            if len(remain) == len(towns):
                return False, f"⚠ {target} 不在关注列表中。"
            g["towns"] = remain
            removed = target
        else:
            hit = None
            for uid, name in towns.items():
                if uid.lower() == tl or str(name).lower() == tl:
                    hit = uid
                    break
            if not hit:
                return False, f"⚠ {target} 不在关注列表中。"
            removed = towns.pop(hit)

        self.prune(g)
        self.save(cfg)
        return True, removed

    def lists(self, gid: str) -> tuple[list[str], list[str]]:
        g = self.load().get(str(gid), {})
        towns = g.get("towns") or {}
        values = list(towns.values()) if isinstance(towns, dict) else list(towns)
        nations = g.get("nations") or {}
        nation_names = (list(nations.values()) if isinstance(nations, dict)
                        else [str(n) for n in nations])
        return [str(n) for n in nation_names], [str(v) for v in values]


class RuinsChecker:
    """每 60 秒 tick：按小时刷新快照，按配置时刻每天推送一次。"""

    def __init__(self, send_message, manager: RuinsWatchManager,
                 alert_days: int = 7, push_hour: int = 18, push_minute: int = 0,
                 refresh_interval: float = 3600, tick_seconds: float = 60):
        self._send = send_message
        self.manager = manager
        self.alert_days = parse_alert_window(alert_days)
        self.push_hour = max(0, min(int(push_hour), 23))
        self.push_minute = max(0, min(int(push_minute), 59))
        self.refresh_interval = refresh_interval
        self.tick_seconds = tick_seconds
        self._last_refresh = 0
        self._task: asyncio.Task | None = None

    # ── 生命周期 ──────────────────────

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"[EarthMC] 废墟关注检查失败: {e}")
            await asyncio.sleep(self.tick_seconds)

    # ── 主循环 ────────────────────────

    async def tick(self, now_ms: int | None = None) -> int:
        """执行一次 tick，返回推送条数。now_ms 可注入便于测试。"""
        now = now_ms if now_ms is not None else _now_ms()
        cfg = self.manager.load()
        if not any(g.get("nations") or g.get("towns") for g in cfg.values()):
            return 0

        dirty = False
        if now - self._last_refresh >= self.refresh_interval * 1000:
            cfg, _ = await self.refresh(now)
            self._last_refresh = now
            dirty = True

        cn = datetime.fromtimestamp(now / 1000, tz=_TZ_CN)
        today = cn.strftime("%Y-%m-%d")
        sched = self.push_hour * 3600 + self.push_minute * 60
        sec = cn.hour * 3600 + cn.minute * 60 + cn.second

        pushed = 0
        if sched <= sec < sched + _PUSH_GRACE_SECONDS:
            # 推送前强制刷新：保证推送内容与推送时刻一致，而不是用最多 1 小时前的快照
            cfg, _ = await self.refresh(now)
            self._last_refresh = now
            dirty = True
            for gid, g in cfg.items():
                if not (g.get("nations") or g.get("towns")):
                    continue
                if g.get("last_push_date") == today:
                    continue
                text = self._digest(g, now)
                if text:
                    await self._push(self._umo(gid, g), text)
                    pushed += 1
                g["last_push_date"] = today
                dirty = True

        if dirty:
            self.manager.save(cfg)
        return pushed

    # ── 刷新 ──────────────────────────

    async def refresh(self, now_ms: int | None = None) -> tuple[dict, dict]:
        """拉取关注国家/城镇并更新快照；返回 (cfg, found)。"""
        now = now_ms if now_ms is not None else _now_ms()
        cfg = self.manager.load()
        groups = {gid: g for gid, g in cfg.items()
                  if g.get("nations") or g.get("towns")}
        if not groups:
            return cfg, {"nations": set(), "towns": set()}

        # 国家：已迁移用 uuid，旧格式用名字
        explicit_nation_uuids: set[str] = set()
        legacy_nations: set[str] = set()
        for g in groups.values():
            nations = g.get("nations") or {}
            if isinstance(nations, list):
                legacy_nations.update(str(n) for n in nations)
                continue
            for uid, name in nations.items():
                if is_uuid(uid):
                    explicit_nation_uuids.add(uid)
                else:
                    legacy_nations.add(str(name or uid))

        nation_query = (sorted(explicit_nation_uuids)
                        + sorted(legacy_nations, key=str.lower))
        n_by_uuid: dict[str, dict] = {}
        n_by_name: dict[str, dict] = {}
        if nation_query:
            ndata = await post_chunked("/nations", nation_query)
            n_by_uuid = {n["uuid"]: n for n in ndata if n.get("uuid")}
            n_by_name = {n["name"].lower(): n for n in ndata if n.get("name")}

        # 迁移每个群的 nations → {uuid: name}
        for g in groups.values():
            nations = g.get("nations")
            new: dict[str, str] = {}
            if isinstance(nations, list):
                for n in nations:
                    nd = n_by_name.get(str(n).lower())
                    if nd and nd.get("uuid"):
                        new[nd["uuid"]] = nd["name"]
            elif isinstance(nations, dict):
                for key, val in nations.items():
                    if is_uuid(key):
                        nd = n_by_uuid.get(key)
                        new[key] = (nd.get("name") if nd else None) or str(val)
                    else:
                        nd = (n_by_name.get(str(val).lower())
                              or n_by_name.get(str(key).lower()))
                        if nd and nd.get("uuid"):
                            new[nd["uuid"]] = nd["name"]
            g["nations"] = new

        nation_towns: dict[str, list[str]] = {
            uid: [t.get("name") for t in (n.get("towns") or []) if t.get("name")]
            for uid, n in n_by_uuid.items()
        }

        # 显式城镇：已迁移用 uuid，旧格式用名字
        explicit_uuids: set[str] = set()
        legacy_names: set[str] = set()
        for g in groups.values():
            towns = g.get("towns") or {}
            if isinstance(towns, list):
                legacy_names.update(str(t) for t in towns)
                continue
            for uid, name in towns.items():
                if is_uuid(uid):
                    explicit_uuids.add(uid)
                else:
                    legacy_names.add(str(name or uid))

        all_nation_towns = {t for ts in nation_towns.values() for t in ts}
        query = sorted(explicit_uuids) + sorted(
            legacy_names | all_nation_towns, key=str.lower)
        tdata = await post_chunked("/towns", query)
        t_by_uuid = {t["uuid"]: t for t in tdata if t.get("uuid")}
        t_by_name = {t["name"].lower(): t for t in tdata if t.get("name")}

        # 迁移每个群的 towns → {uuid: name}
        for g in groups.values():
            towns = g.get("towns")
            new: dict[str, str] = {}
            if isinstance(towns, list):
                for n in towns:
                    td = t_by_name.get(str(n).lower())
                    if td and td.get("uuid"):
                        new[td["uuid"]] = td["name"]
            elif isinstance(towns, dict):
                for key, val in towns.items():
                    if is_uuid(key):
                        td = t_by_uuid.get(key)
                        new[key] = (td.get("name") if td else None) or str(val)
                    else:
                        td = (t_by_name.get(str(val).lower())
                              or t_by_name.get(str(key).lower()))
                        if td and td.get("uuid"):
                            new[td["uuid"]] = td["name"]
            g["towns"] = new

        # 覆盖集合：显式 uuid + 国家下属城镇
        coverage: dict[str, set[str]] = {}
        for gid, g in groups.items():
            cov = set(g["towns"].keys())
            for nation_uid in g["nations"]:
                for tname in nation_towns.get(nation_uid, []):
                    td = t_by_name.get(tname.lower())
                    if td and td.get("uuid"):
                        cov.add(td["uuid"])
            coverage[gid] = cov

        residents: set[str] = set()
        for uid in {u for c in coverage.values() for u in c}:
            for r in (t_by_uuid.get(uid) or {}).get("residents") or []:
                if r.get("name"):
                    residents.add(r["name"])
        p_map = await self._fetch("/players", sorted(residents, key=str.lower))

        estimates = {uid: analyze_ruins(td, p_map, now)
                     for uid, td in t_by_uuid.items()}

        for gid, g in groups.items():
            state: dict[str, dict] = {}
            for uid in coverage[gid]:
                e = estimates.get(uid)
                if not e:
                    continue
                state[uid] = {
                    "name": e.town, "nation": e.nation, "mayor": e.mayor_name,
                    "is_open": e.is_open, "ruined": e.ruined, "missing": e.missing,
                    "mayor_unknown": e.mayor_unknown,
                    "ruins_at": e.ruins_at, "mayor_event_at": e.mayor_event_at,
                    "updated_at": now,
                }
            g["state"] = state
            g["updated_at"] = now

        self.manager.save(cfg)
        return cfg, {"nations": set(n_by_uuid), "towns": set(t_by_uuid)}

    async def _fetch(self, path: str, names: list[str]) -> dict[str, dict]:
        return {t["name"].lower(): t for t in await post_chunked(path, names)
                if t.get("name")}

    # ── 渲染 ──────────────────────────

    def status_text(self, gid: str, now_ms: int | None = None) -> str:
        now = now_ms if now_ms is not None else _now_ms()
        g = self.manager.load().get(str(gid), {})
        raw_nations = g.get("nations") or {}
        nations = (list(raw_nations.values()) if isinstance(raw_nations, dict)
                   else [str(n) for n in raw_nations])
        towns = g.get("towns") or {}
        town_names = (list(towns.values()) if isinstance(towns, dict) else list(towns))
        if not nations and not town_names:
            return ("📋 废墟关注列表为空\n"
                    "添加国家: /em risk nation add <国家>\n"
                    "添加城镇: /em risk town add <城镇>")

        lines = [f"📋 废墟关注 · 每天 {self.push_hour:02d}:{self.push_minute:02d} 推送"
                 f"（窗口 {self.alert_days} 天）",
                 f"数据更新 {fmt_cn(g.get('updated_at'))}"]
        if nations:
            lines.append("国家：" + "、".join(nations))
        if town_names:
            lines.append("城镇：" + "、".join(str(t) for t in town_names))

        items = self._window_items(g, now)
        if not items:
            lines.append("窗口内暂无城镇")
            return "\n".join(lines)

        current = None
        for ev, st in items:
            if st.get("nation") != current:
                current = st.get("nation")
                lines.append(current or "未知国家")
            lines.append(self._line(st, now))
        return "\n".join(lines)

    async def live_status(self, gid: str, now_ms: int | None = None) -> str:
        """裸 /em risk：实时拉取关注范围的最新数据后渲染（只读，不写回快照）。"""
        now = now_ms if now_ms is not None else _now_ms()
        g = self.manager.load().get(str(gid), {})
        raw_nations = g.get("nations") or {}
        nations = (list(raw_nations.values()) if isinstance(raw_nations, dict)
                   else [str(n) for n in raw_nations])
        towns = g.get("towns") or {}
        town_names = (list(towns.values()) if isinstance(towns, dict) else list(towns))
        if not nations and not town_names:
            return ("📋 废墟关注列表为空\n"
                    "添加国家: /em risk nation add <国家>\n"
                    "添加城镇: /em risk town add <城镇>")

        if not (g.get("state") or {}):
            # 还没有任何快照（首次使用/被清空）：退回一次完整刷新
            cfg, _ = await self.refresh(now)
            self._last_refresh = now
            g = cfg.get(str(gid), g)

        state, stale = await self._live_state(g, now)
        lines = [f"📋 废墟关注 · 每天 {self.push_hour:02d}:{self.push_minute:02d} 推送"
                 f"（窗口 {self.alert_days} 天）",
                 f"实时数据 · {fmt_cn(now)}"
                 + (f"（{stale} 个城镇沿用上次快照）" if stale else "")]
        if nations:
            lines.append("国家：" + "、".join(nations))
        if town_names:
            lines.append("城镇：" + "、".join(str(t) for t in town_names))

        items = self._window_items({"state": state}, now)
        if not items:
            lines.append("窗口内暂无城镇")
            return "\n".join(lines)

        current = None
        for ev, st in items:
            if st.get("nation") != current:
                current = st.get("nation")
                lines.append(current or "未知国家")
            lines.append(self._line(st, now))
        return "\n".join(lines)

    async def _live_state(self, g: dict, now: int) -> tuple[dict[str, dict], int]:
        """按快照里的城镇 uuid 实时重算；返回 (state, 沿用快照的条数)。"""
        snap = g.get("state") or {}
        keys = [k for k in snap if is_uuid(k)]
        if not keys:
            return {}, 0

        t_by_uuid = await self._fetch_towns(keys)
        residents = {r["name"] for t in t_by_uuid.values()
                     for r in (t.get("residents") or []) if r.get("name")}
        p_map = await self._fetch("/players", sorted(residents, key=str.lower))

        out: dict[str, dict] = {}
        for uid, td in t_by_uuid.items():
            e = analyze_ruins(td, p_map, now)
            if not e:
                continue
            out[uid] = {
                "name": e.town, "nation": e.nation, "mayor": e.mayor_name,
                "is_open": e.is_open, "ruined": e.ruined, "missing": e.missing,
                "mayor_unknown": e.mayor_unknown,
                "ruins_at": e.ruins_at, "mayor_event_at": e.mayor_event_at,
                "updated_at": now,
            }

        # 网络抖动时 post 会返回 None，这一批城镇就查不到；用上次快照兜底，
        # 避免卡片因为一次请求超时少掉几十个城镇。
        stale = 0
        for uid in keys:
            if uid in out:
                continue
            st = snap.get(uid)
            if st:
                out[uid] = st
                stale += 1
        return out, stale

    async def _fetch_towns(self, keys: list[str]) -> dict[str, dict]:
        """按 uuid 批量查城镇；对漏掉的再重试一轮（API 偶发超时）。"""
        got: dict[str, dict] = {}
        todo = list(keys)
        for attempt in (0, 1):
            if not todo:
                break
            if attempt:
                await asyncio.sleep(0.5)
            for t in await post_chunked("/towns", todo, batch=100):
                if t.get("uuid"):
                    got[t["uuid"]] = t
            todo = [k for k in todo if k not in got]
        return got

    def added_text(self, gid: str, kind: str, key: str, name: str,
                   found: dict, now_ms: int | None = None) -> str:
        """新增关注后输出：该国家/城镇当前快照（不限于窗口）。"""
        now = now_ms if now_ms is not None else _now_ms()
        g = self.manager.load().get(str(gid), {})
        state = list((g.get("state") or {}).values())

        if kind == "nation":
            items = [st for st in state
                     if (st.get("nation") or "").lower() == name.lower()]
            if key not in found.get("nations", set()):
                return f"❌ 未找到国家「{name}」，未加入关注。"
            header = f"🏰 {name} 已加入关注（{len(items)} 个城镇）"
        else:
            if key not in found.get("towns", set()):
                return f"❌ 未找到城镇「{name}」，未加入关注。"
            st = (g.get("state") or {}).get(key)
            items = [st] if st else []
            header = f"🏘 {name} 已加入关注"

        if not items:
            return header + "\n暂无可用数据（可能已无居民或数据缺失）。"

        items.sort(key=lambda st: self._event_of(st) or 0)
        lines = [header]
        lines += [self._line(st, now) for st in items[:15]]
        if len(items) > 15:
            lines.append(f"  …另有 {len(items) - 15} 个城镇")
        return "\n".join(lines)

    # ── 内部 ──────────────────────────

    @staticmethod
    def _umo(gid: str, g: dict) -> str:
        return g.get("umo") or f"qq-bot:GroupMessage:{gid}"

    @staticmethod
    def _event_of(st: dict) -> int | None:
        evs = [x for x in (st.get("ruins_at"), st.get("mayor_event_at")) if x]
        return min(evs) if evs else None

    def _event_label(self, st: dict) -> tuple[int | None, str]:
        ruins = st.get("ruins_at")
        mayor = st.get("mayor_event_at")
        if mayor and (not ruins or mayor <= ruins):
            return mayor, "转让城主"
        return ruins, "变废墟"

    def _window_items(self, g: dict, now: int) -> list[tuple[int, dict]]:
        out = []
        for st in (g.get("state") or {}).values():
            ev = self._event_of(st)
            if ev is None or st.get("ruined"):
                continue
            if ev - now <= self.alert_days * _DAY_MS:
                out.append((ev, st))
        out.sort(key=lambda x: x[0])
        return out

    def _line(self, st: dict, now: int) -> str:
        ev, label = self._event_label(st)
        days = max(0, (ev - now) // _DAY_MS) if ev else 0
        tag = "（数据不可用）" if st.get("mayor_unknown") else ""
        return (f"  {st.get('name')}  {fmt_cn(ev)} {label}"
                f"（剩 {days} 天）· 城主 {st.get('mayor')}{tag}")

    def _digest(self, g: dict, now: int) -> str:
        items = self._window_items(g, now)
        if not items:
            return ""
        lines = [f"⏰ 废墟提醒（{self.alert_days} 天内）"]
        current = None
        for ev, st in items:
            if st.get("nation") != current:
                current = st.get("nation")
                lines.append(current or "未知国家")
            lines.append(self._line(st, now))
        return "\n".join(lines)

    async def _push(self, umo: str, text: str) -> None:
        try:
            await self._send(umo, MessageChain().message(text))
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EarthMC] 废墟提醒发送失败: {e}")


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
