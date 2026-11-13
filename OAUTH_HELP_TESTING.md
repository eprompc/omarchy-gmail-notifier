# OAuth setup help candidate (0.3.2)

Branch: `fix/oauth-setup-help`, based on refresh candidate `4ec9b29b73f320d5d6de65a6047d4b772758b87c` (PR #3). This branch includes both the refresh correction and the focused help/setup change, so they can be tested together. Its PR targets `fix/refresh-scheduling` to keep the help diff focused. Integrate the refresh PR before retargeting/integrating the help PR into main. Neither candidate has desktop acceptance merely because the previous 0.3.0 release was accepted.

## Permanent update requirement

An ordinary source update must retain the existing plugin ID, configuration schema and paths, account identities/order/preferences, original OAuth client and usable Secret Service grants. This candidate changes none of those contracts. `oauth_status` is an additive public state hint; it never writes client JSON, reads/clears tokens, resets accounts or starts OAuth. A missing file does not block an already usable access token. Restoring the original file permits the same saved grant to refresh.

Google revocation/expiry, Testing-mode seven-day limits, lost/replaced client files and a lost/locked keyring are external conditions and need distinct diagnosis. Help must not suggest creating a replacement client or deleting existing accounts to fix an update.

## Automated checks

Run TESTING.md's full Python/JavaScript, D-Bus, Secret Service and manifest checks, plus:

```bash
node scripts/render-setup-docs.cjs --check
# With PySide6-Essentials installed in a development environment:
pyside6-qmlformat OAuthSetupHelp.qml > /dev/null
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software python tests/setup_help_qml.py
```

`tests/test_oauth_setup.py` uses synthetic client/tokens in isolated stores. It checks missing/invalid/unreadable client status, unchanged configuration/client bytes and saved secrets, no implicit OAuth/browser launch, original-client recovery and grant refresh, usable existing tokens while a client is missing, local checking during queued network work and detection of a saved client by a running service. No real Google authorization is used.

`tests/setup-help.test.cjs` checks English/Spanish regional locales, English fallback, matching steps/destinations, the small metadata scope, recovery advice, fixed Google-only URLs without private query parameters and synchronized Markdown guides.

The Qt smoke test loads the actual guide with minimal host-theme/button shims and traverses all steps in English/Spanish at widths 360/448/720. It checks setup states, navigation and the saved-account recovery route. It is not a rendered Omarchy acceptance test. `--screenshots` optionally saves local synthetic previews under ignored `artifacts/`.

## Try the candidate on a desktop

First run status and stop if it shows uncommitted changes. Preserve those changes before switching. Do not reset, remove or replace personal files for this test.

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
git status --short
git fetch origin fix/oauth-setup-help
omarchy plugin disable eprom.gmail-notifier
git switch --detach origin/fix/oauth-setup-help
git rev-parse HEAD
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Do not use the regular updater while testing a branch. Do not deliberately delete your real client or credentials to simulate missing setup; automated fixtures already cover missing/invalid files. Test a genuine first installation with a separate test desktop/user when available.

Record the exact commit, Omarchy version, locale and monitor/scaling setup. Pending owner checks:

- [ ] Update an existing installation and verify accounts, labels, order, alerts, language, layout and authorization survive. Ordinary polling and refresh must work without reauthorizing.
- [ ] On a clean first installation, see a prominent HELP button and the message that the plugin is installed; missing Google setup must not look like a missing plugin.
- [ ] Choose Add Gmail account before creating the client: the button stays available and opens the setup guide, without a blocking error or an OAuth launch. Once ready, the same button starts Google's normal sign-in.
- [ ] Traverse all eight setup steps in English and Spanish, then with the system locale. Check keyboard/mouse navigation, scrolling, compact width and enlarged text. Google links open only on a deliberate click.
- [ ] Follow the guide to configure a test Google Desktop client, including the metadata scope and Testing/Production explanation. Save the JSON privately. Verify the status updates without restarting and Check setup does not open Google.
- [ ] Add a new test account by a deliberate click only. Existing accounts must never need to be added again merely after an update.
- [ ] With saved accounts, open HELP and see the three-step original-client recovery route, not the new-client wizard. Check setup must not create clients or modify tokens/preferences. Return to settings and confirm the existing accounts still work.
- [ ] Roll back to main and verify the same saved client, preferences and authorizations remain usable.

## Return to stable

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
omarchy plugin disable eprom.gmail-notifier
git switch main
git pull --ff-only origin main
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Keep `~/.config/omarchy/gmail-notifier`, its original OAuth client, configuration/backup and the desktop keyring. Never post JSON contents, real snapshots, tokens or account information in test reports.
