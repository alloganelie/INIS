"""Unit tests for FallbackChain per §22.2."""

import pytest

from app.core.errors import InfrastructureError
from app.llm.router.fallback_chain import FallbackChain


def test_fallback_chain_initialization() -> None:
    chain = FallbackChain(["primary-m", "fallback-1", "fallback-2"])
    assert chain.get_primary() == "primary-m"
    assert chain.get_fallback(1) == "fallback-1"
    assert chain.get_fallback(2) == "fallback-2"
    assert chain.get_all() == ["primary-m", "fallback-1", "fallback-2"]


def test_fallback_chain_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        FallbackChain([])


def test_fallback_chain_add_and_remove() -> None:
    chain = FallbackChain(["m1"])
    chain.add_model("m2")
    assert chain.get_all() == ["m1", "m2"]
    chain.remove_model("m1")
    assert chain.get_all() == ["m2"]

    with pytest.raises(ValueError, match="Cannot remove last model"):
        chain.remove_model("m2")


@pytest.mark.asyncio
async def test_fallback_chain_run_succeeds_on_primary() -> None:
    chain = FallbackChain(["m1", "m2"])
    calls = []

    async def call_model(m: str) -> str:
        calls.append(m)
        return f"result-{m}"

    res = await chain.run(call_model)
    assert res == "result-m1"
    assert calls == ["m1"]


@pytest.mark.asyncio
async def test_fallback_chain_run_falls_back_on_failure() -> None:
    chain = FallbackChain(["m1", "m2"])
    calls = []

    async def call_model(m: str) -> str:
        calls.append(m)
        if m == "m1":
            raise RuntimeError("m1 offline")
        return f"result-{m}"

    res = await chain.run(call_model)
    assert res == "result-m2"
    assert calls == ["m1", "m2"]


@pytest.mark.asyncio
async def test_fallback_chain_run_exhaustion_raises_infrastructure_error() -> None:
    chain = FallbackChain(["m1", "m2"])

    async def always_fail(m: str) -> str:
        raise RuntimeError(f"{m} unavailable")

    with pytest.raises(InfrastructureError, match="All 2 models in the fallback chain failed"):
        await chain.run(always_fail)
