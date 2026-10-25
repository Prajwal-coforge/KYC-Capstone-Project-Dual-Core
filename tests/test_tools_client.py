"""Tool client: bounded retries and failure classification, against a scripted fake server."""
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.tools_client import MAX_ATTEMPTS, ToolClient

GOOD = {"source_id": "C1-CUSTOMER", "entity_id": "ENT-1"}


class FakeService:
    """Replies to each GET with the next scripted (status, body) for that path."""

    def __init__(self, script: dict[str, list[tuple[int, object]]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.requests: list[tuple[str, str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _reply(self, status, body):
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                fake.requests.append(("GET", self.path))
                steps = fake.script.get(self.path, [])
                status, body = steps.pop(0) if len(steps) > 1 else (steps[0] if steps else (404, {}))
                self._reply(status, body)

            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                fake.requests.append(("POST", self.path))
                body = json.loads(self.rfile.read(size))
                self._reply(201, {"review_id": "rev_x", "status": "pending", "echo": body})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def count(self, path):
        return sum(1 for _, p in self.requests if p == path)


PATH = "/v1/cases/C1/customer"
TIMEOUT = (503, {"error": "upstream_timeout", "retryable": True})


class ToolClientTests(unittest.TestCase):
    def serve(self, steps):
        fake = FakeService({PATH: steps})
        self.addCleanup(fake.stop)
        return fake, ToolClient(fake.url, timeout=2)

    def test_success_on_first_attempt(self):
        fake, client = self.serve([(200, GOOD)])
        r = client.fetch("C1", "customer")
        self.assertTrue(r.ok)
        self.assertEqual((r.attempts, r.payload, r.source_id), (1, GOOD, "C1-CUSTOMER"))

    def test_transient_failure_recovers_within_three_attempts(self):
        fake, client = self.serve([TIMEOUT, TIMEOUT, (200, GOOD)])
        r = client.fetch("C1", "customer")
        self.assertTrue(r.ok)
        self.assertEqual(r.attempts, 3)
        self.assertEqual(fake.count(PATH), 3)

    def test_persistent_failure_stops_after_three_attempts(self):
        fake, client = self.serve([TIMEOUT])
        r = client.fetch("C1", "customer")
        self.assertFalse(r.ok)
        self.assertEqual((r.attempts, r.error), (MAX_ATTEMPTS, "upstream_timeout"))
        self.assertEqual(fake.count(PATH), 3)
        self.assertIsNone(r.payload)

    def test_not_found_is_not_retried(self):
        fake, client = self.serve([(404, {"error": "not_found"})])
        r = client.fetch("C1", "customer")
        self.assertEqual((r.ok, r.attempts, r.error), (False, 1, "not_found"))
        self.assertEqual(fake.count(PATH), 1)

    def test_bad_request_is_not_retried(self):
        fake, client = self.serve([(400, {"error": "bad"})])
        r = client.fetch("C1", "customer")
        self.assertEqual((r.ok, r.attempts, r.error), (False, 1, "http_400"))

    def test_invalid_json_is_retried_then_fails(self):
        fake, client = self.serve([(200, b"not json")])
        r = client.fetch("C1", "customer")
        self.assertEqual((r.ok, r.attempts, r.error), (False, 3, "invalid_response"))

    def test_payload_without_source_id_is_invalid(self):
        fake, client = self.serve([(200, {"entity_id": "ENT-1"})])
        self.assertEqual(client.fetch("C1", "customer").error, "invalid_response")

    def test_connection_refused_is_retried_then_fails(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        r = ToolClient(f"http://127.0.0.1:{port}", timeout=1).fetch("C1", "customer")
        self.assertEqual((r.ok, r.attempts, r.error), (False, 3, "connection_error"))

    def test_case_id_is_url_quoted(self):
        fake = FakeService({})
        self.addCleanup(fake.stop)
        ToolClient(fake.url, timeout=2).fetch("../admin", "customer")
        self.assertEqual(fake.requests[0][1], "/v1/cases/..%2Fadmin/customer")

    def test_unknown_tool_is_rejected_without_a_request(self):
        fake, client = self.serve([(200, GOOD)])
        with self.assertRaises(ValueError):
            client.fetch("C1", "records")
        self.assertEqual(fake.requests, [])

    def test_submit_review_posts_the_draft(self):
        fake, client = self.serve([(200, GOOD)])
        body = client.submit_review("C1", {"case_id": "C1"})
        self.assertEqual(body["status"], "pending")
        self.assertEqual(fake.requests, [("POST", "/v1/reviews")])

    def test_client_has_no_write_or_approval_operations(self):
        for name in ("create_record", "approve", "reject", "post_record"):
            self.assertFalse(hasattr(ToolClient, name), name)

    def test_backoff_between_retries_is_exponential(self):
        fake, client = self.serve([TIMEOUT])
        delays = []
        client.sleep = delays.append
        client.backoff_seconds = 0.2
        client.fetch("C1", "customer")
        self.assertEqual(delays, [0.2, 0.4])
        self.assertEqual(fake.count(PATH), 3)

    def test_open_circuit_skips_http_until_cooldown_then_one_probe(self):
        fake, client = self.serve([TIMEOUT, TIMEOUT, TIMEOUT, (200, GOOD)])
        clock = {"t": 0.0}
        client._now = lambda: clock["t"]
        client.sleep = lambda _delay: None
        client.backoff_seconds = 0.2
        client.circuit_cooldown = 30.0
        first = client.fetch("C1", "customer")
        self.assertEqual((first.ok, first.attempts, first.circuit), (False, 3, "closed"))
        blocked = client.fetch("C1", "customer")
        self.assertEqual((blocked.ok, blocked.attempts, blocked.error, blocked.circuit),
                         (False, 0, "circuit_open", "open"))
        self.assertEqual(fake.count(PATH), 3)
        clock["t"] = 30.0
        probe = client.fetch("C1", "customer")
        self.assertTrue(probe.ok)
        self.assertEqual(probe.circuit, "half_open")
        self.assertEqual(fake.count(PATH), 4)
        again = client.fetch("C1", "customer")
        self.assertTrue(again.ok)
        self.assertEqual(again.circuit, "closed")


if __name__ == "__main__":
    unittest.main()
