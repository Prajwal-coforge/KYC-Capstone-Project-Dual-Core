"""Shared test helpers: load the supplied tools and run the mock service in-process."""

import importlib.util
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "dev"


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"supplied_{name}", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MockService:
    """The supplied mock (tools/runtime.py) on a free loopback port with its own state file."""

    def __init__(self, state_path: Path, data_dir: Path = DEV):
        self.runtime = load_tool("runtime")
        self.state_path = state_path
        self.server = self.runtime.create_server(data_dir, state_path, port=0)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def audit(self) -> list[dict]:
        with self.runtime.connect(self.state_path) as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY seq")]

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
