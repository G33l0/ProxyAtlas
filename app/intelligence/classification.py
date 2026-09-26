"""Classify a proxy from real signals (hosting flags, ASN/ISP/org keywords,
mobile flag, reverse DNS). Weak evidence gives UNKNOWN with low confidence.
There's no "not datacenter therefore residential" shortcut.
"""

from __future__ import annotations

from app.core.enums import Classification
from app.core.models import ClassificationResult, IntelligenceResult
from app.intelligence.asn import (
    BUSINESS_KEYWORDS,
    DATACENTER_KEYWORDS,
    EDUCATIONAL_KEYWORDS,
    GOVERNMENT_KEYWORDS,
    ISP_KEYWORDS,
    MOBILE_KEYWORDS,
    match_keywords,
)


class NetworkClassifier:
    """Classify a proxy from its intelligence."""

    def classify(self, intel: IntelligenceResult) -> ClassificationResult:
        result = ClassificationResult()
        haystack = " ".join(
            filter(None, [intel.isp, intel.organization, intel.reverse_dns, intel.asn])
        )

        # Strongest signals first, each with explicit evidence.
        scores: dict[Classification, float] = {}

        # Government / educational are specific -> check first.
        gov = match_keywords(haystack, GOVERNMENT_KEYWORDS)
        if gov:
            scores[Classification.GOVERNMENT] = 0.8
            result.add_evidence(f"Government keywords: {', '.join(gov)}")

        edu = match_keywords(haystack, EDUCATIONAL_KEYWORDS)
        if edu:
            scores[Classification.EDUCATIONAL] = 0.8
            result.add_evidence(f"Educational keywords: {', '.join(edu)}")

        # Mobile: explicit provider flag is authoritative.
        if intel.evidence.get("mobile_flag"):
            scores[Classification.MOBILE] = 0.9
            result.add_evidence("Provider reports mobile network")
        mob = match_keywords(haystack, MOBILE_KEYWORDS)
        if mob:
            scores[Classification.MOBILE] = max(scores.get(Classification.MOBILE, 0), 0.7)
            result.add_evidence(f"Mobile carrier keywords: {', '.join(mob)}")

        # Datacenter / hosting.
        if intel.hosting is True:
            scores[Classification.DATACENTER] = 0.85
            result.add_evidence("Provider reports hosting/datacenter network")
        dc = match_keywords(haystack, DATACENTER_KEYWORDS)
        if dc:
            scores[Classification.DATACENTER] = max(scores.get(Classification.DATACENTER, 0), 0.75)
            result.add_evidence(f"Datacenter keywords: {', '.join(dc)}")

        # ISP (consumer broadband) - strong signal of residential-capable ISP.
        isp = match_keywords(haystack, ISP_KEYWORDS)
        if isp:
            scores[Classification.ISP] = 0.7
            result.add_evidence(f"ISP/broadband keywords: {', '.join(isp)}")

        # Business.
        biz = match_keywords(haystack, BUSINESS_KEYWORDS)
        if biz and not dc:
            scores[Classification.BUSINESS] = 0.55
            result.add_evidence(f"Business keywords: {', '.join(biz)}")

        # Residential: only when an ISP signal exists AND no hosting signal.
        if isp and intel.hosting is not True and not dc:
            scores[Classification.RESIDENTIAL] = 0.65
            result.add_evidence("Consumer ISP with no hosting indicators")

        if not scores:
            result.classification = Classification.UNKNOWN
            result.confidence = 0.1
            if not result.evidence:
                result.add_evidence("Insufficient network signals to classify")
            return result

        best = max(scores.items(), key=lambda kv: kv[1])
        result.classification = best[0]
        result.confidence = round(best[1], 2)
        return result


classifier = NetworkClassifier()
