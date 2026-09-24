"""Tests for quality scoring and classification."""

from datetime import datetime, timezone

from app.core.enums import Classification, ValidationStatus
from app.core.models import IntelligenceResult
from app.intelligence.classification import classifier
from app.proxy.quality import compute_quality


def test_quality_working_high():
    q = compute_quality(
        status=ValidationStatus.WORKING, latency_ms=90, reliability=100,
        success_count=10, failure_count=0, samples=3, successes=3,
        last_success_at=datetime.now(timezone.utc),
    )
    assert q.score > 90
    assert set(q.components) == {"connectivity", "latency", "reliability", "stability", "freshness"}


def test_quality_failed_capped():
    q = compute_quality(
        status=ValidationStatus.FAILED, latency_ms=None, reliability=0,
        success_count=0, failure_count=5,
    )
    assert q.score <= 20
    assert q.components["connectivity"] == 0.0


def test_classify_datacenter():
    intel = IntelligenceResult("1.1.1.1", isp="Amazon", organization="AWS EC2", hosting=True)
    res = classifier.classify(intel)
    assert res.classification == Classification.DATACENTER
    assert res.confidence > 0.5
    assert res.evidence


def test_classify_mobile_flag():
    intel = IntelligenceResult("2.2.2.2", isp="MTN", evidence={"mobile_flag": True})
    assert classifier.classify(intel).classification == Classification.MOBILE


def test_classify_unknown_when_no_signal():
    res = classifier.classify(IntelligenceResult("3.3.3.3"))
    assert res.classification == Classification.UNKNOWN
    assert res.confidence < 0.3


def test_no_naive_residential_fallback():
    # Datacenter signal must never become residential.
    intel = IntelligenceResult("4.4.4.4", organization="DigitalOcean", hosting=True)
    assert classifier.classify(intel).classification != Classification.RESIDENTIAL
