"""Concrete credential type implementations.

    bearer_token.py           : ``Authorization: Bearer <token>``.
    basic_auth.py             : HTTP Basic auth (username + password).
    api_key_header.py         : API key injected as an arbitrary header.
    api_key_query.py          : API key appended as a query parameter.
    oauth2_generic.py         : OAuth2 auth-code flow, stores tokens.
    slack_api.py              : Slack Web API bot/user token.
    slack_oauth2.py           : Slack OAuth2 install — pre-filled endpoints + scopes.
    notion_api.py             : Notion integration token + Notion-Version header.
    google_sheets_oauth2.py   : Google Sheets OAuth2 — pre-filled endpoints + scope.
    discord_bot.py            : Discord bot token — ``Authorization: Bot <token>``.
    telegram_bot.py           : Telegram bot token — embedded in URL path.
    trello_api.py             : Trello key + token as query parameters.
    hubspot_private_app.py    : HubSpot Private-App Bearer token.

Per-service OAuth2 types ship alongside their integration node.
"""

from __future__ import annotations

from weftlyflow.credentials.types.api_key_header import ApiKeyHeaderCredential
from weftlyflow.credentials.types.api_key_query import ApiKeyQueryCredential
from weftlyflow.credentials.types.basic_auth import BasicAuthCredential
from weftlyflow.credentials.types.bearer_token import BearerTokenCredential
from weftlyflow.credentials.types.discord_bot import DiscordBotCredential
from weftlyflow.credentials.types.google_sheets_oauth2 import GoogleSheetsOAuth2Credential
from weftlyflow.credentials.types.hubspot_private_app import HubSpotPrivateAppCredential
from weftlyflow.credentials.types.notion_api import NotionApiCredential
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.credentials.types.slack_api import SlackApiCredential
from weftlyflow.credentials.types.slack_oauth2 import SlackOAuth2Credential
from weftlyflow.credentials.types.telegram_bot import TelegramBotCredential
from weftlyflow.credentials.types.trello_api import TrelloApiCredential

__all__ = [
    "ApiKeyHeaderCredential",
    "ApiKeyQueryCredential",
    "BasicAuthCredential",
    "BearerTokenCredential",
    "DiscordBotCredential",
    "GoogleSheetsOAuth2Credential",
    "HubSpotPrivateAppCredential",
    "NotionApiCredential",
    "OAuth2GenericCredential",
    "SlackApiCredential",
    "SlackOAuth2Credential",
    "TelegramBotCredential",
    "TrelloApiCredential",
]
