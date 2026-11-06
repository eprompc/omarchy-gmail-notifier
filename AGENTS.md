# Compatibility and privacy requirements

This plugin is installed on users' desktops and its default branch is consumed by the Omarchy updater. An update must retain existing configuration and Google authorization without launching OAuth again merely because the plugin version changed.

- Keep the plugin ID `eprom.gmail-notifier`, configuration/OAuth-client paths, existing account IDs and the `gmail-notifier` Secret Service application attribute stable. Preserve all saved preferences, account order, switches and unknown configuration fields.
- Configuration schema changes must be additive or have an explicit, reversible migration. Keep a private valid backup. Never silently replace invalid state with an empty account list.
- Never delete or reset tokens on startup, upgrade, restart, a temporary network failure or a failed compatibility copy. Only explicit account removal clears saved authorizations.
- Existing credential attributes must remain readable by previous supported releases. Keep legacy and hashed token copies synchronized, including a rotated refresh token; use the legacy entry as authoritative when both exist so interrupted dual writes recover safely.
- Store tokens only in Secret Service. Do not add token files or credential backups to disk. Use in-process D-Bus/libsecret; no private metadata or credentials in subprocess arguments, environment variables, logs or temporary payloads.
- Keep the Google metadata scope and OAuth client configuration unchanged for compatible upgrades. Google revocation, token expiry, user removal or an unavailable keyring are separate failures: report them without erasing configuration.
- Keep changes reviewable in a branch/PR. Validate the candidate before updating main; publication/marketplace replies must identify the exact commit actually reviewed and tested. Respect the owner's existing authorization rather than asking them to approve an already authorized step again.
- Before declaring release compatibility, run the upgrade fixtures, all Python and JavaScript regressions, the real isolated D-Bus and Secret Service integrations, QML parsing, and the Omarchy manifest validator. Tests use synthetic credentials and isolated stores only. Record desktop acceptance separately; a parser pass is not a rendered Omarchy test.
