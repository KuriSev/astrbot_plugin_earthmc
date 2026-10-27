"""WebAPIMixin：从 main.py 拆出的命令实现。"""
from __future__ import annotations

import os

from .core import store
from .features.watch import parse_cn_time

class WebAPIMixin:
    async def _api_configs_list(self):
        from astrbot.api.web import json_response
        import json
        seen = set()
        result = []
        d = store.configs_dir()
        # 1. 已有显式配置文件
        if os.path.exists(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        result.append(cfg)
                        seen.add(cfg["id"])
                    except Exception:
                        pass
        # 2. 自动发现：所有对话过的群/私聊
        spath = store.seen_path()
        if os.path.exists(spath):
            try:
                with open(spath, "r", encoding="utf-8") as f:
                    seen_ids = json.load(f)
                for uid, ctype in seen_ids.items():
                    if uid not in seen:
                        result.append({
                            "id": uid, "type": ctype,
                            "features": {"watch": True, "market": True,
                                         "map": True, "scanner": True, "commands": True}
                        })
                        seen.add(uid)
            except Exception:
                pass
        # 3. 从 watch 配置兜底
        watch = self.watch.load_config()
        for gid in watch:
            if gid not in seen:
                result.append({
                    "id": gid, "type": "group",
                    "features": {"watch": True, "market": True,
                                 "map": True, "scanner": True, "commands": True}
                })
                seen.add(gid)
        return json_response(result)

    async def _api_configs_get(self):
        from astrbot.api.web import json_response, error_response, request
        uid = request.query.get("id", "").strip()
        if not uid:
            return error_response("missing id", status_code=400)
        return json_response(store.load_feature_config(uid))

    async def _api_configs_save(self):
        from astrbot.api.web import json_response, error_response, request
        import json
        payload = await request.json(default={})
        uid = str(payload.get("id", "")).strip()
        ctype = payload.get("type", "group").strip()
        features = payload.get("features", {})
        if not uid:
            return error_response("missing id", status_code=400)
        if not uid.isdigit():
            return error_response("ID 必须为数字（QQ群号或QQ号）", status_code=400)
        prefix = "friend" if ctype == "friend" else "group"
        path = os.path.join(store.configs_dir(), f"{prefix}_{uid}.json")
        data = {"id": uid, "type": ctype, "features": features}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return json_response({"saved": True})

    async def _api_configs_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        uid = str(payload.get("id", "")).strip()
        if not uid:
            return error_response("missing id", status_code=400)
        for prefix in ("group", "friend"):
            path = os.path.join(store.configs_dir(), f"{prefix}_{uid}.json")
            if os.path.exists(path):
                os.remove(path)
        return json_response({"deleted": True})

    async def _api_watch_groups(self):
        from astrbot.api.web import json_response
        return json_response(list(self.watch.load_config().keys()))

    def _vp_payload(gid: str, w: dict | None) -> dict:
        """VP 配置的对外返回体。"""
        if not w:
            return {"group_id": gid, "empty": True,
                    "vp_thresholds": [], "vp_at": [], "vp_at_lines": [],
                    "vp_dnd_start": "", "vp_dnd_end": ""}
        return {
            "group_id": gid,
            "empty": False,
            "vp_thresholds": w.get("vp_thresholds", []),
            "vp_at": w.get("vp_at", []),
            "vp_at_lines": w.get("vp_at_lines", []),
            "vp_dnd_start": w.get("vp_dnd_start", ""),
            "vp_dnd_end": w.get("vp_dnd_end", ""),
        }

    async def _api_vp_status(self):
        from astrbot.api.web import json_response, error_response, request
        gid = request.query.get("group_id", "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        return json_response(self._vp_payload(gid, self.watch.load_config().get(gid)))

    async def _api_watch_status(self):
        from astrbot.api.web import json_response, error_response, request
        gid = request.query.get("group_id", "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w:
            return json_response({"group_id": gid, "empty": True})
        resp = self._vp_payload(gid, w)      # 兼容：保留 vp 字段供旧缓存前端使用
        resp.update({
            "empty": False,
            "players": {k: v.get("online", False)
                        for k, v in (w.get("players") or {}).items()},
            "towns": {k: {
                "resident_count": v.get("resident_count", "?"),
                "blocks": v.get("blocks", "?"),
                "maxBlocks": v.get("maxBlocks", "?"),
            } for k, v in (w.get("towns") or {}).items()},
        })
        return json_response(resp)

    def _build_umo(gid: str, ctype: str = "group") -> str:
        """按固定格式拼接 umo：qq-bot:GroupMessage:{群号} / qq-bot:FriendMessage:{QQ号}"""
        kind = "FriendMessage" if ctype == "friend" else "GroupMessage"
        return f"qq-bot:{kind}:{gid}"

    def _ensure_watch_umo(cls, config: dict, gid: str, ctype: str = "group"):
        """群配置缺 umo 时按格式补全。"""
        w = config.setdefault(gid, {})
        if not w.get("umo"):
            w["umo"] = cls._build_umo(gid, ctype)

    async def _api_vp_save(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        thresholds = payload.get("thresholds", [])
        at = payload.get("at")                    # list | None（不传则不改动）
        at_lines = payload.get("at_lines")        # list | None（不传则不改动）
        dnd_start = (payload.get("dnd_start") or "").strip()
        dnd_end = (payload.get("dnd_end") or "").strip()
        if not gid:
            return error_response("missing group_id", status_code=400)

        th = [int(t) for t in thresholds if str(t).isdigit() and int(t) > 0]
        th.sort(reverse=True)

        if dnd_start and dnd_end:
            if parse_cn_time(dnd_start) is None or parse_cn_time(dnd_end) is None:
                return error_response("免打扰时间格式无效（需 HH:MM）", status_code=400)

        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        w = config[gid]
        w["vp_thresholds"] = th
        if not th:
            w["vp_last"] = None                    # 与命令行为一致，防误报

        if at is not None:
            uniq, seen = [], set()
            for a in at:
                if str(a).isdigit() and int(a) not in seen:
                    seen.add(int(a))
                    uniq.append(int(a))
            if uniq:
                w["vp_at"] = uniq
            else:
                w.pop("vp_at", None)

        if at_lines is not None:
            uniq, seen = [], set()
            for a in at_lines:
                v = int(a) if str(a).isdigit() else None
                if v is not None and v in th and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            if uniq:
                w["vp_at_lines"] = uniq
            else:
                w.pop("vp_at_lines", None)

        if dnd_start and dnd_end:
            w["vp_dnd_start"], w["vp_dnd_end"] = dnd_start, dnd_end
        else:
            w.pop("vp_dnd_start", None)
            w.pop("vp_dnd_end", None)

        self.watch.save_config(config)
        self.watch.ensure_running()
        return json_response({
            "saved": True,
            "thresholds": th,
            "at": w.get("vp_at", []),
            "at_lines": w.get("vp_at_lines", []),
            "dnd_start": w.get("vp_dnd_start", ""),
            "dnd_end": w.get("vp_dnd_end", ""),
        })

    async def _api_watch_player_add(self):
        from astrbot.api.web import json_response, error_response, request
        from .core.api import post as api_post
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        # 校验玩家存在
        data = await api_post("/players", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return error_response("玩家不存在", status_code=400)
        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        players = config[gid].setdefault("players", {})
        if name.lower() not in {k.lower() for k in players}:
            cname = data[0].get("name") or name      # 落服务端规范大小写
            players[cname] = {"online": False,
                              "town": (data[0].get("town") or {}).get("name", "")}
            self.watch.save_config(config)
            self.watch.ensure_running()
            return json_response({"added": True, "name": name})
        return json_response({"added": False, "name": name})

    async def _api_watch_player_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        config = self.watch.load_config()
        players = (config.get(gid) or {}).get("players", {})
        removed = [k for k in players if k.lower() == name.lower()]
        for k in removed:
            del players[k]
        if removed:
            self.watch.save_config(config)
        return json_response({"deleted": len(removed) > 0})

    async def _api_watch_town_add(self):
        from astrbot.api.web import json_response, error_response, request
        from .core.api import post as api_post
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        ctype = payload.get("type", "group")
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        # 校验城镇存在并拉取初始状态
        data = await api_post("/towns", {"query": [name]})
        if not data or not isinstance(data, list) or len(data) == 0:
            return error_response("城镇不存在", status_code=400)
        t = data[0]
        stats = t.get("stats") or {}
        cur_names = sorted(r.get("name", "") for r in (t.get("residents") or []))
        config = self.watch.load_config()
        self._ensure_watch_umo(config, gid, ctype)
        towns = config[gid].setdefault("towns", {})
        if name.lower() not in {k.lower() for k in towns}:
            towns[t.get("name", name)] = {
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
            self.watch.save_config(config)
            self.watch.ensure_running()
            return json_response({"added": True, "name": t.get("name", name)})
        return json_response({"added": False, "name": name})

    async def _api_watch_town_del(self):
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        name = (payload.get("name", "") or "").strip()
        if not gid or not name:
            return error_response("missing group_id or name", status_code=400)
        config = self.watch.load_config()
        towns = (config.get(gid) or {}).get("towns", {})
        removed = [k for k in towns if k.lower() == name.lower()]
        for k in removed:
            del towns[k]
        if removed:
            self.watch.save_config(config)
        return json_response({"deleted": len(removed) > 0})

    async def _api_watch_off(self):
        """关闭该群的玩家/城镇监控（不动 VP 提醒设置）。"""
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w:
            return json_response({"closed": False})
        changed = False
        for key in ("players", "towns"):
            if key in w:
                del w[key]
                changed = True
        if changed:
            self.watch.save_config(config)
        return json_response({"closed": changed})

    async def _api_vp_off(self):
        """清除 VP 提醒线（与 /em vp off 一致）：清阈值+@触发线，保留 @名单与免打扰。"""
        from astrbot.api.web import json_response, error_response, request
        payload = await request.json(default={})
        gid = str(payload.get("group_id", "")).strip()
        if not gid:
            return error_response("missing group_id", status_code=400)
        config = self.watch.load_config()
        w = config.get(gid)
        if not w or ("vp_thresholds" not in w and "vp_at_lines" not in w):
            return json_response({"closed": False})
        w.pop("vp_thresholds", None)
        w.pop("vp_at_lines", None)
        w["vp_last"] = None          # 重置基线，避免下次加回阈值时误报
        self.watch.save_config(config)
        return json_response({"closed": True})
