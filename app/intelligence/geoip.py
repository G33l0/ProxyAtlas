"""Geo helpers: private/reserved range detection and country utilities."""

from __future__ import annotations

import ipaddress

# Minimal offline country code -> name table for common cases; online providers
# fill in the rest. Kept small on purpose (not a full GeoIP DB).
COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany", "FR": "France",
    "NL": "Netherlands", "CA": "Canada", "RU": "Russia", "CN": "China", "IN": "India",
    "BR": "Brazil", "NG": "Nigeria", "ZA": "South Africa", "JP": "Japan", "KR": "South Korea",
    "SG": "Singapore", "AU": "Australia", "ES": "Spain", "IT": "Italy", "SE": "Sweden",
    "PL": "Poland", "UA": "Ukraine", "TR": "Turkey", "MX": "Mexico", "ID": "Indonesia",
    "VN": "Vietnam", "TH": "Thailand", "AE": "United Arab Emirates", "EG": "Egypt",
}


def is_private_or_reserved(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_reserved
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
    )


def country_name(code: str | None) -> str | None:
    if not code:
        return None
    return COUNTRY_NAMES.get(code.upper(), code.upper())
