"""Architecture guards for src/kyc_copilot layer boundaries (stdlib + unittest only)."""
from __future__ import annotations

import ast
import importlib
import inspect
import sys
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def _ensure_src_on_path() -> None:
    src = str(SRC)
    if src not in sys.path:
        sys.path.insert(0, src)


_ensure_src_on_path()

FROZEN_MODELS = (
    "Source",
    "Policy",
    "Document",
    "ParsedFile",
    "ToolResult",
    "CaseEvidence",
    "Decision",
    "CaseRun",
)
INTERFACE_NAMES = ("KnowledgeStore", "Narrator", "StatutoryRule")


def _module_file(module) -> Path:
    path = getattr(module, "__file__", None)
    if path is None:
        raise AssertionError(f"{module.__name__} has no __file__ (expected a real module under src/)")
    return Path(path).resolve()


def _imported_module_names(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level and node.level > 0:
                continue  # relative imports stay inside the package
            names.add(node.module.split(".")[0])
    return names


def _is_stdlib_or_relative(top_level: str) -> bool:
    if top_level in sys.stdlib_module_names:
        return True
    if top_level == "kyc_copilot":
        return False
    return False


class TestContractsBoundaries(unittest.TestCase):
    def test_contracts_exposes_frozen_models_and_interfaces(self) -> None:
        models = importlib.import_module("kyc_copilot.contracts.models")
        interfaces = importlib.import_module("kyc_copilot.contracts.interfaces")

        for name in FROZEN_MODELS:
            with self.subTest(model=name):
                cls = getattr(models, name, None) or getattr(interfaces, name, None)
                self.assertIsNotNone(cls, f"missing frozen model {name}")
                self.assertTrue(is_dataclass(cls), f"{name} must be a dataclass")
                self.assertTrue(cls.__dataclass_params__.frozen, f"{name} must be frozen")
                # Touch fields so incomplete stubs fail loudly
                self.assertGreaterEqual(len(fields(cls)), 1, f"{name} must declare fields")

        for name in INTERFACE_NAMES:
            with self.subTest(interface=name):
                cls = getattr(interfaces, name, None)
                self.assertIsNotNone(cls, f"missing interface {name} in contracts.interfaces")
                self.assertTrue(inspect.isclass(cls), f"{name} must be a class")

        rule = interfaces.StatutoryRule
        self.assertTrue(inspect.isabstract(rule) or hasattr(rule, "__abstractmethods__"))
        self.assertTrue(hasattr(rule, "_registry"))
        self.assertTrue(hasattr(rule, "ordered_rules"))
        self.assertTrue(callable(rule.ordered_rules))

    def test_contracts_modules_import_stdlib_only(self) -> None:
        models = importlib.import_module("kyc_copilot.contracts.models")
        interfaces = importlib.import_module("kyc_copilot.contracts.interfaces")
        for module in (models, interfaces):
            with self.subTest(module=module.__name__):
                path = _module_file(module)
                self.assertTrue(
                    str(path).startswith(str(SRC.resolve())),
                    f"{module.__name__} must live under src/",
                )
                for top in _imported_module_names(path):
                    self.assertTrue(
                        _is_stdlib_or_relative(top),
                        f"{module.__name__} imports non-stdlib top-level {top!r}",
                    )
                    self.assertNotEqual(top, "kyc_copilot",
                                        f"{module.__name__} must not import other kyc_copilot layers")


if __name__ == "__main__":
    unittest.main()
