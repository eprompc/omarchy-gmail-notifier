# Update compatibility contract

Normal plugin updates replace source code, not personal state. An update must keep accounts, account order and IDs, initials, alert/paused switches, polling interval, language, layout preferences, OAuth client configuration and usable saved Google authorization.

## Stable storage

- Plugin ID: `eprom.gmail-notifier`.
- Configuration: `~/.config/omarchy/gmail-notifier/config.json`, schema version 1.
- OAuth client: `~/.config/omarchy/gmail-notifier/oauth-client.json`. The plugin reads but never rewrites this file.
- Credentials: Secret Service attributes `application=gmail-notifier`, `account=<email>` for legacy readers and `account=<sha256(email)>` for current readers.
- Header cache: `~/.cache/omarchy/gmail-notifier/`. Cache loss may cause a fresh header fetch; it must not trigger OAuth.

0.3.0 keeps the legacy credential entry and creates a compatible hashed copy inside Secret Service. Both are updated on token refresh. A partial write is recovered from the legacy entry; a failed copy retains the valid original. Entries are deleted only when the user explicitly removes an account. New accounts also receive both formats so supported older releases can still read their authorization after rollback. No token is exported to a file, process argument or environment variable.

Configuration migrations add defaults without changing existing account IDs or preferences. Unknown fields are preserved. Limits for creating new accounts or labels must not reject an otherwise valid configuration saved by a supported previous version. Invalid configuration is preserved and reported rather than silently reset.

## Release checks

`tests/fixtures/config-v020.json` records the previous saved format. `tests/test_upgrade.py` verifies repeated upgrades/restarts, unchanged OAuth client bytes, preserved settings and identities, a fresh token reused without a browser or OAuth request, refresh-token rotation, interrupted credential-copy recovery, and authorization reuse after rollback. The real keyring integration repeats legacy-format lookup and refresh with libsecret and an isolated empty Secret Service.

These checks are part of CI and are release requirements for future changes. Keep fixtures for supported persisted formats as versions evolve.

## What an update cannot guarantee

Google can revoke a grant or expire a refresh token independently of plugin updates. External OAuth apps in Google's Testing state can receive time-limited refresh tokens. Deleting an account, clearing the keyring, changing the OAuth client, or having a locked/unavailable Secret Service also changes access independently of source updates. The plugin must distinguish these cases, retain personal state and explain the next action. It must not claim that an external grant will remain valid forever.
