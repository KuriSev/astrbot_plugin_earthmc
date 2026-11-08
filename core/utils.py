"""通用小工具。"""
import math


def is_uuid(value: str) -> bool:
    """粗略判断是否为 uuid（36 位、4 个连字符）。"""
    return isinstance(value, str) and len(value) == 36 and value.count("-") == 4


def fmt_coord(value) -> str:
    """世界坐标 → 方块坐标：向下取整（负数向 −∞，-3829.3 → -3830）。

    Minecraft 里方块坐标 = 该点坐标向下取整；API 返回的 x/y/z 是带小数的实数，
    直接展示会带一长串小数，统一在这里转成整数。
    """
    try:
        return str(math.floor(float(value)))
    except (TypeError, ValueError):
        return "?"


def fmt_coord_pair(x, z) -> str:
    """(x, z) 形式的方块坐标串。"""
    return f"({fmt_coord(x)}, {fmt_coord(z)})"
