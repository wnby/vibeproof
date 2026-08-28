"""锁定包之间的单向依赖，避免后续开发重新退化为平铺耦合。"""

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "vibeproof"

ALLOWED_DEPENDENCIES = {
    "agents": {"agents", "core", "llm", "repository"},
    "core": {"core"},
    "interfaces": {"agents", "config", "core", "interfaces", "llm", "reports", "repository", "runtime", "workflows"},
    "llm": {"config", "llm"},
    "reports": {"core", "reports"},
    "repository": {"core", "repository"},
    "runtime": {"core", "repository", "runtime"},
    "workflows": {"agents", "core", "llm", "repository", "runtime", "workflows"},
}


def test_package_dependencies_follow_architecture_layers() -> None:
    violations: list[str] = []
    for source in PACKAGE_ROOT.rglob("*.py"):
        relative = source.relative_to(PACKAGE_ROOT)
        if len(relative.parts) < 2 or relative.parts[0] not in ALLOWED_DEPENDENCIES:
            continue
        source_layer = relative.parts[0]
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            module = _vibeproof_module(node)
            if not module or "." not in module:
                continue
            target_layer = module.split(".", 2)[1]
            if target_layer in ALLOWED_DEPENDENCIES and target_layer not in ALLOWED_DEPENDENCIES[source_layer]:
                violations.append(f"{relative.as_posix()} -> {target_layer}")

    assert not violations, "invalid package dependencies:\n" + "\n".join(sorted(set(violations)))


def test_public_symbols_have_navigation_docstrings() -> None:
    """公开入口必须说明职责，避免目录整齐但源码仍然无法接管。"""
    missing: list[str] = []
    for source in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in source.parts:
            continue
        relative = source.relative_to(PACKAGE_ROOT)
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(relative))
        for node in tree.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("_") and ast.get_docstring(node) is None:
                missing.append(f"{relative.as_posix()}:{node.lineno} {node.name}")
            if isinstance(node, ast.ClassDef):
                for method in node.body:
                    if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if not method.name.startswith("_") and ast.get_docstring(method) is None:
                        missing.append(f"{relative.as_posix()}:{method.lineno} {node.name}.{method.name}")

    assert not missing, "public symbols without docstrings:\n" + "\n".join(sorted(missing))


def _vibeproof_module(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom):
        return node.module
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("vibeproof"):
                return alias.name
    return None
