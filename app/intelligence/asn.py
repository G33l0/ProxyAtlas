"""ASN helpers and keyword tables used for classification."""

from __future__ import annotations

import re

_ASN_RE = re.compile(r"AS?(\d+)", re.IGNORECASE)

# Well-known hosting / datacenter operators (by org/ISP keyword).
DATACENTER_KEYWORDS = [
    "amazon", "aws", "ec2", "google", "gcp", "microsoft", "azure", "digitalocean",
    "linode", "akamai", "cloudflare", "ovh", "hetzner", "vultr", "leaseweb",
    "contabo", "hostwinds", "choopa", "scaleway", "oracle cloud", "alibaba",
    "tencent", "datacamp", "m247", "colocrossing", "quadranet", "psychz",
    "hosting", "datacenter", "data center", "server", "cloud", "vps", "dedicated",
]

MOBILE_KEYWORDS = [
    "mobile", "wireless", "cellular", "lte", "gsm", "telecom", "mtn", "airtel",
    "vodafone", "orange", "t-mobile", "verizon wireless", "at&t mobility",
    "glo", "9mobile", "safaricom", "jio", "reliance", "china mobile", "china unicom",
]

ISP_KEYWORDS = [
    "comcast", "spectrum", "charter", "at&t", "verizon", "centurylink", "cox",
    "bt ", "sky", "telstra", "bell", "rogers", "telus", "deutsche telekom",
    "telefonica", "telecom italia", "kpn", "swisscom", "telenor", "broadband",
    "cable", "fiber", "dsl", "communications",
]

EDUCATIONAL_KEYWORDS = [
    "university", "college", "school", "institute", "academ", "education",
    "polytechnic", ".edu", "campus", "research and education",
]

GOVERNMENT_KEYWORDS = [
    "government", "ministry", "municipal", "federal", "state of", "department of",
    "national", "gov", "administration", "council", "public sector",
]

BUSINESS_KEYWORDS = [
    "corp", "corporation", "inc", "ltd", "llc", "gmbh", "enterprise", "solutions",
    "technolog", "systems", "consult", "services", "group", "holdings",
]


def normalize_asn(value: str | None) -> str | None:
    if not value:
        return None
    m = _ASN_RE.search(str(value))
    if m:
        return f"AS{m.group(1)}"
    return str(value).strip() or None


def match_keywords(text: str | None, keywords: list[str]) -> list[str]:
    if not text:
        return []
    low = text.lower()
    return [kw for kw in keywords if kw in low]
