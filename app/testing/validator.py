"""Asynchronous proxy validator.

Performs a *real* proxy-mediated request (never a bare TCP probe) to a
configurable validation endpoint, measuring connect/response latency, the exit
IP, authentication outcome, anonymity and DNS behaviour. Transport is chosen
per protocol:

* HTTP / HTTPS / SOCKS5 — via ``httpx.AsyncClient(proxy=...)``
* SOCKS4                — via ``aiohttp`` + ``aiohttp_socks.ProxyConnector``

Every failure is caught and mapped to a :class:`ValidationStatus`; a single bad
proxy can never raise out of :func:`validate_proxy`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

from app.core.enums import Anonymity, DnsStatus, Protocol, ValidationStatus
from app.core.models import Endpoint, ValidationResult, utcnow
from app.testing.anonymity import analyze_anonymity
from app.testing.dns_analysis import analyze_dns
from app.testing.profiles import ValidationProfile

logger = logging.getLogger(__name__)

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")


@dataclass
class _HttpResponse:
    status_code: int
    text: str
    headers: dict[str, str]
    elapsed_ms: float


def _extract_ip(body: str) -> str | None:
    """Extract an exit IP from a validation-endpoint response."""
    body = (body or "").strip()
    if not body:
        return None
    # JSON forms: {"ip": ...} or {"origin": ...}
    try:
        data = json.loads(body)
        for key in ("ip", "origin", "query", "ipAddress"):
            if isinstance(data, dict) and data.get(key):
                candidate = str(data[key]).split(",")[0].strip()
                if _IPV4_RE.search(candidate) or _IPV6_RE.search(candidate):
                    return candidate
    except (json.JSONDecodeError, ValueError):
        pass
    m = _IPV4_RE.search(body)
    if m:
        return m.group(0)
    m = _IPV6_RE.search(body)
    if m and ":" in m.group(0):
        return m.group(0)
    return None


class _AuthError(Exception):
    pass


class _ProtocolError(Exception):
    pass


async def _tcp_connect_time(host: str, port: int, timeout: float) -> float:
    """Return TCP connect time in ms (reachability only, not a proxy check)."""
    start = time.perf_counter()
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
    elapsed = (time.perf_counter() - start) * 1000.0
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # pragma: no cover
        pass
    return elapsed


async def _httpx_get(endpoint: Endpoint, url: str, timeout: float) -> _HttpResponse:
    import httpx

    proxy_url = endpoint.url(include_credentials=True)
    start = time.perf_counter()
    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=httpx.Timeout(timeout),
        verify=False,  # proxies frequently break TLS chains; we only need reachability
        follow_redirects=True,
        headers={"User-Agent": "ProxyAtlas/1.0 validator"},
    ) as client:
        try:
            resp = await client.get(url)
        except httpx.ProxyError as exc:
            if "407" in str(exc) or "auth" in str(exc).lower():
                raise _AuthError(str(exc)) from exc
            raise _ProtocolError(str(exc)) from exc
    elapsed = (time.perf_counter() - start) * 1000.0
    if resp.status_code == 407:
        raise _AuthError("Proxy authentication required (407)")
    return _HttpResponse(resp.status_code, resp.text, dict(resp.headers), elapsed)


async def _aiohttp_socks_get(endpoint: Endpoint, url: str, timeout: float) -> _HttpResponse:
    import aiohttp
    from aiohttp_socks import ProxyConnector

    connector = ProxyConnector.from_url(endpoint.url(include_credentials=True))
    start = time.perf_counter()
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout_cfg) as session:
        async with session.get(
            url, headers={"User-Agent": "ProxyAtlas/1.0 validator"}, ssl=False
        ) as resp:
            text = await resp.text()
            elapsed = (time.perf_counter() - start) * 1000.0
            return _HttpResponse(resp.status, text, {k: v for k, v in resp.headers.items()}, elapsed)


async def _proxied_get(endpoint: Endpoint, url: str, timeout: float) -> _HttpResponse:
    if endpoint.protocol == Protocol.SOCKS4:
        return await _aiohttp_socks_get(endpoint, url, timeout)
    return await _httpx_get(endpoint, url, timeout)


def _categorize(exc: Exception) -> tuple[ValidationStatus, str, str]:
    """Map an exception to (status, category, detail)."""
    name = type(exc).__name__
    text = str(exc).lower()
    if isinstance(exc, _AuthError):
        return ValidationStatus.AUTH_REQUIRED, "auth", str(exc)
    if isinstance(exc, (asyncio.TimeoutError,)) or "timeout" in text or "timed out" in text:
        return ValidationStatus.TIMEOUT, "timeout", "Operation timed out"
    if isinstance(exc, _ProtocolError) or "socks" in text or "handshake" in text or "protocol" in text:
        return ValidationStatus.FAILED, "protocol", str(exc)
    if "refused" in text or "connect" in text or "unreachable" in text or "reset" in text:
        return ValidationStatus.FAILED, "connect", str(exc)
    if "name" in text and "resolve" in text or "getaddrinfo" in text:
        return ValidationStatus.FAILED, "dns", str(exc)
    return ValidationStatus.FAILED, "unknown", f"{name}: {exc}"[:300]


# Failure categories that are worth retrying (transient); auth is terminal.
_RETRYABLE_CATEGORIES = {"timeout", "connect", "protocol", "unknown", "http_error", "no_exit_ip", "dns"}

# Order tried during protocol auto-detection, after the candidate's own protocol.
_AUTODETECT_ORDER = [Protocol.HTTP, Protocol.SOCKS5, Protocol.SOCKS4, Protocol.HTTPS]


async def validate_proxy(
    endpoint: Endpoint,
    profile: ValidationProfile,
    validation_endpoints: list[str],
    judge_endpoint: str | None = None,
    real_ip: str | None = None,
    retries: int = 0,
    retry_backoff: float = 0.0,
    protocols: list[Protocol] | None = None,
) -> ValidationResult:
    """Validate a single proxy. Never raises; always returns a result.

    ``retries``/``retry_backoff`` re-attempt transient failures (never turning a
    failure into a false WORKING — success still requires a real proxied request
    returning a valid exit IP). ``protocols``, when given, tries each protocol in
    order and returns the first that genuinely works, so a mislabeled candidate
    (e.g. a plain ``IP:PORT`` list) can still be identified.
    """
    attempt_protocols = protocols or [endpoint.protocol]
    last: ValidationResult | None = None
    for proto in attempt_protocols:
        candidate_ep = endpoint if proto == endpoint.protocol else _with_protocol(endpoint, proto)
        res = await _validate_with_retries(
            candidate_ep, profile, validation_endpoints, judge_endpoint, real_ip,
            retries, retry_backoff,
        )
        if res.status == ValidationStatus.WORKING:
            return res
        if res.status == ValidationStatus.AUTH_REQUIRED:
            # Auth is a definitive answer for this protocol; don't try others.
            return res
        last = res
    return last  # type: ignore[return-value]


def _with_protocol(endpoint: Endpoint, protocol: Protocol) -> Endpoint:
    return Endpoint(
        host=endpoint.host, port=endpoint.port, protocol=protocol,
        username=endpoint.username, password=endpoint.password,
    )


async def _validate_with_retries(
    endpoint: Endpoint,
    profile: ValidationProfile,
    validation_endpoints: list[str],
    judge_endpoint: str | None,
    real_ip: str | None,
    retries: int,
    retry_backoff: float,
) -> ValidationResult:
    attempts = max(1, retries + 1)
    result = ValidationResult(endpoint=endpoint, status=ValidationStatus.FAILED, tested_at=utcnow())
    for attempt in range(attempts):
        result = await _validate_single(
            endpoint, profile, validation_endpoints, judge_endpoint, real_ip
        )
        if result.status == ValidationStatus.WORKING:
            return result
        if result.status == ValidationStatus.AUTH_REQUIRED:
            return result
        if (result.error_category not in _RETRYABLE_CATEGORIES) or attempt == attempts - 1:
            return result
        if retry_backoff > 0:
            await asyncio.sleep(retry_backoff * (2 ** attempt))
    return result


async def _validate_single(
    endpoint: Endpoint,
    profile: ValidationProfile,
    validation_endpoints: list[str],
    judge_endpoint: str | None = None,
    real_ip: str | None = None,
) -> ValidationResult:
    """Perform one full validation attempt for a fixed endpoint/protocol."""
    result = ValidationResult(endpoint=endpoint, status=ValidationStatus.TESTING, tested_at=utcnow())
    timeout = profile.timeout

    # 1. Reachability (informational only — not sufficient for WORKING).
    if profile.check_connectivity:
        try:
            result.connect_time_ms = round(
                await _tcp_connect_time(endpoint.host, endpoint.port, timeout), 2
            )
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all
            status, category, detail = _categorize(exc)
            result.status = status
            result.error_category = category
            result.error_detail = detail
            return result

    # 2. Real proxied request(s). Exit-IP detection requires this even in Quick.
    endpoints = validation_endpoints or ["https://api.ipify.org?format=json"]
    samples = max(1, profile.repeated_requests)
    successes = 0
    latencies: list[float] = []
    last_error: tuple[ValidationStatus, str, str] | None = None
    exit_ip: str | None = None
    working_endpoint: str | None = None

    for _attempt in range(samples):
        got_success = False
        for url in endpoints:
            try:
                resp = await _proxied_get(endpoint, url, timeout)
            except Exception as exc:  # noqa: BLE001
                last_error = _categorize(exc)
                if last_error[0] == ValidationStatus.AUTH_REQUIRED:
                    result.status = ValidationStatus.AUTH_REQUIRED
                    result.error_category, result.error_detail = last_error[1], last_error[2]
                    result.samples = samples
                    result.successes = successes
                    return result
                continue
            if resp.status_code >= 400:
                last_error = (ValidationStatus.FAILED, "http_error", f"HTTP {resp.status_code}")
                continue
            ip = _extract_ip(resp.text)
            if ip is None:
                last_error = (ValidationStatus.FAILED, "no_exit_ip", "No IP in response")
                continue
            got_success = True
            successes += 1
            latencies.append(resp.elapsed_ms)
            exit_ip = exit_ip or ip
            working_endpoint = working_endpoint or url
            break
        if not got_success and samples == 1:
            break

    result.samples = samples
    result.successes = successes

    if successes == 0:
        status, category, detail = last_error or (
            ValidationStatus.FAILED,
            "unknown",
            "No successful proxied request",
        )
        result.status = status
        result.error_category = category
        result.error_detail = detail
        return result

    # Success!
    result.status = ValidationStatus.WORKING
    result.http_success = True
    result.exit_ip = exit_ip
    result.validation_endpoint = working_endpoint
    result.response_time_ms = round(min(latencies), 2) if latencies else None
    result.latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
    if endpoint.has_credentials:
        result.auth_ok = True

    # 3. Header / anonymity + DNS analysis via judge endpoint.
    if (profile.header_analysis or profile.dns_analysis) and judge_endpoint:
        try:
            judge = await _proxied_get(endpoint, judge_endpoint, timeout)
            echoed = _extract_echoed_headers(judge.text, judge.headers)
            result.raw_headers = {k: v for k, v in list(echoed.items())[:40]}
            if profile.header_analysis:
                anon, evidence = analyze_anonymity(echoed, exit_ip, real_ip)
                result.anonymity = anon
                result.anonymity_evidence = evidence
            if profile.dns_analysis:
                status, evidence, conf = analyze_dns(
                    request_succeeded=True,
                    exit_ip=exit_ip,
                    echoed_headers=echoed,
                    real_ip=real_ip,
                )
                result.dns_status = status
                result.dns_evidence = {**evidence, "confidence": conf}
        except Exception as exc:  # noqa: BLE001 - analysis is best-effort
            logger.debug("Judge request failed for %s: %s", endpoint.identity, exc)
            if result.anonymity == Anonymity.UNKNOWN and profile.header_analysis:
                result.anonymity = Anonymity.UNKNOWN
            if profile.dns_analysis and result.dns_status == DnsStatus.UNTESTED:
                result.dns_status = DnsStatus.UNTESTED

    return result


def _extract_echoed_headers(body: str, response_headers: dict[str, str]) -> dict[str, str]:
    """Pull request headers a judge endpoint echoes (httpbin-style)."""
    echoed: dict[str, str] = {}
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            hdrs = data.get("headers")
            if isinstance(hdrs, dict):
                echoed.update({str(k): str(v) for k, v in hdrs.items()})
            if data.get("origin"):
                echoed["origin"] = str(data["origin"])
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back to actual response headers for Via etc.
    for k, v in response_headers.items():
        echoed.setdefault(k, v)
    return echoed


async def detect_public_ip(validation_endpoints: list[str], timeout: float = 8.0) -> str | None:
    """Fetch this machine's public IP directly (no proxy) as a baseline."""
    import httpx

    for url in validation_endpoints or ["https://api.ipify.org?format=json"]:
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
                resp = await client.get(url)
            ip = _extract_ip(resp.text)
            if ip:
                return ip
        except Exception:  # noqa: BLE001
            continue
    return None
