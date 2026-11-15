"""插件数据落盘：功能开关配置与会话记录。"""
import json
import os

_SEEN_FILE = "seen_conversations.json"


def configs_dir() -> str:
    """按群/私聊存放功能开关的目录。"""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    d = os.path.join(
        str(get_astrbot_data_path()), "plugin_data",
        "astrbot_plugin_earthmc", "configs",
    )
    os.makedirs(d, exist_ok=True)
    return d


def seen_path() -> str:
    return os.path.join(configs_dir(), "..", _SEEN_FILE)


def record_conversation(uid: str, ctype: str) -> None:
    """自动记录所有对话过的 ID。"""
    path = seen_path()
    seen = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                seen = json.load(f)
    except Exception:
        pass
    if uid not in seen:
        seen[uid] = ctype
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(seen, f)
        os.replace(tmp, path)


def load_feature_config(uid: str) -> dict:
    """读取某 ID 的功能开关配置。"""
    uid = str(uid)
    path = os.path.join(configs_dir(), f"group_{uid}.json")
    if not os.path.exists(path):
        path = os.path.join(configs_dir(), f"friend_{uid}.json")
    if not os.path.exists(path):
        return {"features": {}}  # 默认全部开启
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"features": {}}


# 功能开关默认值：配置里没写的键按这里取值
# 扩展查询（附近城镇/坐标归属/领地/地图截图）默认关闭，需在 WebUI 插件页面手动开启
FEATURE_DEFAULTS = {
    "commands": True,
    "watch": True,
    "market": True,
    "map": False,
    "nearby": False,
    "location": False,
    "quarter": False,
}


def feature_enabled(cfg: dict, key: str) -> bool:
    return bool(cfg.get("features", {}).get(key, FEATURE_DEFAULTS.get(key, True)))
