# Gmail Notifier by Eprom

A lightweight personal Omarchy bar widget that checks multiple Gmail accounts without depending on a browser profile or container. The bar always has one envelope button for settings; account badges appear only while that account has unread Inbox messages.

### Bar notifications screenshot

<p align="center">
  <img src="assets/bar.png" alt="Bar notifications screenshot" width="265">
</p>

### Widget settings panel screenshot

<p align="center">
  <img src="assets/preview.png" alt="Widget settings panel screenshot" width="380">
</p>

## Features

- One account badge per account with unread messages. The user chooses a one-to-seven-character label and can reorder accounts.
- Clicking an account badge shows sender and subject in pages of 50 unread Inbox messages; use **Load messages** to fetch another page. The plugin never reads message bodies and has no mail actions. Clicking an account stops any active new-mail flashing immediately.
- Header includes a manual **Update** button to immediately query Gmail on demand.
- Account headings and separators follow Omarchy's live popup-border color. Sender display names use the theme accent, without bold; subjects use the normal theme foreground.
- Themed styling with dynamic Omarchy tokens: "Add Gmail account" button uses the active theme's green (`themeGreen` from `colors.toml` / `Color.accent`) with a 2 px thick border; "Remove" and confirmation use urgent red (`themeRed` from `Color.urgent` / `colors.toml`).
- Cleaner two-line layout per account: top line has reorder arrows (`↑` and `↓`), status dot, email address, and label field; bottom line has desktop alerts toggle (`Ui.ToggleSwitch`), pause/resume button, and remove button.
- Desktop notifications ("Alerts") call the notification server directly through Gio D-Bus, in process. The title identifies the configured account initials; the body shows the sender in bold and the subject. No message text is sent through command arguments or environment variables. Notifications are transient and can be disabled per account.
- Flash duration is configurable in seconds (default: 60s, range 5s–600s), with a toggle for "Flash until clicked".
- Messages outside Inbox, including snoozed mail, are excluded.
- Accounts can be paused, resumed, silenced, or removed. Polling is adjustable from 1 to 60 minutes (2 minutes by default).
- Settings follow Omarchy’s live language with English fallback and a Spanish catalog; explicit English/Spanish overrides are available, use compact theme-styled buttons, and require an explicit confirmation before removing an account. The account label field has a visible outline. The panel starts at 376 px and can be resized in settings.
- All monitors share one local service and ordered state revisions. Clicking an account stops that alert everywhere, including while Gmail is busy. Each widget keeps one persistent client; there are no recurring Python process launches per monitor. Configuration edits use a short transaction and file replacement, so simultaneous edits cannot overwrite each other.
- Google OAuth runs in the system default browser with PKCE and a loopback callback. Chrome/Chromium is not required; Zen Browser works when it is the default browser.
- A prominent **HELP / AYUDA** button guides first-time users through their Google client setup in English or Spanish. Existing accounts get a recovery guide that preserves the original client and saved authorization.

## Installation

Install directly in Omarchy using the official CLI:

```bash
omarchy plugin add https://github.com/eprompc/omarchy-gmail-notifier.git --enable --yes
```

To update to the latest release at any time:

```bash
omarchy plugin update eprom.gmail-notifier
```

### Uninstall

To disable and remove the plugin from Omarchy:

```bash
omarchy plugin disable eprom.gmail-notifier
omarchy plugin remove eprom.gmail-notifier
```

Requirements: **Omarchy 4.5 or newer**, `python3`, `python-gobject` (Gio/GLib introspection), `libsecret` (including the Secret typelib), and an unlocked Secret Service in the desktop session. The plugin does not install these packages. A Python virtual environment without the system introspection modules is not supported. `notify-send`, `busctl` and `secret-tool` are not used by this version.

### Omarchy 4.5 compatibility

The plugin uses Omarchy's schema 1 `bar-widget` contract and is compatible with Omarchy 4.5 (Quattro). Validate a checkout before enabling it:

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
node --test tests/*.test.cjs
python3 -m compileall -q helper
dbus-run-session -- /usr/bin/python3 tests/dbus_integration.py
```

One private Unix socket connects the widgets to a per-user Python service. Peer user IDs and directory/file permissions are checked. The service admits one network operation at a time and publishes its busy state to every monitor. Refresh controls are disabled while it runs, and duplicate requests are rejected rather than queued. Local settings and alert confirmations remain independent of network requests. The service exits after 60 seconds without clients and pending work. Disabling the plugin closes its clients. Account pausing disables that account’s polling and notifications.

## Google OAuth setup

The plugin reads a Google Desktop OAuth client configuration from:

```text
~/.config/omarchy/gmail-notifier/oauth-client.json
```

### Creating your OAuth client

Open the envelope → **HELP — Set up Google**. The eight-step guide follows the plugin/system language and explains each Google screen, with official links. You can also read the same instructions in [English](docs/OAUTH_SETUP.en.md) or [español](docs/OAUTH_SETUP.es.md).

In brief: select your Google Cloud project, enable Gmail API, configure **Google Auth Platform → Branding / Audience / Data Access**, request only `https://www.googleapis.com/auth/gmail.metadata`, then create a **Desktop app** under **Clients** and download its JSON. Keep the whole downloaded file at the path above, private to your user (folder `0700`, file `0600`). The guide explains the file-manager steps and permissions. Do not upload this file to GitHub or paste it into support chats.

**Check setup** only validates the local client file and rereads saved state. It does not launch OAuth or change accounts, settings or credentials. Saving/restoring the file is detected automatically, without restarting the plugin. Missing, invalid and unreadable files get distinct guidance.

**Existing users:** plugin updates must reuse saved accounts and usable authorization. Keep the same OAuth client. If it is missing, restore the **original** JSON from your own computer/private backup; creating a different client does not restore its predecessor's grants. The help switches to a recovery guide when saved accounts exist. A new computer needs its own one-time account connection because saved tokens live in that computer's private keyring.

Google classifies `gmail.metadata` as restricted. For regular use, review **Audience → Publishing status** before your first sign-in: an External app left in **Testing** grants access for seven days. The guide explains **In production**, Google's possible verification/organization requirements, and the distinction between an update and an externally expired/revoked grant. See [Google's audience guidance](https://support.google.com/cloud/answer/15549945) and [OAuth expiry rules](https://developers.google.com/identity/protocols/oauth2#expiration).

### Authorizing accounts

After configuring `oauth-client.json`:
1. Click the envelope icon in the bar to open the settings panel.
2. Click **Add Gmail account**. Your default browser will open Google's authorization screen.
3. Select and authorize each of your Gmail accounts (one by one).
4. Tokens are stored through the libsecret API in your desktop Secret Service. Existing secrets are read in process and copied to hashed account keys without deleting their original entries. Token refresh keeps both formats usable for rollback; new accounts use opaque IDs and compatible credential copies. No token is passed to a child process. Account settings are saved in `~/.config/omarchy/gmail-notifier/config.json`. The shared runtime snapshot, alert state and lock files are stored in `~/.config/omarchy/gmail-notifier/`, and header caches in `~/.cache/omarchy/gmail-notifier/`.

## Privacy and polling

The periodic Gmail query requests unread message IDs carrying both `INBOX` and `UNREAD`. It retrieves sender/subject headers when the user opens an account list, and a subject for a new-mail desktop notification and never requests bodies, sends mail, changes labels, or marks messages read. Snoozed messages leave Inbox and are not counted.

The displayed count changes at the next Gmail poll (2 minutes by default). The shared service pushes each completed account to every monitor in an ordered stream. The next interval starts when the previous manual or automatic sweep finishes; requests never overlap. Each account has a separate 60-second network budget and a 70-second process watchdog, so a blocked account cannot permanently freeze those after it. Private worker requests and results travel through pipes, without account IDs, sender, subject or tokens in process arguments. New unread IDs trigger flashing after the initial baseline, including replacement with an unchanged count. Late responses cannot undo an acknowledgement. Failed operations preserve the last count, report an error, and use bounded retries; detail retries are explicit. Slow or disconnected monitors cannot block broadcasts to the others. See [REFRESH_TESTING.md](REFRESH_TESTING.md) for the 0.3.1 candidate and desktop checks.

Each network operation has a 60-second budget, with individual requests limited to 20 seconds. Google responses are limited to 2 MiB, unread IDs to 10,000 per account, newly configured accounts to 32 (existing larger lists are retained), and sender/subject headers to 4,096 characters. Header pages contain at most 50 messages. The header cache is bounded to 4 MiB per account and the shared snapshot to 8 MiB; the helper reports a limit or trims visible cached details while retaining counters. Larger inboxes keep the last count and show a limit error rather than silently displaying a truncated total.

State and header caches are private to your user (directory mode 0700, files 0600). Notification contents are still visible on your screen and to your own notification server; transient notifications request no history persistence. This does not protect against software already running with your user’s privileges. Configuration writes preserve the previous valid configuration as `config.backup.json`. A corrupt configuration is reported and preserved; it is never silently replaced with an empty account list. To restore it, disable the plugin and restore a known valid backup before enabling it again.

Removing an account clears its saved local authorizations and header cache; it does not revoke the grant on Google’s servers. To revoke it there, use your Google Account’s third-party connections page. A failed local secret deletion is reported and leaves the account configured so that you can retry.

For branch installation, regression checks, desktop acceptance and rollback instructions, see [TESTING.md](TESTING.md). The implementation and outstanding manual checks for the review tasks are tracked in [TASKS.md](TASKS.md). The permanent update requirements and regression coverage are documented in [COMPATIBILITY.md](COMPATIBILITY.md): source updates must preserve settings and usable saved authorization.

For this OAuth help candidate's specific checks and acceptance limits, see [OAUTH_HELP_TESTING.md](OAUTH_HELP_TESTING.md).
