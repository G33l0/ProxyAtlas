"""All DB access lives here. Functions take a Session so the caller owns the
transaction; services wrap them in db.session(). Proxies dedupe on
protocol/host/port.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import Anonymity, Classification, DnsStatus, Protocol, ValidationStatus
from app.core.models import (
    ClassificationResult,
    Endpoint,
    IntelligenceResult,
    ProxyCandidate,
    QualityScore,
    ValidationResult,
)
from app.database.filters import FilterSpec
from app.database.models import (
    ApplicationSetting,
    AuditLog,
    DiscoveryResult,
    ExportJob,
    GeoLocation,
    MonitoringJob,
    MonitoringResult,
    NetworkIdentity,
    Proxy,
    ProxyCredential,
    ProxyHistory,
    ProxySource,
    ProxyTest,
)

SORTABLE_COLUMNS = {
    "host": Proxy.host,
    "port": Proxy.port,
    "protocol": Proxy.protocol,
    "status": Proxy.status,
    "exit_ip": Proxy.exit_ip,
    "country": Proxy.country,
    "region": Proxy.region,
    "isp": Proxy.isp,
    "asn": Proxy.asn,
    "classification": Proxy.classification,
    "anonymity": Proxy.anonymity,
    "latency": Proxy.latency,
    "reliability": Proxy.reliability,
    "uptime": Proxy.uptime,
    "score": Proxy.score,
    "last_checked_at": Proxy.last_checked_at,
    "source": Proxy.source,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Audit
def add_audit(session: Session, action: str, detail: str | None = None) -> None:
    session.add(AuditLog(action=action, detail=detail))


# Proxy upsert / query
def get_proxy_by_identity(session: Session, endpoint: Endpoint) -> Proxy | None:
    stmt = select(Proxy).where(
        Proxy.protocol == endpoint.protocol.value,
        Proxy.host == endpoint.host,
        Proxy.port == endpoint.port,
    )
    return session.scalars(stmt).first()


def delete_proxies_at_hostport_except(
    session: Session, host: str, port: int, keep_protocol: str
) -> int:
    """Delete proxy rows at (host, port) whose protocol differs from
    `keep_protocol`.

    A single host:port socket speaks one protocol, so when auto-detection
    corrects a mislabeled proxy the stale other-protocol row must be removed
    rather than left behind as a duplicate.
    """
    stmt = select(Proxy).where(
        Proxy.host == host, Proxy.port == port, Proxy.protocol != keep_protocol
    )
    rows = list(session.scalars(stmt).all())
    for row in rows:
        session.delete(row)
    return len(rows)


def upsert_proxy_from_candidate(
    session: Session, candidate: ProxyCandidate, cipher=None
) -> Proxy:
    """Insert or fetch a canonical proxy for a discovered candidate."""
    proxy = get_proxy_by_identity(session, candidate.endpoint)
    if proxy is None:
        proxy = Proxy(
            host=candidate.endpoint.host,
            port=candidate.endpoint.port,
            protocol=candidate.endpoint.protocol.value,
            status=ValidationStatus.DISCOVERED.value,
            source=candidate.source,
            discovered_at=candidate.discovered_at,
        )
        session.add(proxy)
        session.flush()
    if candidate.endpoint.has_credentials and cipher is not None:
        _attach_credentials(session, proxy, candidate.endpoint, cipher)
    return proxy


def _attach_credentials(session: Session, proxy: Proxy, endpoint: Endpoint, cipher) -> None:
    cred = ProxyCredential(
        username_enc=cipher.encrypt(endpoint.username),
        password_enc=cipher.encrypt(endpoint.password),
    )
    session.add(cred)
    session.flush()
    proxy.credential_reference = cred.id


def apply_validation_result(
    session: Session, proxy: Proxy, result: ValidationResult, profile: str = "standard"
) -> ProxyTest:
    """Update a proxy from a validation result and record the test + history."""
    proxy.status = result.status.value
    proxy.last_checked_at = result.tested_at
    proxy.check_count = (proxy.check_count or 0) + 1

    if result.exit_ip:
        proxy.exit_ip = result.exit_ip
    if result.latency_ms is not None:
        proxy.latency = round(result.latency_ms, 2)
    if result.connect_time_ms is not None:
        proxy.connect_latency = round(result.connect_time_ms, 2)
    # don't let a lighter re-check clobber a good anonymity/DNS reading
    if result.anonymity != Anonymity.UNKNOWN:
        proxy.anonymity = result.anonymity.value
    if result.dns_status != DnsStatus.UNTESTED:
        proxy.dns_status = result.dns_status.value

    if result.ok:
        proxy.success_count = (proxy.success_count or 0) + 1
        proxy.last_success_at = result.tested_at
    else:
        proxy.failure_count = (proxy.failure_count or 0) + 1
        proxy.last_failure_at = result.tested_at

    total = (proxy.success_count or 0) + (proxy.failure_count or 0)
    proxy.uptime = round(100.0 * (proxy.success_count or 0) / total, 2) if total else 0.0
    # Reliability from this run's repeated samples (deep profile), fallback to uptime.
    proxy.reliability = result.reliability if result.samples > 1 else proxy.uptime

    test = ProxyTest(
        proxy_id=proxy.id,
        profile=profile,
        status=result.status.value,
        connect_time_ms=result.connect_time_ms,
        response_time_ms=result.response_time_ms,
        exit_ip=result.exit_ip,
        validation_endpoint=result.validation_endpoint,
        error_category=result.error_category,
        error_detail=result.error_detail,
        tested_at=result.tested_at,
    )
    session.add(test)
    session.add(
        ProxyHistory(
            proxy_id=proxy.id,
            status=result.status.value,
            latency=proxy.latency,
            exit_ip=proxy.exit_ip,
            classification=proxy.classification,
            recorded_at=result.tested_at,
        )
    )
    return test


def apply_intelligence(session: Session, proxy: Proxy, intel: IntelligenceResult) -> None:
    proxy.country = intel.country or proxy.country
    proxy.country_code = intel.country_code or proxy.country_code
    proxy.region = intel.region or proxy.region
    proxy.city = intel.city or proxy.city
    proxy.timezone = intel.timezone or proxy.timezone
    proxy.latitude = intel.latitude if intel.latitude is not None else proxy.latitude
    proxy.longitude = intel.longitude if intel.longitude is not None else proxy.longitude
    proxy.asn = intel.asn or proxy.asn
    proxy.isp = intel.isp or proxy.isp
    proxy.organization = intel.organization or proxy.organization


def apply_classification(
    session: Session, proxy: Proxy, cls: ClassificationResult
) -> None:
    proxy.classification = cls.classification.value
    proxy.classification_confidence = round(cls.confidence, 2)
    proxy.classification_evidence = json.dumps(cls.evidence)


def apply_quality(session: Session, proxy: Proxy, quality: QualityScore) -> None:
    proxy.score = round(quality.score, 2)
    proxy.score_components = json.dumps(quality.components)
    if "stability" in quality.components:
        proxy.stability = round(quality.components["stability"], 2)
    if "freshness" in quality.components:
        proxy.freshness = round(quality.components["freshness"], 2)


def query_proxies(
    session: Session,
    spec: FilterSpec | None = None,
    *,
    sort_by: str = "score",
    descending: bool = True,
    limit: int | None = None,
    offset: int = 0,
) -> list[Proxy]:
    stmt = select(Proxy)
    if spec is not None:
        expr = spec.to_expression()
        if expr is not None:
            stmt = stmt.where(expr)
    col = SORTABLE_COLUMNS.get(sort_by, Proxy.score)
    stmt = stmt.order_by(col.desc() if descending else col.asc(), Proxy.id.asc())
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


def count_proxies(session: Session, spec: FilterSpec | None = None) -> int:
    stmt = select(func.count(Proxy.id))
    if spec is not None:
        expr = spec.to_expression()
        if expr is not None:
            stmt = stmt.where(expr)
    return int(session.scalar(stmt) or 0)


def get_proxy(session: Session, proxy_id: int) -> Proxy | None:
    return session.get(Proxy, proxy_id)


def delete_proxies(session: Session, ids: Sequence[int]) -> int:
    count = 0
    for pid in ids:
        obj = session.get(Proxy, pid)
        if obj is not None:
            session.delete(obj)
            count += 1
    return count


def add_tag(session: Session, proxy_id: int, tag: str) -> None:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return
    tags = {t.strip() for t in (proxy.tags or "").split(",") if t.strip()}
    tags.add(tag.strip())
    proxy.tags = ",".join(sorted(tags))


def get_credentials(session: Session, proxy: Proxy, cipher) -> tuple[str | None, str | None]:
    if not proxy.credential_reference:
        return None, None
    cred = session.get(ProxyCredential, proxy.credential_reference)
    if cred is None:
        return None, None
    return cipher.decrypt(cred.username_enc), cipher.decrypt(cred.password_enc)


# Discovery result queue
def add_discovery_candidate(
    session: Session, candidate: ProxyCandidate, cipher=None
) -> tuple[DiscoveryResult, bool]:
    """Insert a candidate into the discovery queue. Returns (row, is_new)."""
    ep = candidate.endpoint
    existing = session.scalars(
        select(DiscoveryResult).where(
            DiscoveryResult.protocol == ep.protocol.value,
            DiscoveryResult.host == ep.host,
            DiscoveryResult.port == ep.port,
        )
    ).first()
    if existing is not None:
        return existing, False
    row = DiscoveryResult(
        host=ep.host,
        port=ep.port,
        protocol=ep.protocol.value,
        source=candidate.source,
        source_reference=candidate.source_reference,
        credentials_available=ep.has_credentials,
        username_enc=cipher.encrypt(ep.username) if (ep.has_credentials and cipher) else None,
        password_enc=cipher.encrypt(ep.password) if (ep.has_credentials and cipher) else None,
        validation_status=candidate.validation_status.value,
        discovered_at=candidate.discovered_at,
        meta_json=json.dumps(candidate.metadata) if candidate.metadata else None,
    )
    session.add(row)
    return row, True


def list_discovery_results(
    session: Session, status: str | None = None, limit: int | None = None
) -> list[DiscoveryResult]:
    stmt = select(DiscoveryResult).order_by(DiscoveryResult.discovered_at.desc())
    if status:
        stmt = stmt.where(DiscoveryResult.validation_status == status)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def discovery_result_to_candidate(row: DiscoveryResult, cipher=None) -> ProxyCandidate:
    username = cipher.decrypt(row.username_enc) if (row.username_enc and cipher) else None
    password = cipher.decrypt(row.password_enc) if (row.password_enc and cipher) else None
    endpoint = Endpoint(
        host=row.host,
        port=row.port,
        protocol=Protocol.from_value(row.protocol, Protocol.HTTP),
        username=username,
        password=password,
    )
    return ProxyCandidate(
        endpoint=endpoint,
        source=row.source,
        source_reference=row.source_reference,
        discovered_at=row.discovered_at,
        validation_status=ValidationStatus.from_value(
            row.validation_status, ValidationStatus.DISCOVERED
        ),
    )


def update_discovery_status(session: Session, row_id: int, status: str) -> None:
    row = session.get(DiscoveryResult, row_id)
    if row is not None:
        row.validation_status = status


def delete_discovery_results(session: Session, ids: Sequence[int]) -> int:
    count = 0
    for rid in ids:
        row = session.get(DiscoveryResult, rid)
        if row is not None:
            session.delete(row)
            count += 1
    return count


def clear_discovery_results(session: Session) -> int:
    rows = list(session.scalars(select(DiscoveryResult)).all())
    for r in rows:
        session.delete(r)
    return len(rows)


# Sources
def list_sources(session: Session) -> list[ProxySource]:
    return list(session.scalars(select(ProxySource).order_by(ProxySource.name)).all())


def get_source(session: Session, source_id: int) -> ProxySource | None:
    return session.get(ProxySource, source_id)


def upsert_source(
    session: Session,
    name: str,
    source_type: str,
    provider: str,
    config: dict[str, Any],
    enabled: bool = True,
    source_id: int | None = None,
) -> ProxySource:
    src = session.get(ProxySource, source_id) if source_id else None
    if src is None:
        src = ProxySource(name=name)
        session.add(src)
    src.name = name
    src.source_type = source_type
    src.provider = provider
    src.config_json = json.dumps(config)
    src.enabled = enabled
    session.flush()
    return src


def delete_source(session: Session, source_id: int) -> None:
    src = session.get(ProxySource, source_id)
    if src is not None:
        session.delete(src)


# Collections and saved filters (stored in ApplicationSetting)
def _get_setting(session: Session, key: str, default: Any) -> Any:
    row = session.scalars(
        select(ApplicationSetting).where(ApplicationSetting.key == key)
    ).first()
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except json.JSONDecodeError:
        return default


def _set_setting(session: Session, key: str, value: Any) -> None:
    row = session.scalars(
        select(ApplicationSetting).where(ApplicationSetting.key == key)
    ).first()
    if row is None:
        row = ApplicationSetting(key=key)
        session.add(row)
    row.value_json = json.dumps(value)


def list_collections(session: Session) -> list[dict[str, Any]]:
    return _get_setting(session, "collections", [])


def save_collection(session: Session, name: str, spec: FilterSpec) -> None:
    collections = list_collections(session)
    collections = [c for c in collections if c.get("name") != name]
    collections.append({"name": name, "filter": spec.to_dict()})
    _set_setting(session, "collections", collections)


def delete_collection(session: Session, name: str) -> None:
    collections = [c for c in list_collections(session) if c.get("name") != name]
    _set_setting(session, "collections", collections)


def list_saved_filters(session: Session) -> list[dict[str, Any]]:
    return _get_setting(session, "saved_filters", [])


def save_filter(session: Session, name: str, spec: FilterSpec) -> None:
    filters = [f for f in list_saved_filters(session) if f.get("name") != name]
    filters.append({"name": name, "filter": spec.to_dict()})
    _set_setting(session, "saved_filters", filters)


def delete_saved_filter(session: Session, name: str) -> None:
    filters = [f for f in list_saved_filters(session) if f.get("name") != name]
    _set_setting(session, "saved_filters", filters)


# Monitoring
def list_monitoring_jobs(session: Session) -> list[MonitoringJob]:
    return list(session.scalars(select(MonitoringJob).order_by(MonitoringJob.name)).all())


def upsert_monitoring_job(
    session: Session,
    name: str,
    target_type: str,
    target_ref: str,
    interval_minutes: int,
    enabled: bool = True,
    job_id: int | None = None,
) -> MonitoringJob:
    job = session.get(MonitoringJob, job_id) if job_id else None
    if job is None:
        job = MonitoringJob(name=name)
        session.add(job)
    job.name = name
    job.target_type = target_type
    job.target_ref = target_ref
    job.interval_minutes = interval_minutes
    job.enabled = enabled
    session.flush()
    return job


def delete_monitoring_job(session: Session, job_id: int) -> None:
    job = session.get(MonitoringJob, job_id)
    if job is not None:
        session.delete(job)


def record_monitoring_result(
    session: Session, job_id: int, total: int, working: int, failed: int, avg_latency: float | None
) -> MonitoringResult:
    res = MonitoringResult(
        job_id=job_id, total=total, working=working, failed=failed, avg_latency=avg_latency
    )
    session.add(res)
    job = session.get(MonitoringJob, job_id)
    if job is not None:
        job.last_run_at = _utcnow()
        job.next_run_at = _utcnow() + timedelta(minutes=job.interval_minutes)
    return res


def monitoring_history(session: Session, job_id: int, limit: int = 200) -> list[MonitoringResult]:
    stmt = (
        select(MonitoringResult)
        .where(MonitoringResult.job_id == job_id)
        .order_by(MonitoringResult.recorded_at.desc())
        .limit(limit)
    )
    return list(reversed(session.scalars(stmt).all()))


def proxy_history(session: Session, proxy_id: int, limit: int = 200) -> list[ProxyHistory]:
    stmt = (
        select(ProxyHistory)
        .where(ProxyHistory.proxy_id == proxy_id)
        .order_by(ProxyHistory.recorded_at.desc())
        .limit(limit)
    )
    return list(reversed(session.scalars(stmt).all()))


def proxy_tests(session: Session, proxy_id: int, limit: int = 50) -> list[ProxyTest]:
    stmt = (
        select(ProxyTest)
        .where(ProxyTest.proxy_id == proxy_id)
        .order_by(ProxyTest.tested_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


# Intelligence caches
def get_cached_geo(session: Session, ip: str) -> GeoLocation | None:
    return session.scalars(select(GeoLocation).where(GeoLocation.ip == ip)).first()


def cache_geo(session: Session, intel: IntelligenceResult) -> None:
    row = get_cached_geo(session, intel.ip)
    if row is None:
        row = GeoLocation(ip=intel.ip)
        session.add(row)
    row.country = intel.country
    row.country_code = intel.country_code
    row.region = intel.region
    row.city = intel.city
    row.latitude = intel.latitude
    row.longitude = intel.longitude
    row.timezone = intel.timezone
    row.provider = intel.provider


def get_cached_network(session: Session, ip: str) -> NetworkIdentity | None:
    return session.scalars(select(NetworkIdentity).where(NetworkIdentity.ip == ip)).first()


def cache_network(session: Session, intel: IntelligenceResult) -> None:
    row = get_cached_network(session, intel.ip)
    if row is None:
        row = NetworkIdentity(ip=intel.ip)
        session.add(row)
    row.asn = intel.asn
    row.isp = intel.isp
    row.organization = intel.organization
    row.hosting = intel.hosting
    row.reverse_dns = intel.reverse_dns
    row.provider = intel.provider


# Export jobs
def record_export(
    session: Session, fmt: str, path: str, count: int, filter_json: str | None
) -> ExportJob:
    job = ExportJob(fmt=fmt, path=path, record_count=count, filter_json=filter_json)
    session.add(job)
    return job


# Dashboard / statistics
def dashboard_stats(session: Session) -> dict[str, Any]:
    total = count_proxies(session)
    working = int(
        session.scalar(
            select(func.count(Proxy.id)).where(Proxy.status == ValidationStatus.WORKING.value)
        )
        or 0
    )
    avg_latency = session.scalar(
        select(func.avg(Proxy.latency)).where(Proxy.status == ValidationStatus.WORKING.value)
    )
    avg_reliability = session.scalar(select(func.avg(Proxy.reliability)).where(Proxy.check_count > 0))

    by_classification = dict(
        session.execute(
            select(Proxy.classification, func.count(Proxy.id)).group_by(Proxy.classification)
        ).all()
    )
    by_protocol = dict(
        session.execute(
            select(Proxy.protocol, func.count(Proxy.id)).group_by(Proxy.protocol)
        ).all()
    )
    by_country = dict(
        session.execute(
            select(Proxy.country_code, func.count(Proxy.id))
            .where(Proxy.country_code.is_not(None))
            .group_by(Proxy.country_code)
            .order_by(func.count(Proxy.id).desc())
            .limit(12)
        ).all()
    )
    by_status = dict(
        session.execute(
            select(Proxy.status, func.count(Proxy.id)).group_by(Proxy.status)
        ).all()
    )
    return {
        "total": total,
        "working": working,
        "avg_latency": round(float(avg_latency), 1) if avg_latency else 0.0,
        "avg_reliability": round(float(avg_reliability), 1) if avg_reliability else 0.0,
        "by_classification": by_classification,
        "by_protocol": by_protocol,
        "by_country": by_country,
        "by_status": by_status,
        "residential": by_classification.get(Classification.RESIDENTIAL.value, 0),
        "mobile": by_classification.get(Classification.MOBILE.value, 0),
        "datacenter": by_classification.get(Classification.DATACENTER.value, 0),
        "isp": by_classification.get(Classification.ISP.value, 0),
        "unknown": by_classification.get(Classification.UNKNOWN.value, 0),
    }


def recent_activity(session: Session, limit: int = 8) -> dict[str, list[Proxy]]:
    latest_discovered = list(
        session.scalars(select(Proxy).order_by(Proxy.discovered_at.desc()).limit(limit)).all()
    )
    latest_working = list(
        session.scalars(
            select(Proxy)
            .where(Proxy.status == ValidationStatus.WORKING.value)
            .order_by(Proxy.last_success_at.desc())
            .limit(limit)
        ).all()
    )
    latest_failed = list(
        session.scalars(
            select(Proxy)
            .where(Proxy.last_failure_at.is_not(None))
            .order_by(Proxy.last_failure_at.desc())
            .limit(limit)
        ).all()
    )
    return {
        "discovered": latest_discovered,
        "working": latest_working,
        "failed": latest_failed,
    }


def latency_buckets(session: Session) -> dict[str, int]:
    working = list(
        session.scalars(
            select(Proxy.latency).where(
                Proxy.status == ValidationStatus.WORKING.value, Proxy.latency.is_not(None)
            )
        ).all()
    )
    buckets = {"<200ms": 0, "200-500ms": 0, "500ms-1s": 0, ">1s": 0}
    for lat in working:
        if lat < 200:
            buckets["<200ms"] += 1
        elif lat < 500:
            buckets["200-500ms"] += 1
        elif lat < 1000:
            buckets["500ms-1s"] += 1
        else:
            buckets[">1s"] += 1
    return buckets
