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


def _kyc_imports_from_file(py_file: Path) -> set[str]:
    """Return absolute kyc_copilot.* module prefixes referenced by absolute imports."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("kyc_copilot"):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("kyc_copilot"):
                found.add(node.module)
    return found


class TestObservabilityBoundaries(unittest.TestCase):
    """Cycle 2.1: observability may import only kyc_copilot.contracts (+ stdlib)."""

    def test_observability_tracing_module_exists_and_imports_contracts_only(self) -> None:
        tracing = importlib.import_module("kyc_copilot.observability.tracing")
        path = _module_file(tracing)
        obs = (SRC / "kyc_copilot" / "observability").resolve()
        self.assertTrue(str(path).startswith(str(obs)))
        for name in ("JsonlTrace", "metrics", "trace_events"):
            self.assertTrue(hasattr(tracing, name), f"missing {name}")

        for top in _imported_module_names(path):
            if top in sys.stdlib_module_names:
                continue
            if top == "kyc_copilot":
                continue
            self.fail(f"observability.tracing imports disallowed top-level {top!r}")

        abs_imports = _kyc_imports_from_file(path)
        for mod in abs_imports:
            self.assertTrue(
                mod == "kyc_copilot.contracts" or mod.startswith("kyc_copilot.contracts."),
                f"observability must only import contracts, found {mod}",
            )
            self.assertFalse(mod.startswith("kyc_copilot.adapters"))
            self.assertFalse(mod.startswith("kyc_copilot.runner"))
            self.assertFalse(mod.startswith("kyc_copilot.domain"))


class TestDomainBoundaries(unittest.TestCase):
    """Cycle 3.1 / 4.1: domain may import only kyc_copilot.contracts (+ stdlib)."""

    def test_domain_packet_module_exports_build_helpers(self) -> None:
        packet = importlib.import_module("kyc_copilot.domain.packet")
        path = _module_file(packet)
        domain = (SRC / "kyc_copilot" / "domain").resolve()
        self.assertTrue(str(path).startswith(str(domain)))
        for name in ("build_citations", "build_packet", "_follow_up"):
            self.assertTrue(hasattr(packet, name), f"missing {name}")

    def test_domain_rules_module_exists_and_registers_statutory_rules(self) -> None:
        rules = importlib.import_module("kyc_copilot.domain.rules")
        path = _module_file(rules)
        domain = (SRC / "kyc_copilot" / "domain").resolve()
        self.assertTrue(str(path).startswith(str(domain)))
        for name in (
            "CaseEvidence",
            "decide",
            "normalize_address",
            "compare_addresses",
            "ToolAvailabilityRule",
            "CrossSourceConflictRule",
            "ScopeAndPolicyRule",
            "OwnershipDepthRule",
            "ScreeningMatchRule",
            "IdentityDocumentRule",
            "AddressComparisonRule",
            "EddAndPepRule",
        ):
            self.assertTrue(hasattr(rules, name), f"missing {name}")

        from kyc_copilot.contracts.interfaces import StatutoryRule

        ordered = StatutoryRule.ordered_rules()
        self.assertEqual(
            [r.rule_id for r in ordered],
            [
                "tool_availability",
                "cross_source_conflict",
                "scope_and_policy",
                "ownership_depth",
                "screening_match",
                "identity_document",
                "address_comparison",
                "edd_and_pep",
            ],
        )

    def test_domain_imports_only_contracts(self) -> None:
        domain_dir = SRC / "kyc_copilot" / "domain"
        files = [p for p in domain_dir.glob("*.py") if p.name != "__init__.py"]
        self.assertTrue(files, f"expected modules under {domain_dir}")
        for path in files:
            with self.subTest(file=path.name):
                for top in _imported_module_names(path):
                    if top in sys.stdlib_module_names or top in ALLOWED_CONTRACT_THIRD_PARTY:
                        continue
                    if top == "kyc_copilot":
                        continue
                    self.fail(f"{path.name} imports disallowed top-level {top!r}")
                for mod in _kyc_imports_from_file(path):
                    allowed = mod == "kyc_copilot.contracts" or mod.startswith(
                        "kyc_copilot.contracts."
                    )
                    same_layer = mod == "kyc_copilot.domain" or mod.startswith(
                        "kyc_copilot.domain."
                    )
                    self.assertTrue(
                        allowed or same_layer,
                        f"{path.name} imports {mod} outside contracts/domain",
                    )


class TestAdaptersBoundaries(unittest.TestCase):
    """Cycle 2.2: adapters may import contracts + observability only."""

    def test_adapter_modules_exist_with_expected_exports(self) -> None:
        redaction = importlib.import_module("kyc_copilot.adapters.redaction")
        store = importlib.import_module("kyc_copilot.adapters.sqlite_store")
        tools = importlib.import_module("kyc_copilot.adapters.tools_client")

        self.assertTrue(hasattr(redaction, "redact"))
        self.assertTrue(hasattr(redaction, "canonical_json"))
        self.assertTrue(hasattr(redaction, "json_fragment"))
        self.assertEqual(store.SCHEMA_VERSION, 3)
        self.assertTrue(hasattr(store, "SqliteKnowledgeStore"))
        self.assertTrue(hasattr(tools, "ToolClient"))
        self.assertTrue(hasattr(tools, "MAX_ATTEMPTS"))

    def test_adapters_import_only_contracts_and_observability(self) -> None:
        adapters_dir = SRC / "kyc_copilot" / "adapters"
        files = list(adapters_dir.glob("*.py"))
        self.assertTrue(files, f"expected modules under {adapters_dir}")
        allowed_prefixes = (
            "kyc_copilot.contracts",
            "kyc_copilot.observability",
        )
        for path in files:
            with self.subTest(file=path.name):
                for top in _imported_module_names(path):
                    if top in sys.stdlib_module_names or top in ALLOWED_CONTRACT_THIRD_PARTY:
                        continue
                    if top == "kyc_copilot":
                        continue
                    self.fail(f"{path.name} imports disallowed top-level {top!r}")
                for mod in _kyc_imports_from_file(path):
                    self.assertTrue(
                        any(mod == p or mod.startswith(p + ".") for p in allowed_prefixes),
                        f"{path.name} imports {mod} outside contracts/observability",
                    )
                    self.assertFalse(mod.startswith("kyc_copilot.domain"))
                    self.assertFalse(mod.startswith("kyc_copilot.ingestion"))
                    self.assertFalse(mod.startswith("kyc_copilot.runner"))


if __name__ == "__main__":
    unittest.main()
