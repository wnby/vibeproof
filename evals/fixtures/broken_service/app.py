"""用于 Eval 的已知缺陷服务，故意保留与测试预期不一致的计算逻辑。"""


def total_with_tax(subtotal: float, tax_rate: float) -> float:
    """错误地减去税额，用于验证运行失败能否被如实记录。"""
    return subtotal - subtotal * tax_rate
