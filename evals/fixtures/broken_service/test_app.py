"""声明 broken_service 的正确预期，使固定运行检查稳定地产生失败证据。"""

from app import total_with_tax


def test_total_with_tax_adds_tax() -> None:
    assert total_with_tax(100, 0.13) == 113
