"""Run fixture tests with network access disabled and artifacts in a temporary directory."""

import inspect
import os
import socket
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo), str(repo / "tests")]
sys.dont_write_bytecode = True
os.environ.update(
    MONGODB_URI="mongodb://127.0.0.1:1",
    MONGODB_DB_NAME="offline_tests",
    APP_ENV="test",
    SMTP_HOST="",
    SMTP_PASSWORD="",
    SMTP_USERNAME="",
    SMTP_FROM_EMAIL="",
    MERCADOPAGO_TEST_ACCESS_TOKEN="",
    MERCADOPAGO_TEST_WEBHOOK_SECRET="",
    PAYMENTS_ENVIRONMENT="integration",
    PAYMENTS_PRODUCTION_ENABLED="false",
)
original_connect = socket.socket.connect


def deny_network(sock, address):
    # Windows asyncio uses a private loopback socket pair to wake its event loop.
    caller = inspect.currentframe().f_back
    if caller.f_code.co_name == "_fallback_socketpair" and address[0] == "127.0.0.1":
        return original_connect(sock, address)
    raise RuntimeError("Network access is disabled in offline tests")


socket.socket.connect = deny_network
import pytest

with TemporaryDirectory(prefix="nuvly-offline-tests-") as temporary:
    previous_directory = Path.cwd()
    try:
        os.chdir(temporary)
        result = pytest.main(
            [
                str(repo / "tests"),
                "-q",
                "-p",
                "no:cacheprovider",
                "--rootdir=" + str(repo),
                "--confcutdir=" + str(repo / "tests"),
                "--basetemp=" + str(Path(temporary) / "pytest"),
            ]
        )
    finally:
        os.chdir(previous_directory)
raise SystemExit(result)
