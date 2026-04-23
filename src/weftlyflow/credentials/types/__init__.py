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
    datadog_api.py            : Datadog dual ``DD-API-KEY`` + ``DD-APPLICATION-KEY`` headers.
    freshdesk_api.py          : Freshdesk Basic auth with api_key + dummy ``X``.
    supabase_api.py           : Supabase dual ``apikey`` + ``Authorization: Bearer``.
    okta_api.py               : Okta ``Authorization: SSWS <token>`` + per-org URL.
    linear_api.py             : Linear raw ``Authorization`` for GraphQL endpoint.
    pushover_api.py           : Pushover form-body auth (``token`` + ``user``).
    elasticsearch_api.py      : Elasticsearch ``ApiKey <b64(id:key)>`` prefix.
    dropbox_api.py            : Dropbox Bearer + node-side ``Dropbox-API-Arg`` JSON header.
    twitch_api.py             : Twitch Bearer + mandatory ``Client-Id`` header pair.
    salesforce_api.py         : Salesforce Bearer + per-org ``instance_url``.
    zoom_api.py               : Zoom Server-to-Server Bearer + ``account_id`` audit field.
    microsoft_graph.py        : Microsoft Graph Bearer + ``tenant_id`` audit field.
    asana_api.py              : Asana Bearer + optional ``Asana-Enable`` opt-ins.
    box_api.py                : Box Bearer + optional ``As-User`` impersonation.
    snowflake_api.py          : Snowflake Bearer + token-type declaration header.
    activecampaign_api.py     : ActiveCampaign raw ``Api-Token`` + per-tenant URL.
    aws_s3.py                 : AWS S3 access key + secret + region — SigV4 signing.
    openai_api.py             : OpenAI Bearer + ``OpenAI-Organization`` + ``OpenAI-Project``.
    xero_api.py               : Xero OAuth2 Bearer + mandatory ``xero-tenant-id`` header.
    netsuite_api.py           : NetSuite OAuth 1.0a HMAC-SHA256 Token-Based Auth.
    quickbooks_oauth2.py      : QuickBooks OAuth2 Bearer + realmId in URL path.
    square_api.py             : Square Bearer + mandatory ``Square-Version`` header.
    facebook_graph.py         : Facebook Graph Bearer + optional HMAC ``appsecret_proof`` query.
    anthropic_api.py          : Anthropic ``x-api-key`` + ``anthropic-version`` header pair.
    bitbucket_api.py          : Bitbucket Cloud Basic auth + workspace-scoped URL paths.
    paypal_api.py             : PayPal OAuth2 Client Credentials — runtime token fetch.
    mapbox_api.py             : Mapbox ``?access_token=`` query-param auth.
    rocket_chat_api.py        : Rocket.Chat ``X-Auth-Token`` + ``X-User-Id`` dual header.
    contentful_api.py         : Contentful Bearer — split mgmt (CMA) vs CDN (CDA) hosts.
    hasura_api.py             : Hasura ``X-Hasura-Admin-Secret`` + optional role header.
    ghost_admin.py            : Ghost Admin ``Authorization: Ghost <HS256 JWT>`` per request.
    pinecone_api.py           : Pinecone ``Api-Key`` + control/data-plane host split.
    gmail_oauth2.py           : Gmail OAuth2 — pre-filled endpoints + send scope.
    google_drive_oauth2.py    : Google Drive OAuth2 — pre-filled endpoints + file scope.

Per-service OAuth2 types ship alongside their integration node.
"""

from __future__ import annotations

from weftlyflow.credentials.types.activecampaign_api import ActiveCampaignApiCredential
from weftlyflow.credentials.types.algolia_api import AlgoliaApiCredential
from weftlyflow.credentials.types.anthropic_api import AnthropicApiCredential
from weftlyflow.credentials.types.api_key_header import ApiKeyHeaderCredential
from weftlyflow.credentials.types.api_key_query import ApiKeyQueryCredential
from weftlyflow.credentials.types.asana_api import AsanaApiCredential
from weftlyflow.credentials.types.aws_s3 import AwsS3Credential
from weftlyflow.credentials.types.basic_auth import BasicAuthCredential
from weftlyflow.credentials.types.bearer_token import BearerTokenCredential
from weftlyflow.credentials.types.bitbucket_api import BitbucketApiCredential
from weftlyflow.credentials.types.box_api import BoxApiCredential
from weftlyflow.credentials.types.brevo_api import BrevoApiCredential
from weftlyflow.credentials.types.clickup_api import ClickUpApiCredential
from weftlyflow.credentials.types.cloudflare_api import CloudflareApiCredential
from weftlyflow.credentials.types.contentful_api import ContentfulApiCredential
from weftlyflow.credentials.types.datadog_api import DatadogApiCredential
from weftlyflow.credentials.types.discord_bot import DiscordBotCredential
from weftlyflow.credentials.types.dropbox_api import DropboxApiCredential
from weftlyflow.credentials.types.elasticsearch_api import ElasticsearchApiCredential
from weftlyflow.credentials.types.facebook_graph import FacebookGraphCredential
from weftlyflow.credentials.types.freshdesk_api import FreshdeskApiCredential
from weftlyflow.credentials.types.ghost_admin import GhostAdminCredential
from weftlyflow.credentials.types.gitlab_token import GitLabTokenCredential
from weftlyflow.credentials.types.gmail_oauth2 import GmailOAuth2Credential
from weftlyflow.credentials.types.google_drive_oauth2 import GoogleDriveOAuth2Credential
from weftlyflow.credentials.types.google_sheets_oauth2 import GoogleSheetsOAuth2Credential
from weftlyflow.credentials.types.hasura_api import HasuraApiCredential
from weftlyflow.credentials.types.hubspot_private_app import HubSpotPrivateAppCredential
from weftlyflow.credentials.types.intercom_api import IntercomApiCredential
from weftlyflow.credentials.types.jira_cloud import JiraCloudCredential
from weftlyflow.credentials.types.linear_api import LinearApiCredential
from weftlyflow.credentials.types.mailchimp_api import MailchimpApiCredential
from weftlyflow.credentials.types.mapbox_api import MapboxApiCredential
from weftlyflow.credentials.types.mattermost_api import MattermostApiCredential
from weftlyflow.credentials.types.microsoft_graph import MicrosoftGraphCredential
from weftlyflow.credentials.types.monday_api import MondayApiCredential
from weftlyflow.credentials.types.netsuite_api import NetSuiteApiCredential
from weftlyflow.credentials.types.notion_api import NotionApiCredential
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.credentials.types.okta_api import OktaApiCredential
from weftlyflow.credentials.types.openai_api import OpenAIApiCredential
from weftlyflow.credentials.types.pagerduty_api import PagerDutyApiCredential
from weftlyflow.credentials.types.paypal_api import PayPalApiCredential
from weftlyflow.credentials.types.pinecone_api import PineconeApiCredential
from weftlyflow.credentials.types.pipedrive_api import PipedriveApiCredential
from weftlyflow.credentials.types.pushover_api import PushoverApiCredential
from weftlyflow.credentials.types.quickbooks_oauth2 import QuickBooksOAuth2Credential
from weftlyflow.credentials.types.rocket_chat_api import RocketChatApiCredential
from weftlyflow.credentials.types.salesforce_api import SalesforceApiCredential
from weftlyflow.credentials.types.shopify_admin import ShopifyAdminCredential
from weftlyflow.credentials.types.slack_api import SlackApiCredential
from weftlyflow.credentials.types.slack_oauth2 import SlackOAuth2Credential
from weftlyflow.credentials.types.snowflake_api import SnowflakeApiCredential
from weftlyflow.credentials.types.square_api import SquareApiCredential
from weftlyflow.credentials.types.supabase_api import SupabaseApiCredential
from weftlyflow.credentials.types.telegram_bot import TelegramBotCredential
from weftlyflow.credentials.types.trello_api import TrelloApiCredential
from weftlyflow.credentials.types.twilio_api import TwilioApiCredential
from weftlyflow.credentials.types.twitch_api import TwitchApiCredential
from weftlyflow.credentials.types.xero_api import XeroApiCredential
from weftlyflow.credentials.types.zendesk_api import ZendeskApiCredential
from weftlyflow.credentials.types.zoho_crm_oauth2 import ZohoCrmOAuth2Credential
from weftlyflow.credentials.types.zoom_api import ZoomApiCredential

__all__ = [
    "ActiveCampaignApiCredential",
    "AlgoliaApiCredential",
    "AnthropicApiCredential",
    "ApiKeyHeaderCredential",
    "ApiKeyQueryCredential",
    "AsanaApiCredential",
    "AwsS3Credential",
    "BasicAuthCredential",
    "BearerTokenCredential",
    "BitbucketApiCredential",
    "BoxApiCredential",
    "BrevoApiCredential",
    "ClickUpApiCredential",
    "CloudflareApiCredential",
    "ContentfulApiCredential",
    "DatadogApiCredential",
    "DiscordBotCredential",
    "DropboxApiCredential",
    "ElasticsearchApiCredential",
    "FacebookGraphCredential",
    "FreshdeskApiCredential",
    "GhostAdminCredential",
    "GitLabTokenCredential",
    "GmailOAuth2Credential",
    "GoogleDriveOAuth2Credential",
    "GoogleSheetsOAuth2Credential",
    "HasuraApiCredential",
    "HubSpotPrivateAppCredential",
    "IntercomApiCredential",
    "JiraCloudCredential",
    "LinearApiCredential",
    "MailchimpApiCredential",
    "MapboxApiCredential",
    "MattermostApiCredential",
    "MicrosoftGraphCredential",
    "MondayApiCredential",
    "NetSuiteApiCredential",
    "NotionApiCredential",
    "OAuth2GenericCredential",
    "OktaApiCredential",
    "OpenAIApiCredential",
    "PagerDutyApiCredential",
    "PayPalApiCredential",
    "PineconeApiCredential",
    "PipedriveApiCredential",
    "PushoverApiCredential",
    "QuickBooksOAuth2Credential",
    "RocketChatApiCredential",
    "SalesforceApiCredential",
    "ShopifyAdminCredential",
    "SlackApiCredential",
    "SlackOAuth2Credential",
    "SnowflakeApiCredential",
    "SquareApiCredential",
    "SupabaseApiCredential",
    "TelegramBotCredential",
    "TrelloApiCredential",
    "TwilioApiCredential",
    "TwitchApiCredential",
    "XeroApiCredential",
    "ZendeskApiCredential",
    "ZohoCrmOAuth2Credential",
    "ZoomApiCredential",
]
