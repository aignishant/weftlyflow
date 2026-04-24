# Expressions

*Stub — populated in Phase 4.*

Template strings wrapped in `{{ ... }}`. The body is a restricted Python subset evaluated in a sandbox. Available proxies: `$json`, `$binary`, `$input`, `$output`, `$prev_node`, `$now`, `$today`, `$env`, `$workflow`, `$execution`, `$vars`. No `$credentials` proxy — nodes access credentials through a separate API.

See `weftlyinfo.md §10`.
