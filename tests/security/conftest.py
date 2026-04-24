"""Shared fixtures for the security test suite.

Reuses the integration suite's ``client``, ``access_token``, and
``auth_headers`` fixtures by re-exporting them here so that each security
test file only needs to import from its own conftest.
"""

from __future__ import annotations

from tests.integration.conftest import (  # noqa: F401
    TEST_ADMIN_EMAIL,
    TEST_ADMIN_PASSWORD,
    access_token,
    auth_headers,
    client,
)
