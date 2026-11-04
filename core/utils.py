"""通用小工具。"""


def is_uuid(value: str) -> bool:
    """粗略判断是否为 uuid（36 位、4 个连字符）。"""
    return isinstance(value, str) and len(value) == 36 and value.count("-") == 4
