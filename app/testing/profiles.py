"""Validation profiles controlling how deep a proxy is tested.

A :class:`ValidationProfile` is a set of feature flags plus tuning. Three
built-ins (Quick, Standard, Deep) are provided, and users may create custom
profiles which are persisted in settings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.enums import ValidationProfileName


@dataclass
class ValidationProfile:
    """Feature toggles for a validation run."""

    name: str = "standard"
    check_connectivity: bool = True
    detect_exit_ip: bool = True
    http_request: bool = True
    https_request: bool = False
    measure_latency: bool = True
    dns_analysis: bool = False
    header_analysis: bool = False
    repeated_requests: int = 1  # number of samples for reliability
    timeout: float = 12.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationProfile":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


def quick_profile(timeout: float = 8.0) -> ValidationProfile:
    return ValidationProfile(
        name=ValidationProfileName.QUICK.value,
        check_connectivity=True,
        detect_exit_ip=True,
        http_request=False,
        measure_latency=True,
        dns_analysis=False,
        header_analysis=False,
        repeated_requests=1,
        timeout=timeout,
    )


def standard_profile(timeout: float = 12.0) -> ValidationProfile:
    return ValidationProfile(
        name=ValidationProfileName.STANDARD.value,
        check_connectivity=True,
        detect_exit_ip=True,
        http_request=True,
        measure_latency=True,
        dns_analysis=True,
        header_analysis=True,
        repeated_requests=1,
        timeout=timeout,
    )


def deep_profile(timeout: float = 20.0) -> ValidationProfile:
    return ValidationProfile(
        name=ValidationProfileName.DEEP.value,
        check_connectivity=True,
        detect_exit_ip=True,
        http_request=True,
        https_request=True,
        measure_latency=True,
        dns_analysis=True,
        header_analysis=True,
        repeated_requests=3,
        timeout=timeout,
    )


BUILTIN_PROFILES: dict[str, ValidationProfile] = {
    ValidationProfileName.QUICK.value: quick_profile(),
    ValidationProfileName.STANDARD.value: standard_profile(),
    ValidationProfileName.DEEP.value: deep_profile(),
}


def get_profile(name: str, custom: dict[str, dict] | None = None) -> ValidationProfile:
    """Resolve a profile by name from built-ins or a custom dict."""
    if custom and name in custom:
        return ValidationProfile.from_dict(custom[name])
    return BUILTIN_PROFILES.get(name, BUILTIN_PROFILES["standard"])
