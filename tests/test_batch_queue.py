"""The cloud worker leaves a case on the queue unless Postgres accepts the review."""

from __future__ import annotations

import json
import runpy
import subprocess
import unittest
from unittest.mock import patch

from kyc_copilot.runner.batch_queue import (
    main,
    parse_receive,
    require_postgres_url,
    review_command,
    run_once,
)

URL = "postgresql://kyc:secret@db.example:5432/kyc"
ENV = {
    "KYC_DATABASE_URL": URL,
    "KYC_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/kyc",
    "AWS_REGION": "us-east-1",
}


def _done(code: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr="")


def _message(body: str, receipt: str = "receipt-1") -> str:
    return json.dumps({"Messages": [{"Body": body, "ReceiptHandle": receipt}]})


class PostgresRequirementTests(unittest.TestCase):
    def test_postgres_urls_are_accepted(self) -> None:
        self.assertEqual(require_postgres_url({"KYC_DATABASE_URL": URL}), URL)
        self.assertTrue(require_postgres_url({"KYC_DATABASE_URL": "postgres://db/kyc"}))

    def test_a_missing_or_file_url_stays_off_the_queue_reader(self) -> None:
        for env in ({}, {"KYC_DATABASE_URL": " .state/app.sqlite "}):
            with self.assertRaises(ValueError) as caught:
                require_postgres_url(env)
            self.assertIn("stays on the queue", str(caught.exception))


class ParseReceiveTests(unittest.TestCase):
    def test_an_empty_receive_is_idle(self) -> None:
        self.assertIsNone(parse_receive("{}"))
        self.assertIsNone(parse_receive('{"Messages": []}'))

    def test_a_plain_body_and_a_json_body_both_yield_the_case(self) -> None:
        plain = parse_receive(_message("KYC-D01"))
        wrapped = parse_receive(_message(json.dumps({"case_id": " KYC-D02 "})))
        assert plain is not None and wrapped is not None
        self.assertEqual(plain.case_id, "KYC-D01")
        self.assertEqual(wrapped.case_id, "KYC-D02")

    def test_unreadable_responses_are_refused(self) -> None:
        payloads = (
            "[",
            "[]",
            "{",
            json.dumps({"Messages": ["KYC-D01"]}),
            json.dumps({"Messages": [{"Body": 1, "ReceiptHandle": "r"}]}),
            json.dumps({"Messages": [{"Body": "KYC-D01", "ReceiptHandle": ""}]}),
            _message(""),
            _message("{not json}"),
            _message(json.dumps({"case_id": 1})),
        )
        for payload in payloads:
            with self.assertRaises(ValueError):
                parse_receive(payload)


class ReviewCommandTests(unittest.TestCase):
    def test_the_image_command_does_not_carry_the_database_url(self) -> None:
        command = review_command("KYC-D01", {**ENV, "KYC_IMAGE": "kyc@sha256:abc"})
        self.assertEqual(command[0], "docker")
        self.assertIn("kyc@sha256:abc", command)
        self.assertIn("KYC-D01", command)
        self.assertNotIn(URL, command)
        self.assertNotIn("secret", " ".join(command))

    def test_the_cloud_review_shares_the_host_network_as_kyc(self) -> None:
        command = review_command(
            "KYC-D01",
            {
                **ENV,
                "KYC_IMAGE": "kyc:dev",
                "KYC_DOCKER_NETWORK": "host",
                "KYC_RUN_USER": "kyc",
                "KYC_API_URL": "http://127.0.0.1:8766",
            },
        )
        self.assertEqual(command[command.index("--network") + 1], "host")
        self.assertEqual(command[command.index("--user") + 1], "kyc")
        self.assertIn("http://127.0.0.1:8766", command)

    def test_without_an_image_the_local_interpreter_runs_the_review(self) -> None:
        command = review_command("KYC-D01", ENV)
        self.assertIn("kyc_copilot", command)
        self.assertNotIn("docker", command)


class RunOnceTests(unittest.TestCase):
    def test_a_file_store_never_reads_the_queue(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(args)
            return _done()

        code = run_once({"KYC_DATABASE_URL": ".state/app.sqlite", "KYC_QUEUE_URL": "q"}, run)
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_a_missing_queue_url_does_not_call_aws(self) -> None:
        calls: list[list[str]] = []
        code = run_once({"KYC_DATABASE_URL": URL}, lambda args, **_k: calls.append(args))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_a_failed_receive_leaves_the_case_alone(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(args)
            return _done(code=1, stdout="")

        self.assertEqual(run_once(ENV, run), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "receive-message")

    def test_a_bad_message_is_not_deleted(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            return _done(stdout="{")

        self.assertEqual(run_once(ENV, run), 1)
        self.assertEqual([item[2] for item in calls], ["receive-message"])

    def test_an_idle_queue_does_not_review(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            return _done(stdout="{}")

        self.assertEqual(run_once(ENV, run), 3)
        self.assertEqual([item[2] for item in calls], ["receive-message"])

    def test_a_failed_review_is_not_deleted(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            if args[0] == "aws":
                return _done(stdout=_message("KYC-D07"))
            return _done(code=1)

        self.assertEqual(run_once(ENV, run), 1)
        self.assertEqual(calls[0][2], "receive-message")
        self.assertNotEqual(calls[1][0], "aws")
        self.assertFalse(any(item[0] == "aws" and item[2] == "delete-message" for item in calls))

    def test_a_finished_review_deletes_only_that_receipt(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            if args[2:3] == ["receive-message"]:
                return _done(stdout=_message(json.dumps({"case_id": "KYC-D01"}), "rh-9"))
            return _done()

        self.assertEqual(run_once({**ENV, "KYC_IMAGE": "kyc:dev"}, run), 0)
        delete = calls[-1]
        self.assertEqual(delete[2], "delete-message")
        self.assertIn("rh-9", delete)
        self.assertNotIn("secret", " ".join(" ".join(item) for item in calls))

    def test_a_finished_review_copies_the_packet_before_delete(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            if args[2:3] == ["receive-message"]:
                return _done(stdout=_message("KYC-D01", "rh-1"))
            return _done()

        env = {
            **ENV,
            "KYC_IMAGE": "kyc:dev",
            "KYC_OUT_DIR": "/var/lib/kyc/out",
            "KYC_PACKET_BUCKET": "packets",
            "KYC_TRACE_BUCKET": "traces",
        }
        self.assertEqual(run_once(env, run), 0)
        self.assertIn("/out/results.json", calls[1])
        self.assertIn("/var/lib/kyc/out:/out", calls[1])
        self.assertEqual(calls[2][0:3], ["aws", "s3", "cp"])
        self.assertEqual(calls[2][4], "s3://packets/cases/KYC-D01/results.json")
        self.assertEqual(calls[3][0:3], ["aws", "s3", "cp"])
        self.assertEqual(calls[3][4], "s3://traces/cases/KYC-D01/trace.jsonl")
        self.assertEqual(calls[4][2], "delete-message")
        self.assertNotIn("secret", " ".join(" ".join(item) for item in calls))

    def test_a_missed_copy_leaves_the_message(self) -> None:
        def run(args, **_kwargs):
            if args[2:3] == ["receive-message"]:
                return _done(stdout=_message("KYC-D01"))
            if args[0:3] == ["aws", "s3", "cp"]:
                return _done(code=1)
            return _done()

        env = {
            **ENV,
            "KYC_OUT_DIR": "/var/lib/kyc/out",
            "KYC_PACKET_BUCKET": "packets",
            "KYC_TRACE_BUCKET": "traces",
        }
        self.assertEqual(run_once(env, run), 1)

    def test_a_partial_copy_configuration_leaves_the_message(self) -> None:
        calls: list[list[str]] = []

        def run(args, **_kwargs):
            calls.append(list(args))
            if args[2:3] == ["receive-message"]:
                return _done(stdout=_message("KYC-D01"))
            return _done()

        self.assertEqual(run_once({**ENV, "KYC_OUT_DIR": "/var/lib/kyc/out"}, run), 1)
        self.assertFalse(any(item[0] == "aws" and item[2] == "delete-message" for item in calls))

    def test_a_delete_failure_after_a_good_review_is_reported(self) -> None:
        def run(args, **_kwargs):
            if args[2:3] == ["receive-message"]:
                return _done(stdout=_message("KYC-D01"))
            if args[0] == "aws":
                return _done(code=1)
            return _done()

        self.assertEqual(run_once(ENV, run), 1)

    def test_main_reads_the_process_environment(self) -> None:
        with (
            patch.dict("os.environ", {"KYC_DATABASE_URL": ".state/app.sqlite"}, clear=True),
            patch("sys.stderr"),
        ):
            self.assertEqual(main([]), 2)


class ModuleEntryTests(unittest.TestCase):
    def test_module_entry_returns_the_worker_code(self) -> None:
        with (
            patch.dict("os.environ", ENV, clear=True),
            patch("subprocess.run", return_value=_done(stdout="{}")),
            patch("sys.argv", ["batch_queue"]),
            self.assertRaises(SystemExit) as caught,
        ):
            runpy.run_module("kyc_copilot.runner.batch_queue", run_name="__main__")
        self.assertEqual(caught.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
