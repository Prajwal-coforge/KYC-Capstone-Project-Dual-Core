"""Factory selects sqlite vs postgres and refuses the mock bank database."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.adapters.store_factory import open_knowledge_store, resolve_store_target
from kyc_copilot.contracts.interfaces import KnowledgeStore


class OpenKnowledgeStoreTests(unittest.TestCase):
    def test_memory_opens_sqlite_store(self) -> None:
        store = open_knowledge_store(":memory:")
        self.addCleanup(store.close)
        self.assertIsInstance(store, SqliteKnowledgeStore)
        self.assertTrue(hasattr(store, "replace_all"))
        self.assertTrue(hasattr(store, "save_tool_evidence"))
        self.assertTrue(hasattr(store, "counts"))
        with store as entered:
            self.assertIs(entered, store)

    def test_sqlite_path_opens_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "app.sqlite")
            store = open_knowledge_store(path)
            self.addCleanup(store.close)
            self.assertIsInstance(store, SqliteKnowledgeStore)

    def test_postgresql_url_opens_postgres_store(self) -> None:
        fake = MagicMock()
        with patch(
            "kyc_copilot.adapters.postgres_store.PostgresKnowledgeStore",
            return_value=fake,
        ) as cls:
            store = open_knowledge_store("postgresql://kyc:kyc@db:5432/kyc")
        cls.assert_called_once_with("postgresql://kyc:kyc@db:5432/kyc")
        self.assertIs(store, fake)

    def test_postgres_url_opens_postgres_store(self) -> None:
        fake = MagicMock()
        with patch(
            "kyc_copilot.adapters.postgres_store.PostgresKnowledgeStore",
            return_value=fake,
        ):
            store = open_knowledge_store("postgres://kyc:kyc@db:5432/kyc")
        self.assertIs(store, fake)

    def test_mock_sqlite_filename_is_refused(self) -> None:
        for target in ("mock.sqlite", "/tmp/mock.sqlite", str(Path(".state") / "mock.sqlite")):
            with self.subTest(target=target), self.assertRaises(ValueError) as ctx:
                open_knowledge_store(target)
            self.assertIn("mock", str(ctx.exception).lower())

    def test_missing_target_and_unknown_target_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            resolve_store_target(db=None, dsn="  ", env={})
        with self.assertRaises(ValueError):
            open_knowledge_store("not-a-database")

    def test_a_failed_postgres_open_does_not_fall_back_to_sqlite(self) -> None:
        with patch(
            "kyc_copilot.adapters.postgres_store.psycopg.connect",
            side_effect=OSError("down"),
        ):
            with self.assertRaises(OSError):
                open_knowledge_store("postgresql://kyc:kyc@db.example:5432/kyc")

    def test_knowledge_store_protocol_includes_writes_and_close(self) -> None:
        for name in ("replace_all", "save_tool_evidence", "counts", "__enter__", "__exit__"):
            self.assertTrue(hasattr(KnowledgeStore, name), name)


if __name__ == "__main__":
    unittest.main()
