"""SQLAlchemy ORM models for ProxyAtlas.

The schema is normalized around a canonical :class:`Proxy` row (one per
``protocol://host:port`` identity) with satellite tables for credentials,
tests, history, monitoring, sources, jobs, geolocation, network identity,
exports, settings and an audit log.

All models use SQLAlchemy 2.0 typed declarative mapping. Timestamps are stored
timezone-aware in UTC. Indexes and a unique constraint on endpoint identity
prevent duplicate proxies.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Proxy(Base, TimestampMixin):
    """Canonical validated/known proxy endpoint."""

    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint("protocol", "host", "port", name="uq_proxy_identity"),
        Index("ix_proxy_status", "status"),
        Index("ix_proxy_classification", "classification"),
        Index("ix_proxy_country", "country_code"),
        Index("ix_proxy_protocol", "protocol"),
        Index("ix_proxy_score", "score"),
        Index("ix_proxy_last_checked", "last_checked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(16))

    credential_reference: Mapped[int | None] = mapped_column(
        ForeignKey("proxy_credentials.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(24), default="discovered")
    exit_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Intelligence
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    asn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    isp: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Classification
    classification: Mapped[str] = mapped_column(String(24), default="unknown")
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    classification_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Behaviour
    anonymity: Mapped[str] = mapped_column(String(16), default="unknown")
    dns_status: Mapped[str] = mapped_column(String(24), default="untested")

    # Quality metrics
    latency: Mapped[float | None] = mapped_column(Float, nullable=True)  # ms
    connect_latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability: Mapped[float] = mapped_column(Float, default=0.0)  # %
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    uptime: Mapped[float] = mapped_column(Float, default=0.0)  # %
    freshness: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_components: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    # Provenance
    source: Mapped[str] = mapped_column(String(120), default="unknown")
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated

    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    check_count: Mapped[int] = mapped_column(Integer, default=0)

    credential: Mapped[ProxyCredential | None] = relationship(
        "ProxyCredential", foreign_keys=[credential_reference]
    )
    tests: Mapped[list[ProxyTest]] = relationship(
        back_populates="proxy", cascade="all, delete-orphan"
    )
    history: Mapped[list[ProxyHistory]] = relationship(
        back_populates="proxy", cascade="all, delete-orphan"
    )

    @property
    def identity(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


class ProxyEndpoint(Base, TimestampMixin):
    """Raw discovery record for a proxy (may map to a canonical Proxy)."""

    __tablename__ = "proxy_endpoints"
    __table_args__ = (Index("ix_endpoint_identity", "protocol", "host", "port"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(16))
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )


class ProxyCredential(Base, TimestampMixin):
    """Encrypted credentials for a proxy. Never store plaintext."""

    __tablename__ = "proxy_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    username_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ProxyTest(Base):
    """A single validation test run against a proxy."""

    __tablename__ = "proxy_tests"
    __table_args__ = (Index("ix_test_proxy", "proxy_id", "tested_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey("proxies.id", ondelete="CASCADE"))
    profile: Mapped[str] = mapped_column(String(32), default="standard")
    status: Mapped[str] = mapped_column(String(24))
    connect_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    proxy: Mapped[Proxy] = relationship(back_populates="tests")
    results: Mapped[list[ProxyTestResult]] = relationship(
        back_populates="test", cascade="all, delete-orphan"
    )


class ProxyTestResult(Base):
    """A granular metric/result belonging to a :class:`ProxyTest`."""

    __tablename__ = "proxy_test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("proxy_tests.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(48))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    test: Mapped[ProxyTest] = relationship(back_populates="results")


class ProxyHistory(Base):
    """Time-series snapshots of a proxy for monitoring/history charts."""

    __tablename__ = "proxy_history"
    __table_args__ = (Index("ix_history_proxy", "proxy_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey("proxies.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24))
    latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(24), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    proxy: Mapped[Proxy] = relationship(back_populates="history")


class ProxySource(Base, TimestampMixin):
    """A configured discovery source."""

    __tablename__ = "proxy_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    source_type: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(64))
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryJob(Base, TimestampMixin):
    __tablename__ = "discovery_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxy_sources.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(16), default="queued")
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    total_new: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryResult(Base):
    """A discovered candidate in the discovery queue (pre-validation)."""

    __tablename__ = "discovery_results"
    __table_args__ = (
        UniqueConstraint("protocol", "host", "port", name="uq_discovery_identity"),
        Index("ix_discovery_status", "validation_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(120), default="unknown")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credentials_available: Mapped[bool] = mapped_column(Boolean, default=False)
    username_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(24), default="discovered")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitoringJob(Base, TimestampMixin):
    __tablename__ = "monitoring_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(24), default="collection")  # collection|filter|proxy
    target_ref: Mapped[str | None] = mapped_column(Text, nullable=True)  # collection id or filter json
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MonitoringResult(Base):
    __tablename__ = "monitoring_results"
    __table_args__ = (Index("ix_monitoring_job", "job_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("monitoring_jobs.id", ondelete="CASCADE"))
    total: Mapped[int] = mapped_column(Integer, default=0)
    working: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NetworkIdentity(Base, TimestampMixin):
    """Cached ASN/ISP/org intelligence keyed by IP."""

    __tablename__ = "network_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    asn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    isp: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hosting: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reverse_dns: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)


class GeoLocation(Base, TimestampMixin):
    """Cached geolocation intelligence keyed by IP."""

    __tablename__ = "geo_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ApplicationSetting(Base, TimestampMixin):
    """Key/value settings persisted in the DB (collections, saved filters)."""

    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")


class ExportJob(Base, TimestampMixin):
    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    fmt: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(Text)
    filter_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16), default="completed")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


ALL_MODELS = [
    Proxy, ProxyEndpoint, ProxyCredential, ProxyTest, ProxyTestResult, ProxyHistory,
    ProxySource, DiscoveryJob, DiscoveryResult, MonitoringJob, MonitoringResult,
    NetworkIdentity, GeoLocation, ApplicationSetting, ExportJob, AuditLog,
]
