"""Tests for validator retry/backoff and protocol auto-detection wrappers.

These exercise the orchestration logic deterministically by patching the single
attempt, so no network is required and the zero-false-positive contract (WORKING
only ever comes from a genuine attempt result) is verified explicitly.
"""

import app.testing.validator as validator
from app.core.enums import Protocol, ValidationStatus
from app.core.models import Endpoint, ValidationResult
from app.testing.profiles import quick_profile


def _res(ep, status, category=None):
    return ValidationResult(endpoint=ep, status=status, error_category=category,
                            exit_ip="5.6.7.8" if status == ValidationStatus.WORKING else None)


async def test_retry_stops_on_first_success(monkeypatch):
    calls = {"n": 0}

    async def fake_single(ep, *a, **k):
        calls["n"] += 1
        status = ValidationStatus.WORKING if calls["n"] == 2 else ValidationStatus.TIMEOUT
        return _res(ep, status, None if status == ValidationStatus.WORKING else "timeout")

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 80, Protocol.HTTP)
    r = await validator.validate_proxy(ep, quick_profile(), ["u"], retries=3, retry_backoff=0)
    assert r.status == ValidationStatus.WORKING
    assert calls["n"] == 2  # stopped after the first success


async def test_retry_exhausts_and_stays_failed(monkeypatch):
    calls = {"n": 0}

    async def fake_single(ep, *a, **k):
        calls["n"] += 1
        return _res(ep, ValidationStatus.TIMEOUT, "timeout")

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 80, Protocol.HTTP)
    r = await validator.validate_proxy(ep, quick_profile(), ["u"], retries=2, retry_backoff=0)
    assert r.status == ValidationStatus.TIMEOUT  # never a false WORKING
    assert calls["n"] == 3  # 1 + 2 retries


async def test_auth_is_terminal_no_retry(monkeypatch):
    calls = {"n": 0}

    async def fake_single(ep, *a, **k):
        calls["n"] += 1
        return _res(ep, ValidationStatus.AUTH_REQUIRED, "auth")

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 80, Protocol.HTTP)
    r = await validator.validate_proxy(ep, quick_profile(), ["u"], retries=3, retry_backoff=0)
    assert r.status == ValidationStatus.AUTH_REQUIRED
    assert calls["n"] == 1  # auth not retried


async def test_autodetect_tries_own_protocol_first(monkeypatch):
    seen = []

    async def fake_single(ep, *a, **k):
        seen.append(ep.protocol)
        return _res(ep, ValidationStatus.WORKING)

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 1080, Protocol.SOCKS5)
    r = await validator.validate_proxy(
        ep, quick_profile(), ["u"], protocols=[Protocol.SOCKS5, Protocol.HTTP]
    )
    assert r.status == ValidationStatus.WORKING
    assert seen == [Protocol.SOCKS5]  # own protocol worked first, no others tried


async def test_autodetect_corrects_mislabeled(monkeypatch):
    async def fake_single(ep, *a, **k):
        # Only HTTP genuinely works for this endpoint.
        if ep.protocol == Protocol.HTTP:
            return _res(ep, ValidationStatus.WORKING)
        return _res(ep, ValidationStatus.FAILED, "protocol")

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 8080, Protocol.SOCKS5)  # mislabeled
    r = await validator.validate_proxy(
        ep, quick_profile(), ["u"], protocols=[Protocol.SOCKS5, Protocol.HTTP, Protocol.SOCKS4]
    )
    assert r.status == ValidationStatus.WORKING
    assert r.endpoint.protocol == Protocol.HTTP  # corrected


async def test_autodetect_all_fail_no_false_positive(monkeypatch):
    async def fake_single(ep, *a, **k):
        return _res(ep, ValidationStatus.FAILED, "connect")

    monkeypatch.setattr(validator, "_validate_single", fake_single)
    ep = Endpoint("1.2.3.4", 9999, Protocol.HTTP)
    r = await validator.validate_proxy(
        ep, quick_profile(), ["u"], protocols=list(validator._AUTODETECT_ORDER)
    )
    assert r.status != ValidationStatus.WORKING
