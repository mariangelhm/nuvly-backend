from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace

import pytest

from app.core import rate_limits
from app.core.errors import NuvlyError


@pytest.fixture
def budget(monkeypatch):
    class Collection:
        def __init__(self):
            self.records = {}
            self.lock = Lock()

        def find_one_and_update(self, filters, update, **kwargs):
            with self.lock:
                record = self.records.setdefault(filters["_id"], {"count": 0, **update.get("$setOnInsert", {})})
                record["count"] += update["$inc"]["count"]
                return dict(record)

    collection = Collection()
    monkeypatch.setattr(rate_limits, "get_database", lambda: SimpleNamespace(rate_limits=collection))
    return collection


def test_limits_are_atomic_shared_and_expire_by_window_without_storing_identity(budget):
    def consume(_):
        try:
            rate_limits.consume_rate_limit("login", "private@example.test", 5, 60, now=100)
            return True
        except NuvlyError as error:
            assert error.status_code == 429
            assert error.retry_after > 0
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(consume, range(20))) == 5
    rate_limits.consume_rate_limit("login", "private@example.test", 5, 60, now=121)
    assert "private@example.test" not in str(budget.records)
    assert all("expiresAt" in record for record in budget.records.values())


def test_weighted_owner_budget_cannot_exceed_daily_limit(budget):
    rate_limits.consume_rate_limit("media", "owner", 100, 86400, cost=80, now=100)
    with pytest.raises(NuvlyError) as error:
        rate_limits.consume_rate_limit("media", "owner", 100, 86400, cost=30, now=100)
    assert error.value.code == "RATE_LIMIT_EXCEEDED"
    rate_limits.consume_rate_limit("media", "another-owner", 100, 86400, cost=30, now=100)


def test_rate_store_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(rate_limits, "get_database", lambda: (_ for _ in ()).throw(OSError("storage unavailable")))
    with pytest.raises(NuvlyError) as error:
        rate_limits.consume_rate_limit("login", "account", 10, 60)
    assert error.value.status_code == 503


def test_ip_limit_rejects_before_downstream_body_processing(monkeypatch):
    import asyncio

    messages = []

    async def downstream(*args):
        pytest.fail("A limited request must not reach body parsing or endpoints")

    def reject(*args):
        error = NuvlyError("Wait", 429, "RATE_LIMIT_EXCEEDED")
        error.retry_after = 20
        raise error

    monkeypatch.setattr(rate_limits, "consume_rate_limit", reject)

    async def run():
        async def receive():
            pytest.fail("No request body should be read")

        async def send(message):
            messages.append(message)

        await rate_limits.AbuseLimitMiddleware(downstream, api_prefix="/api")(
            {"type": "http", "path": "/api/auth/login", "method": "POST", "client": ("synthetic", 1)},
            receive,
            send,
        )

    asyncio.run(run())
    assert messages[0]["status"] == 429
    assert (b"retry-after", b"20") in messages[0]["headers"]
