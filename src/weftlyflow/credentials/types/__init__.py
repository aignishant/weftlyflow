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
    jira_cloud.py             : Jira Cloud email + API token basic auth.
    shopify_admin.py          : Shopify Admin API ``X-Shopify-Access-Token``.
    clickup_api.py            : ClickUp unprefixed ``Authorization`` token.
    twilio_api.py             : Twilio Account SID + Auth Token Basic auth.
    gitlab_token.py           : GitLab ``PRIVATE-TOKEN`` header + configurable host.
    intercom_api.py           : Intercom Bearer + ``Intercom-Version`` header.
    monday_api.py             : Monday.com unprefixed ``Authorization`` token.
    zendesk_api.py            : Zendesk Basic auth with ``/token`` email suffix.
    brevo_api.py              : Brevo ``api-key`` lowercase header.
    pagerduty_api.py          : PagerDuty ``Token token=<key>`` + From header.
    algolia_api.py            : Algolia dual ``X-Algolia-*`` headers.
    mailchimp_api.py          : Mailchimp Basic auth with dc parsed from key.
    pipedrive_api.py          : Pipedrive ``?api_token=`` query + tenant host.
    zoho_crm_oauth2.py        : Zoho ``Zoho-oauthtoken`` prefix + DC host.
    mattermost_api.py         : Mattermost Bearer + credential-owned base URL.
    cloudflare_api.py         : Cloudflare dual ``X-Auth-Email`` + ``X-Auth-Key``.
    freshdesk_api.py          : Freshdesk Basic auth with api_key + dummy ``X``.
    supabase_api.py           : Supabase dual ``apikey`` + ``Authorization: Bearer``.
    okta_api.py               : Okta ``Authorization: SSWS <token>`` + per-org URL.
    linear_api.py             : Linear raw ``Authorization`` for GraphQL endpoint.
    pushover_api.py           : Pushover form-body auth (``token`` + ``user``).
    elasticsearch_api.py      : Elasticsearch ``ApiKey <b64(id:key)>`` prefix.
    dropbox_api.py            : Dropbox Bearer + node-side ``Dropbox-API-Arg`` JSON header.
    twitch_api.py             : Twitch Bearer + mandatory ``Client-Id`` header pair.

Per-service OAuth2 types ship alongside their integration node.
"""

from __future__ import annotations

from weftlyflow.credentials.types.algolia_api import AlgoliaApiCredential
from weftlyflow.credentials.types.api_key_header import ApiKeyHeaderCredential
from weftlyflow.credentials.types.api_key_query import ApiKeyQueryCredential
from weftlyflow.credentials.types.basic_auth import BasicAuthCredential
from weftlyflow.credentials.types.bearer_token import BearerTokenCredential
from weftlyflow.credentials.types.brevo_api import BrevoApiCredential
from weftlyflow.credentials.types.clickup_api import ClickUpApiCredential
from weftlyflow.credentials.types.cloudflare_api import CloudflareApiCredential
from weftlyflow.credentials.types.discord_bot import DiscordBotCredential
from weftlyflow.credentials.types.dropbox_api import DropboxApiCredential
from weftlyflow.credentials.types.elasticsearch_api import ElasticsearchApiCredential
from weftlyflow.credentials.types.freshdesk_api import FreshdeskApiCredential
from weftlyflow.credentials.types.gitlab_token import GitLabTokenCredential
from weftlyflow.credentials.types.google_sheets_oauth2 import GoogleSheetsOAuth2Credential
from weftlyflow.credentials.types.hubspot_private_app import HubSpotPrivateAppCredential
from weftlyflow.credentials.types.intercom_api import IntercomApiCredential
from weftlyflow.credentials.types.jira_cloud import JiraCloudCredential
from weftlyflow.credentials.types.linear_api import LinearApiCredential
from weftlyflow.credentials.types.mailchimp_api import MailchimpApiCredential
from weftlyflow.credentials.types.mattermost_api import MattermostApiCredential
from weftlyflow.credentials.types.monday_api import MondayApiCredential
from weftlyflow.credentials.types.notion_api import NotionApiCredential
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.credentials.types.okta_api import OktaApiCredential
from weftlyflow.credentials.types.pagerduty_api import PagerDutyApiCredential
from weftlyflow.credentials.types.pipedrive_api import PipedriveApiCredential
from weftlyflow.credentials.types.pushover_api import PushoverApiCredential
from weftlyflow.credentials.types.shopify_admin import ShopifyAdminCredential
from weftlyflow.credentials.types.slack_api import SlackApiCredential
from weftlyflow.credentials.types.slack_oauth2 import SlackOAuth2Credential
from weftlyflow.credentials.types.supabase_api import SupabaseApiCredential
from weftlyflow.credentials.types.telegram_bot import TelegramBotCredential
from weftlyflow.credentials.types.trello_api import TrelloApiCredential
from weftlyflow.credentials.types.twilio_api import TwilioApiCredential
from weftlyflow.credentials.types.twitch_api import TwitchApiCredential
from weftlyflow.credentials.types.zendesk_api import ZendeskApiCredential
from weftlyflow.credentials.types.zoho_crm_oauth2 import ZohoCrmOAuth2Credential

__all__ = [
    "AlgoliaApiCredential",
    "ApiKeyHeaderCredential",
    "ApiKeyQueryCredential",
    "BasicAuthCredential",
    "BearerTokenCredential",
    "BrevoApiCredential",
    "ClickUpApiCredential",
    "CloudflareApiCredential",
    "DiscordBotCredential",
    "DropboxApiCredential",
    "ElasticsearchApiCredential",
    "FreshdeskApiCredential",
    "GitLabTokenCredential",
    "GoogleSheetsOAuth2Credential",
    "HubSpotPrivateAppCredential",
    "IntercomApiCredential",
    "JiraCloudCredential",
    "LinearApiCredential",
    "MailchimpApiCredential",
    "MattermostApiCredential",
    "MondayApiCredential",
    "NotionApiCredential",
    "OAuth2GenericCredential",
    "OktaApiCredential",
    "PagerDutyApiCredential",
    "PipedriveApiCredential",
    "PushoverApiCredential",
    "ShopifyAdminCredential",
    "SlackApiCredential",
    "SlackOAuth2Credential",
    "SupabaseApiCredential",
    "TelegramBotCredential",
    "TrelloApiCredential",
    "TwilioApiCredential",
    "TwitchApiCredential",
    "ZendeskApiCredential",
    "ZohoCrmOAuth2Credential",
]
