"""Architecture guards for src/kyc_copilot layer boundaries."""
from __future__ import annotations

import ast
import importlib
import inspect
import sys
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

from pydantic.dataclasses import is_pydantic_dataclass

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
ALLOWED_CONTRACT_THIRD_PARTY = frozenset({"pydantic"})


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
        raise AssertionError(
            f"{module.__name__} has no __file__ (expected a real module under src/)"
        )
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


def _is_allowed_contracts_import(top_level: str) -> bool:
    if top_level in sys.stdlib_module_names:
        return True
    return top_level in ALLOWED_CONTRACT_THIRD_PARTY


def _is_frozen(cls: type) -> bool:
    params = getattr(cls, "__dataclass_params__", None)
    if params is not None and getattr(params, "frozen", False):
        return True
    config = getattr(cls, "__pydantic_config__", None)
    if config is not None:
        return bool(config.get("frozen"))
    return False


class TestContractsBoundaries(unittest.TestCase):
    def test_pydantic_rejects_invalid_document_review_date(self) -> None:
        from pydantic import ValidationError

        from kyc_copilot.contracts.models import Document

        with self.assertRaises(ValidationError):
            Document("KYC-X-INTAKE", "KYC-X", "intake", True, "not-a-date", None)

    def test_contracts_exposes_frozen_models_and_interfaces(self) -> None:
        models = importlib.import_module("kyc_copilot.contracts.models")
        interfaces = importlib.import_module("kyc_copilot.contracts.interfaces")

        for name in FROZEN_MODELS:
            with self.subTest(model=name):
                cls = getattr(models, name, None) or getattr(interfaces, name, None)
                self.assertIsNotNone(cls, f"missing frozen model {name}")
                self.assertTrue(is_dataclass(cls), f"{name} must be a dataclass")
                self.assertTrue(
                    is_pydantic_dataclass(cls),
                    f"{name} must be a Pydantic dataclass (schema validation)",
                )
                self.assertTrue(_is_frozen(cls), f"{name} must be frozen")
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

    def test_contracts_modules_import_stdlib_or_pydantic_only(self) -> None:
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
                    if top == "kyc_copilot":
                        self.fail(f"{module.__name__} must not import other kyc_copilot layers")
                    self.assertTrue(
                        _is_allowed_contracts_import(top),
                        f"{module.__name__} imports disallowed top-level {top!r}",
                    )


if __name__ == "__main__":
    unittest.main()
