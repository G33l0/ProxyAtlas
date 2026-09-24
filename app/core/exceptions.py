"""Structured exception hierarchy for ProxyAtlas."""

from __future__ import annotations


class ProxyAtlasError(Exception):
    """Base class for all application-specific errors."""


class ConfigurationError(ProxyAtlasError):
    """Raised when configuration is missing or invalid."""


class DatabaseError(ProxyAtlasError):
    """Raised for database-level failures."""


class ParseError(ProxyAtlasError):
    """Raised when a proxy record cannot be parsed."""


class ValidationError(ProxyAtlasError):
    """Raised for validation-pipeline failures that are not per-proxy."""


class ProviderError(ProxyAtlasError):
    """Raised when a discovery/intelligence provider fails."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider is misconfigured."""


class DiscoveryError(ProxyAtlasError):
    """Raised for discovery-engine failures."""


class ExportError(ProxyAtlasError):
    """Raised when an export/report cannot be produced."""


class SecurityError(ProxyAtlasError):
    """Raised for credential / crypto failures."""
