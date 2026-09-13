"""Tests for HealthAggregator default checks (fakes, no infrastructure)."""

from app.observability.health_aggregator import HealthAggregator
from app.observability.health_aggregator import make_broker_check
from app.observability.health_aggregator import make_default_checks
from app.observability.health_aggregator import make_postgres_check
from app.observability.health_aggregator import make_redis_check


class _FakeEngine:
    def __init__(self, mode: str = "up") -> None:
        self._mode = mode

    def connect(self) -> object:
        mode = self._mode

        class _Conn:
            async def __aenter__(self) -> "_Conn":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def execute(self, sql: str) -> str:
                if mode == "down":
                    raise ConnectionError("postgres unreachable")
                return "1"

        return _Conn()


class _FakeRedis:
    def __init__(self, mode: str = "up") -> None:
        self._mode = mode

    async def ping(self) -> bool:
        if self._mode == "down":
            raise ConnectionError("redis unreachable")
        return True


class _FakeBroker:
    def __init__(self, mode: str = "up") -> None:
        self._mode = mode

    async def health_check(self) -> dict:
        if self._mode == "down":
            raise ConnectionError("broker unreachable")
        return {"status": "up", "latency_ms": 1.0}


class TestHealthAggregatorChecks:
    """3 tests: up aggregation, down propagation, exception isolation."""

    async def test_all_checks_up(self) -> None:
        """Three wired checks report a global up status."""
        aggregator = HealthAggregator(
            engine=_FakeEngine(), redis_client=_FakeRedis(), broker=_FakeBroker()  # type: ignore[arg-type]
        )

        report = await aggregator.aggregate()

        assert report["status"] == "up"
        assert {s["subsystem"] for s in report["subsystems"]} == {"postgres", "redis", "broker"}
        assert all(s["status"] == "up" for s in report["subsystems"])
        assert all("latency_ms" in s for s in report["subsystems"])

    def test_make_default_checks_registers_available_dependencies(self) -> None:
        """The lifecycle factory exposes a postgres check when an engine exists."""
        checks = make_default_checks(engine=_FakeEngine())  # type: ignore[arg-type]

        assert checks
        assert checks[0][0] == "postgres"

    def test_make_default_checks_is_empty_without_dependencies(self) -> None:
        """Degraded startup registers no unavailable infrastructure checks."""
        assert make_default_checks() == []

    async def test_down_check_propagates(self) -> None:
        """One down subsystem drives the global status to down."""
        aggregator = HealthAggregator(
            checks={
                "postgres": make_postgres_check(_FakeEngine("down")),  # type: ignore[arg-type]
                "redis": make_redis_check(_FakeRedis()),
                "broker": make_broker_check(_FakeBroker()),
            }
        )

        report = await aggregator.aggregate()

        assert report["status"] == "down"
        by_name = {s["subsystem"]: s for s in report["subsystems"]}
        assert by_name["postgres"]["status"] == "down"
        assert by_name["redis"]["status"] == "up"

    async def test_exception_isolated_as_down(self) -> None:
        """A raising check never escapes aggregate (isolated as down)."""

        async def boom() -> dict:
            raise RuntimeError("unexpected")

        aggregator = HealthAggregator(checks={"flaky": boom})

        report = await aggregator.aggregate()

        assert report["status"] == "down"
        assert report["subsystems"][0]["subsystem"] == "flaky"
        assert "RuntimeError" in report["subsystems"][0]["error"]
