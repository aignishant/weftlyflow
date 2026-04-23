"""Reddit integration — user info, submissions, subreddit reads.

Uses :class:`~weftlyflow.credentials.types.reddit_oauth2.RedditOAuth2Credential`.
The credential injects both Bearer auth and a Reddit-formatted
User-Agent (``platform:app_id:version (by /u/user)``) — the User-Agent
is enforced server-side and a generic httpx default will be throttled.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.reddit.node import RedditNode

NODE = RedditNode

__all__ = ["NODE", "RedditNode"]
