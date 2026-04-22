"""Constants for the Cloudflare client/v4 integration node.

Reference: https://developers.cloudflare.com/api/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.cloudflare.com/client/v4"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_ZONES: Final[str] = "list_zones"
OP_GET_ZONE: Final[str] = "get_zone"
OP_LIST_DNS_RECORDS: Final[str] = "list_dns_records"
OP_CREATE_DNS_RECORD: Final[str] = "create_dns_record"
OP_UPDATE_DNS_RECORD: Final[str] = "update_dns_record"
OP_DELETE_DNS_RECORD: Final[str] = "delete_dns_record"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_ZONES,
    OP_GET_ZONE,
    OP_LIST_DNS_RECORDS,
    OP_CREATE_DNS_RECORD,
    OP_UPDATE_DNS_RECORD,
    OP_DELETE_DNS_RECORD,
)

DEFAULT_PER_PAGE: Final[int] = 50
MAX_PER_PAGE: Final[int] = 1000
MIN_TTL_SECONDS: Final[int] = 60
TTL_AUTO: Final[int] = 1

DNS_RECORD_TYPES: Final[frozenset[str]] = frozenset(
    {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "PTR"},
)

DNS_RECORD_UPDATE_FIELDS: Final[frozenset[str]] = frozenset(
    {"type", "name", "content", "ttl", "proxied", "priority", "comment", "tags"},
)
