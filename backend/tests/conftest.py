"""Shared pytest fixtures.

Unit tests mock every network source, but httpx still inspects proxy
environment variables when constructing clients. On machines/CI sandboxes
that export a SOCKS proxy (ALL_PROXY=socks5h://...), client construction
raises ImportError unless socksio is installed — failing tests that never
intended to touch the network. Strip proxy variables for the test session so
the suite is hermetic everywhere; production behavior is unchanged.
"""
from __future__ import annotations

import os

import pytest

_PROXY_VARS = (
    "ALL_PROXY", "all_proxy",
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "FTP_PROXY", "ftp_proxy",
    "GRPC_PROXY", "grpc_proxy",
)


@pytest.fixture(autouse=True)
def _no_env_proxies(monkeypatch):
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
