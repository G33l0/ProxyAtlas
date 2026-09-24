"""Internet Discovery provider.

Generates proxy *candidates* across user-configured, authorized/publicly
intended address space (explicit CIDR ranges) combined with a configurable list
of common proxy ports. It performs **no validation** itself — every candidate
enters the standard validation pipeline like any other source. Generation is
bounded by ``max_candidates`` to keep jobs controlled, and reserved/private
ranges are skipped.

This is deliberately implemented as a provider/module so additional discovery
techniques can be added later without touching the core engine.
"""

from __future__ import annotations

import ipaddress
import random
from collections.abc import AsyncIterator
from typing import Any

from app.core.enums import Protocol, SourceType
from app.core.models import Endpoint, ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.normalizer import candidate_from_endpoint
from app.intelligence.geoip import is_private_or_reserved

# Common proxy ports mapped to a protocol guess (validation confirms reality).
DEFAULT_PORT_PROTOCOLS: dict[int, Protocol] = {
    80: Protocol.HTTP,
    8080: Protocol.HTTP,
    3128: Protocol.HTTP,
    8000: Protocol.HTTP,
    8888: Protocol.HTTP,
    8118: Protocol.HTTP,
    443: Protocol.HTTPS,
    8443: Protocol.HTTPS,
    1080: Protocol.SOCKS5,
    1081: Protocol.SOCKS5,
    9050: Protocol.SOCKS5,
    4145: Protocol.SOCKS4,
}


class InternetDiscoveryProvider(DiscoveryProvider):
    source_type = SourceType.INTERNET

    def name(self) -> str:
        return self._config.get("name", "internet-discovery")

    def description(self) -> str:
        return (
            "Generate proxy candidates across authorized CIDR ranges and common "
            "proxy ports; all candidates enter the standard validation pipeline."
        )

    def config_schema(self) -> dict[str, Any]:
        return {
            "cidrs": {"type": "textarea", "label": "Target CIDR ranges (one per line)", "required": True},
            "ports": {"type": "text", "label": "Ports (comma separated)"},
            "max_candidates": {"type": "number", "label": "Max candidates"},
            "shuffle": {"type": "bool", "label": "Randomize host order"},
            "profile": {"type": "text", "label": "Discovery profile label"},
        }

    def validate_configuration(self) -> tuple[bool, str]:
        cidrs = self._parse_cidrs()
        if not cidrs:
            return False, "At least one valid CIDR range is required"
        total_hosts = sum(net.num_addresses for net in cidrs)
        if total_hosts > 5_000_000:
            return False, "Target space too large; narrow the CIDR ranges"
        return True, f"{len(cidrs)} range(s), up to {self._max_candidates()} candidates"

    def _parse_cidrs(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        raw = self._config.get("cidrs") or ""
        if isinstance(raw, list):
            entries = raw
        else:
            entries = str(raw).replace(",", "\n").splitlines()
        nets = []
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            try:
                nets.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                continue
        return nets

    def _ports(self) -> list[int]:
        raw = self._config.get("ports")
        if not raw:
            return list(DEFAULT_PORT_PROTOCOLS.keys())
        ports = []
        for tok in str(raw).replace(" ", "").split(","):
            if tok.isdigit() and 1 <= int(tok) <= 65535:
                ports.append(int(tok))
        return ports or list(DEFAULT_PORT_PROTOCOLS.keys())

    def _max_candidates(self) -> int:
        try:
            return max(1, min(200_000, int(self._config.get("max_candidates", 2000))))
        except (TypeError, ValueError):
            return 2000

    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        nets = self._parse_cidrs()
        ports = self._ports()
        max_candidates = self._max_candidates()
        shuffle = bool(self._config.get("shuffle", True))
        profile = self._config.get("profile", "default")
        source = self.name()

        hosts: list[str] = []
        for net in nets:
            for addr in net.hosts():
                ip = str(addr)
                if is_private_or_reserved(ip):
                    continue
                hosts.append(ip)
                if len(hosts) >= max_candidates:
                    break
            if len(hosts) >= max_candidates:
                break

        if shuffle:
            random.shuffle(hosts)

        emitted = 0
        for ip in hosts:
            for port in ports:
                if emitted >= max_candidates:
                    return
                protocol = DEFAULT_PORT_PROTOCOLS.get(port, Protocol.HTTP)
                endpoint = Endpoint(host=ip, port=port, protocol=protocol)
                cand = candidate_from_endpoint(endpoint, source, source_reference=f"scan:{profile}")
                cand.metadata["discovery_profile"] = profile
                cand.metadata["generated"] = True
                emitted += 1
                yield cand
