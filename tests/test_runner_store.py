"""Runner selects sqlite or postgres via --dsn / KYC_DATABASE_URL, never mock.sqlite."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kyc_copilot.adapters.store_factory import resolve_store_target
from kyc_copilot.runner.cli import main as run_cli
from kyc_copilot.runner.ingest import ingest
from kyc_copilot.runner.ingest import main as run_ingest
from tests.helpers import DEV


class ResolveStoreTargetTests(unittest.TestCase):
    def test_dsn_wins_over_env_and_db(self) -> None:
        self.assertEqual(
            resolve_store_target(
                db=".state/app.sqlite",
                dsn="postgresql://cli/kyc",
                env={"KYC_DATABASE_URL": "postgresql://env/kyc"},
            ),
            "postgresql://cli/kyc",
        )

    def test_env_wins_over_db(self) -> None:
        self.assertEqual(
            resolve_store_target(
                db=".state/app.sqlite",
                dsn=None,
                env={"KYC_DATABASE_URL": "postgresql://env/kyc"},
            ),
            "postgresql://env/kyc",
        )

    def test_db_used_when_no_dsn_or_env(self) -> None:
        self.assertEqual(
            resolve_store_target(db=".state/app.sqlite", dsn=None, env={}),
            ".state/app.sqlite",
        )

    def test_cloud_run_needs_only_env(self) -> None:
        self.assertEqual(
            resolve_store_target(
                db=None, dsn=None, env={"KYC_DATABASE_URL": "postgresql://cloud/kyc"}
            ),
            "postgresql://cloud/kyc",
        )


class CliStoreSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = str(Path(self.tmp.name) / "results.json")

    def _store(self) -> MagicMock:
        store = MagicMock()
        store.__enter__.return_value = store
        store.__exit__.return_value = False
        store.replace_all.return_value = {
            "added": [],
            "updated": [],
            "unchanged": [],
            "removed": [],
        }
        store.counts.return_value = {
            "sources": 0,
            "tool_sources": 0,
            "policies": 0,
            "documents": 0,
            "chunks": 0,
        }
        return store

    def test_cli_dsn_is_passed_to_factory(self) -> None:
        store = self._store()
        with (
            patch("kyc_copilot.runner.cli.open_knowledge_store", return_value=store) as opener,
            patch("kyc_copilot.runner.cli.ingest"),
            patch("kyc_copilot.runner.cli.run_cases", return_value=[]),
            patch("kyc_copilot.runner.cli.ToolClient") as client_cls,
        ):
            client_cls.return_value.list_cases.return_value = []
            run_cli(
                [
                    "--dsn",
                    "postgresql://kyc:kyc@localhost/kyc",
                    "--db",
                    str(Path(self.tmp.name) / "app.sqlite"),
                    "--out",
                    self.out,
                    "--cases",
                ]
            )
        opener.assert_called_once()
        self.assertEqual(opener.call_args[0][0], "postgresql://kyc:kyc@localhost/kyc")

    def test_cli_env_wins_over_db(self) -> None:
        store = self._store()
        env = {**os.environ, "KYC_DATABASE_URL": "postgresql://env-host/kyc"}
        with (
            patch("kyc_copilot.runner.cli.open_knowledge_store", return_value=store) as opener,
            patch("kyc_copilot.runner.cli.ingest"),
            patch("kyc_copilot.runner.cli.run_cases", return_value=[]),
            patch("kyc_copilot.runner.cli.ToolClient") as client_cls,
            patch("kyc_copilot.runner.cli.os.environ", env),
        ):
            client_cls.return_value.list_cases.return_value = []
            run_cli(["--out", self.out, "--cases"])
        self.assertEqual(opener.call_args[0][0], "postgresql://env-host/kyc")

    def test_cli_still_refuses_mock_sqlite_path(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "KYC_DATABASE_URL"}
        with patch("kyc_copilot.runner.cli.os.environ", env), self.assertRaises(SystemExit):
            run_cli(
                [
                    "--db",
                    str(Path(self.tmp.name) / "mock.sqlite"),
                    "--out",
                    self.out,
                ]
            )

    def test_ingest_accepts_factory_sqlite_store(self) -> None:
        from kyc_copilot.adapters.store_factory import open_knowledge_store

        with open_knowledge_store(":memory:") as store:
            report = ingest(DEV, store)
        self.assertGreater(report["totals"]["policies"], 0)

    def test_ingest_cli_dsn_is_passed_to_factory(self) -> None:
        store = self._store()
        with patch("kyc_copilot.runner.ingest.open_knowledge_store", return_value=store) as opener:
            run_ingest(["--dsn", "postgresql://kyc:kyc@localhost/kyc", "--data", str(DEV)])
        opener.assert_called_once()
        self.assertEqual(opener.call_args[0][0], "postgresql://kyc:kyc@localhost/kyc")


if __name__ == "__main__":
    unittest.main()
