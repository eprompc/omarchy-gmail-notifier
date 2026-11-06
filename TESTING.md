# Validate 0.3.0 before release

This branch is a release candidate. Automated checks use synthetic data and never authenticate to Google. Runtime dependencies are documented in README.md.

## Automated checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.test.cjs
python3 -m compileall -q helper
dbus-run-session -- /usr/bin/python3 tests/dbus_integration.py
# Optional integration dependency: gnome-keyring, used only with a temporary empty keyring.
dbus-run-session -- /usr/bin/python3 tests/secret_integration.py
omarchy plugin validate .
```

Use a system Python with PyGObject for the D-Bus test. CI installs its dependencies only on the disposable GitHub Actions runner. The plugin does not contain a package installer. Qt 6 parses both QML files in CI; the JavaScript tests execute the widget's actual response/queue functions without a compositor. These checks do not constitute a rendered Omarchy acceptance test.

The D-Bus test owns a fake notification server on an isolated session bus. It verifies typed delivery, transient hints and the absence of child process invocation. Other tests exercise two persistent widget clients, shared state revisions, acknowledgement during blocked network work, concurrent configuration edits, 501-message pagination, invalid state/Google data, and notification failure without losing counts.

## Try the candidate

Use the existing installed checkout, preserve any uncommitted changes first, and stop if `git status --short` is not empty. Do not install two copies with the same plugin ID.

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
git status --short
git fetch origin fix/privacy-reliability-45
omarchy plugin disable eprom.gmail-notifier
git switch --detach origin/fix/privacy-reliability-45
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Use the existing OAuth client and accounts. Installing the new dependencies does not require new Google scopes. The first successful use creates a compatible hashed credential copy inside Secret Service while retaining the original entry. Refresh keeps both formats synchronized, and rollback to the previous release must reuse the existing authorization. Do not delete tokens or personal state as part of testing. Configuration IDs are retained for existing accounts.

The normal Omarchy plugin updater fetches the default branch (`main`), not this candidate. Do not run it while trying the candidate.

## Required desktop acceptance

Record the exact commit, Omarchy version, monitor count and scale factors. The repository owner reported successful routine testing of the previous version; this candidate changes IPC and needs its own acceptance record.

- [ ] Validate and load in Omarchy 4.5 without QML import/runtime errors.
- [ ] Update an existing installation without authorizing again. Verify unchanged accounts, order, initials, switches, language and layout; roll back and verify authorization still works. Separately authorize a new test account and cancel one authorization attempt.
- [ ] Receive a synthetic email. Verify account initials in the title, sender in bold, subject below, theme appearance, DND and alert disabling.
- [ ] With synthetic notification data, inspect process command lines during delivery: no sender, subject, account address, or token should appear in newly launched desktop helper commands.
- [ ] On two/three monitors, receive new mail, acknowledge on each monitor, test a new arrival concurrent with a click, disconnect/reconnect a monitor, and restart the shell.
- [ ] Pause/resume and edit settings simultaneously on different monitors. Remove a test account during an active request.
- [ ] Open an inbox with more than 500 unread messages; load subsequent pages, test a message deleted during loading, and interrupt connectivity. Confirm no repeating error loop.
- [ ] Change system language, test English/Spanish overrides, a different theme, keyboard navigation and mixed scaling.
- [ ] With no new mail, confirm the service and persistent clients remain running without recurring process launches. With all widgets disabled, confirm service exit after 60 idle seconds.

## Rollback

```bash
cd ~/.config/omarchy/plugins/eprom.gmail-notifier
omarchy plugin disable eprom.gmail-notifier
git switch main
git pull --ff-only origin main
omarchy plugin validate .
omarchy plugin enable eprom.gmail-notifier
```

Preserve config.json and its private backup. Do not post OAuth files, socket payloads, tokens, account configurations or real snapshots in issues. Use synthetic metadata for reports.
