"""验证 healthy_service 的输入规范化和问候语行为。"""

from app import greeting, normalize_name


def test_normalize_name() -> None:
    assert normalize_name("  ada   lovelace ") == "Ada Lovelace"


def test_greeting() -> None:
    assert greeting("grace hopper") == "Hello, Grace Hopper!"
