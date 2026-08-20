"""用于 Eval 的最小正常服务，提供可被测试验证的确定性业务函数。"""


def normalize_name(name: str) -> str:
    """去除首尾空白并将每个单词转换为标题格式。"""
    return " ".join(part.capitalize() for part in name.strip().split())


def greeting(name: str) -> str:
    """根据规范化后的姓名生成问候语。"""
    return f"Hello, {normalize_name(name)}!"
