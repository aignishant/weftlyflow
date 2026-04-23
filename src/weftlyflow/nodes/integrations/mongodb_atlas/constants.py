"""Constants for the MongoDB Atlas integration node.

Reference: https://www.mongodb.com/docs/atlas/reference/api-resources-spec/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://cloud.mongodb.com/api/atlas/v2"
ACCEPT_MEDIA_TYPE: Final[str] = "application/vnd.atlas.2024-05-30+json"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_PROJECTS: Final[str] = "list_projects"
OP_LIST_CLUSTERS: Final[str] = "list_clusters"
OP_GET_CLUSTER: Final[str] = "get_cluster"
OP_LIST_DB_USERS: Final[str] = "list_db_users"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_PROJECTS,
    OP_LIST_CLUSTERS,
    OP_GET_CLUSTER,
    OP_LIST_DB_USERS,
)
