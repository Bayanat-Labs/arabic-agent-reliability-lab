"""Filesystem and local-network settings."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("BARL_ROOT", PACKAGE_ROOT.parents[1])).resolve()
SCENARIO_ROOT = Path(os.environ.get("BARL_SCENARIOS", REPO_ROOT / "scenarios")).resolve()
ARTIFACT_ROOT = Path(os.environ.get("BARL_ARTIFACTS", REPO_ROOT / "artifacts")).resolve()
DEFAULT_SUITE = SCENARIO_ROOT / "open" / "v0.json"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765


def ensure_runtime_directories() -> None:
    """Create the two repository-owned artifact directories."""

    (ARTIFACT_ROOT / "runs").mkdir(parents=True, exist_ok=True)
    (ARTIFACT_ROOT / "passports").mkdir(parents=True, exist_ok=True)


def require_loopback_url(value: str) -> str:
    """Reject non-loopback service URLs so benchmark execution stays local."""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid local service URL: {value!r}")
    host = parsed.hostname.lower()
    if host == "localhost":
        return value.rstrip("/")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(f"Service host must be loopback, got {host!r}") from exc
    if not address.is_loopback:
        raise ValueError(f"Service host must be loopback, got {host!r}")
    return value.rstrip("/")


def require_loopback_host(value: str) -> str:
    """Validate a bind host without performing DNS resolution."""

    if value.lower() == "localhost":
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("Dashboard host must be localhost or a loopback address") from exc
    if not address.is_loopback:
        raise ValueError("Dashboard host must be loopback")
    return value
